export const meta = {
  name: 'calistir',
  description: 'Orkestra görev kartlarını bağımlılık sırasıyla, bağımsız olanları paralel yürütür; her işi ayrı bir denetçiden geçirir, iki retten sonra basamak yükseltir.',
  whenToUse: '/orkestra:is skill\'i görev kartlarını oluşturduktan sonra; args = { gorevler: [kart JSON...] }',
  phases: [
    { title: 'İş', detail: 'basamağa uygun işçi ajanı' },
    { title: 'Denetim', detail: 'işçiden ayrı denetçi; T3+ için iki mercek' },
  ],
}

// ---------------------------------------------------------------- ayarlar
const SIRA = ['T1', 'T2', 'T3', 'T4']
const ISCI = { T1: 'orkestra:isci-t1', T2: 'orkestra:isci-t2', T3: 'orkestra:isci-t3', T4: 'orkestra:isci-t4' }
// Denetçi işçinin bir üstünde ya da (en üstte) eşit basamakta çalışır; asla altında değil.
const DENETCI = {
  T1: { model: 'sonnet', effort: 'medium' },
  T2: { model: 'opus', effort: 'medium' },
  T3: { model: 'opus', effort: 'high' },
  T4: { model: 'opus', effort: 'xhigh' },
}
const AYNI_BASAMAKTA_EN_COK_RET = 2

const ISCI_SEMA = {
  type: 'object',
  properties: {
    ozet: { type: 'string' },
    ciktilar: { type: 'array', items: { type: 'string' } },
    kanit: { type: 'array', items: { type: 'string' } },
    acik_sorular: { type: 'array', items: { type: 'string' } },
  },
  required: ['ozet', 'ciktilar', 'kanit'],
}
const DENETIM_SEMA = {
  type: 'object',
  properties: {
    karar: { type: 'string', enum: ['onay', 'ret'] },
    bulgular: { type: 'array', items: { type: 'string' } },
    duzeltme_talimati: { type: 'string' },
  },
  required: ['karar', 'bulgular'],
}

// ---------------------------------------------------------------- istemler
function isciIstemi(k, surec, ret) {
  return [
    `#GOREV:${k.id} #SUREC:${surec}`,
    `Görev: ${k.baslik}`,
    k.girdi ? `Girdi: ${k.girdi}` : '',
    'Kabul kriterleri:',
    ...k.kabul_kriterleri.map((c, i) => `  ${i + 1}. ${c}`),
    `Yazma alanı: ${(k.yazma_alani || []).join(', ') || '(sınırsız)'}`,
    ret ? `ÖNCEKİ DENETİM RET VERDİ. Düzeltme talimatı: ${ret.duzeltme_talimati || '-'}\nBulgular: ${(ret.bulgular || []).join(' | ')}` : '',
    'Protokolünü izle: kart durum isleniyor → iş → kart durum is-bitti. Son yanıtın şemaya uygun olsun.',
  ].filter(Boolean).join('\n')
}

function denetimIstemi(k, is, mercek) {
  return [
    `#GOREV:${k.id} #SUREC:denetim`,
    `Denetlenecek görev: ${k.baslik}`,
    'Kabul kriterleri:',
    ...k.kabul_kriterleri.map((c, i) => `  ${i + 1}. ${c}`),
    `İşçinin bildirdiği çıktılar: ${(is.ciktilar || []).join(', ') || '-'}`,
    `İşçinin özeti (güvenme, kendin doğrula): ${is.ozet}`,
    `Mercek: ${mercek}`,
    'Çıktıları kendin aç, her kriteri kanıtla değerlendir, kararı `orkestra kart denetim` ile yaz, son yanıtın şemaya uygun olsun.',
  ].join('\n')
}

// ---------------------------------------------------------------- tek görev
async function yurut(k) {
  let basamak = k.basamak === 'T0' ? 'T1' : k.basamak
  let retSayisi = 0
  let sonRet = null
  const gecmis = []
  for (let tur = 0; tur < 10; tur++) {
    const surec = tur === 0 ? 'is' : retSayisi === 0 ? 'yukseltme' : 'duzeltme'
    const is = await agent(isciIstemi(k, surec, sonRet), {
      agentType: ISCI[basamak], schema: ISCI_SEMA, label: `${k.id} işçi ${basamak}`, phase: 'İş',
    })
    if (!is) return { id: k.id, durum: 'hata', basamak, gecmis, neden: 'işçi ajan sonuç döndürmedi' }

    const mercekler = basamak === 'T3' || basamak === 'T4'
      ? ['doğruluk: iddialar ve sayılar kaynağıyla tutuyor mu', 'kanıt ve kapsam: her kriter kanıtlı ve eksiksiz mi']
      : ['doğruluk ve kapsam: her kriter kanıtla karşılanıyor mu']
    const kararlar = (await parallel(mercekler.map(m => () =>
      agent(denetimIstemi(k, is, m), {
        agentType: 'orkestra:denetci', model: DENETCI[basamak].model, effort: DENETCI[basamak].effort,
        schema: DENETIM_SEMA, label: `${k.id} denetim ${basamak}`, phase: 'Denetim',
      })))).filter(Boolean)

    // Tüm merceklerin onayı gerekir; tek ret yeter.
    const ret = kararlar.find(d => d.karar !== 'onay')
    gecmis.push({ basamak, surec, karar: kararlar.length === 0 ? 'denetim-yok' : ret ? 'ret' : 'onay' })
    if (kararlar.length > 0 && !ret) {
      return { id: k.id, durum: 'onaylandi', basamak, ozet: is.ozet, ciktilar: is.ciktilar, kanit: is.kanit, gecmis }
    }
    sonRet = ret || { duzeltme_talimati: 'Denetçi sonuç döndürmedi; işi kanıtlarıyla yeniden sun.', bulgular: [] }
    retSayisi += 1
    if (retSayisi >= AYNI_BASAMAKTA_EN_COK_RET) {
      const i = SIRA.indexOf(basamak)
      if (i === SIRA.length - 1) {
        return { id: k.id, durum: 'reddedildi', basamak, son_ret: sonRet, gecmis }
      }
      basamak = SIRA[i + 1]
      retSayisi = 0
      gecmis.push({ basamak, surec: 'yukseltme', karar: '-' })
      log(`${k.id}: aynı basamakta iki ret → ${basamak} basamağına yükseltildi`)
    }
  }
  return { id: k.id, durum: 'reddedildi', basamak, son_ret: sonRet, gecmis }
}

// ---------------------------------------------------------------- DAG yürütme
const kartlar = (args && args.gorevler) || []
if (kartlar.length === 0) {
  return { hata: 'args.gorevler boş: önce `orkestra kart toplu` ile kartları oluştur ve JSON listesini ver.' }
}
const kimlik = {}
for (const k of kartlar) kimlik[k.id] = k

const soz = {}
function calistir(id, yol) {
  if (yol.includes(id)) return Promise.resolve({ id, durum: 'hata', neden: `bağımlılık döngüsü: ${[...yol, id].join(' → ')}` })
  if (!soz[id]) {
    const k = kimlik[id]
    const bag = (k.bagimliliklar || []).filter(d => kimlik[d])
    soz[id] = Promise.all(bag.map(d => calistir(d, [...yol, id]))).then(sonuclar => {
      const eksik = sonuclar.filter(s => s.durum !== 'onaylandi').map(s => s.id)
      if (eksik.length) return { id, durum: 'atlandi', neden: `bağımlılık onaylanmadı: ${eksik.join(', ')}` }
      return yurut(k)
    })
  }
  return soz[id]
}

log(`${kartlar.length} kart; bağımsız olanlar paralel koşuyor.`)
const sonuclar = await Promise.all(kartlar.map(k => calistir(k.id, [])))
const say = d => sonuclar.filter(s => s.durum === d).length
log(`Bitti: ${say('onaylandi')} onaylandı, ${say('reddedildi')} reddedildi, ${say('atlandi')} atlandı, ${say('hata')} hata.`)
return { sonuclar }
