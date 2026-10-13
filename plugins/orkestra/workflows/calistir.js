export const meta = {
  name: 'calistir',
  description: 'Orkestra görev kartlarını bağımlılık sırasıyla, bağımsız olanları paralel yürütür; her işi ayrı bir denetçiden geçirir, iki retten sonra basamak yükseltir. Kod kartında (sinif=kod) önce test yazılır, kırmızı/yeşil test kapısından geçilir.',
  whenToUse: '/orkestra:is skill\'i görev kartlarını oluşturduktan sonra; args = { gorevler: [kart JSON...] }',
  phases: [
    { title: 'Test', detail: 'kod kartında: kabul kriterlerinden test yazarı (koddan önce)' },
    { title: 'Kapı', detail: 'kod kartında: kırmızı (kod yokken başarısız) ve yeşil (koddan sonra geçer) test kapısı' },
    { title: 'İş', detail: 'basamağa uygun işçi ajanı' },
    { title: 'Denetim', detail: 'işçiden ayrı denetçi; T3+ için iki mercek; kod kartında ek test kalitesi merceği' },
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
// Kod kartı: kırmızı kapı geçmezse test yazarına geri bildirimle en çok bu kadar YENİDEN deneme (toplam 1 + 2).
const KIRMIZI_EN_COK_YENIDEN_DENEME = 2
const TEST_YAZARI = 'orkestra:test-yazari'
const KAPI_AJANI = 'orkestra:isci-t1'
const TEST_MERCEGI = 'test kalitesi: her kriter test_alani\'ndaki bir testle karşılanıyor mu, negatif/uç durum var mı, totolojik assert, skip/xfail ya da aşırı mock var mı, son koşu geçen yeşil ve test dosyaları kilitle aynı mı; test yetersizse bulguyu \'TEST:\' önekiyle yaz'

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
// Test kapısı ajanının dönüşü: {gecti, cikis_kodu, ozet}; cikti_kuyrugu isteğe bağlı (düzeltme turuna aktarılır).
const KAPI_SEMA = {
  type: 'object',
  properties: {
    gecti: { type: 'boolean' },
    cikis_kodu: { type: 'integer' },
    ozet: { type: 'string' },
    cikti_kuyrugu: { type: 'string' },
  },
  required: ['gecti', 'cikis_kodu', 'ozet'],
}

// ---------------------------------------------------------------- yardımcılar
const kodKarti = k => k.sinif === 'kod'
const testAlani = k => (k.test_alani || []).join(', ') || '-'

function testBilgisi(k) {
  if (!kodKarti(k)) return ''
  return [
    `Sınıf: kod. Test komutu: ${k.test_komutu || '-'}`,
    `Test alanı (kilitli testler; bu dosyalara YAZMA): ${testAlani(k)}`,
  ].join('\n')
}

// Denetçi 'TEST:' önekli bulgu ya da talimat satırı yazdıysa ret test kalitesindendir.
function testKalitesiReddi(d) {
  if (!d || d.karar === 'onay') return false
  const satirlar = [...(d.bulgular || []), ...String(d.duzeltme_talimati || '').split('\n')]
  return satirlar.some(s => String(s).trim().toUpperCase().startsWith('TEST:'))
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
    testBilgisi(k),
    kodKarti(k) ? `Testleri geçirecek kodu yaz; testi değiştirme. is-bitti öncesi \`orkestra kart test-kos ${k.id} --asama yesil\` ile kendin dene.` : '',
    ret ? `ÖNCEKİ DENETİM RET VERDİ. Düzeltme talimatı: ${ret.duzeltme_talimati || '-'}\nBulgular: ${(ret.bulgular || []).join(' | ')}` : '',
    'Protokolünü izle: kart durum isleniyor → iş → kart durum is-bitti. Son yanıtın şemaya uygun olsun.',
  ].filter(Boolean).join('\n')
}

function testYazariIstemi(k, geriBildirim) {
  return [
    `#GOREV:${k.id} #SUREC:test-yaz`,
    `Görev: ${k.baslik} — uygulama kodundan ÖNCE kabul kriterlerinden test yaz.`,
    k.girdi ? `Girdi: ${k.girdi}` : '',
    'Kabul kriterleri:',
    ...k.kabul_kriterleri.map((c, i) => `  ${i + 1}. ${c}`),
    `Test komutu: ${k.test_komutu || '-'}`,
    `Test alanı (yalnız buraya yaz): ${testAlani(k)}`,
    `Uygulamanın yazma alanı (sen YAZMA): ${(k.yazma_alani || []).join(', ') || '-'}`,
    geriBildirim
      ? `ÖNCEKİ KIRMIZI TEYİDİ GEÇMEDİ (kod yokken testler başarısız olmalı). Kapı özeti: ${geriBildirim.ozet || '-'}` +
        (geriBildirim.cikti_kuyrugu ? `\nÇıktı kuyruğu:\n${geriBildirim.cikti_kuyrugu}` : '')
      : '',
    `Protokolünü izle: kart durum isleniyor → test yaz → \`orkestra kart test-kos ${k.id} --asama kirmizi\` → kart durum is-bitti. Son yanıtın şemaya uygun olsun.`,
  ].filter(Boolean).join('\n')
}

function kapiIstemi(k, asama) {
  const komut = `orkestra kart test-kos ${k.id} --asama ${asama}`
  return [
    `#GOREV:${k.id} #SUREC:test-kapisi`,
    `Görev: ${k.baslik} — ${asama} test kapısı. Yalnız komut çalıştır ve sonucu bildir; HİÇBİR dosya yazma, kart durumunu DEĞİŞTİRME (kart durum isleniyor/is-bitti çalıştırma).`,
    `1. \`${komut}\` komutunu tek başına çalıştır. Çıkış 0 → geçti; 4 → geçmedi; başka kod → geçmedi (CLI hatası; mesajı özete yaz).`,
    asama === 'kirmizi'
      ? `   İstisna: hata "zaten kilitli" ise test yazarı kırmızıyı kendisi koşup kilitlemiştir. O durumda \`orkestra kart goster ${k.id}\` ile test_kosulari'ndaki SON kırmızı kaydın gecti=true olduğunu ve test_kilidi'nin dolu olduğunu doğrula; ikisi de doğruysa gecti=true, cikis_kodu=o kaydın cikis_kodu.`
      : '',
    `2. \`orkestra kart goster ${k.id}\` ile test_kosulari'ndaki son kaydın cikti_kuyrugu alanının son 40 satırını al.`,
    'Son yanıtın yalnız şu JSON olsun: {"gecti": true|false, "cikis_kodu": <tamsayı>, "ozet": "<CLI çıktı satırı + tek cümle>", "cikti_kuyrugu": "<son satırlar>"}',
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
    testBilgisi(k),
    'Çıktıları kendin aç, her kriteri kanıtla değerlendir, kararı `orkestra kart denetim` ile yaz, son yanıtın şemaya uygun olsun.',
  ].filter(Boolean).join('\n')
}

// ---------------------------------------------------------------- test kapısı
async function kapi(k, asama) {
  const r = await agent(kapiIstemi(k, asama), {
    agentType: KAPI_AJANI, schema: KAPI_SEMA, label: `${k.id} kapı ${asama}`, phase: 'Kapı',
  })
  if (!r) return { gecti: false, cikis_kodu: -1, ozet: 'kapı ajanı sonuç döndürmedi' }
  return r
}

// Kod kartında işten önce: test yazarı + kırmızı kapı. null → işe geç; nesne → kartın son sonucu.
async function testOnce(k, basamak, gecmis) {
  let geriBildirim = null
  for (let deneme = 0; deneme <= KIRMIZI_EN_COK_YENIDEN_DENEME; deneme++) {
    const t = await agent(testYazariIstemi(k, geriBildirim), {
      agentType: TEST_YAZARI, schema: ISCI_SEMA, label: `${k.id} test yazarı`, phase: 'Test',
    })
    if (!t) return { id: k.id, durum: 'hata', basamak, gecmis, neden: 'test yazarı sonuç döndürmedi' }
    const r = await kapi(k, 'kirmizi')
    gecmis.push({ basamak, surec: 'test-kapisi', asama: 'kirmizi', karar: r.gecti ? 'gecti' : 'gecmedi' })
    if (r.gecti) return null
    geriBildirim = r
    log(`${k.id}: kırmızı teyit geçmedi (${deneme + 1}. deneme)`)
  }
  return {
    id: k.id, durum: 'reddedildi', neden: 'kirmizi-teyit', basamak, gecmis,
    son_ret: {
      duzeltme_talimati: 'Testler kod yokken başarısız olmadı ya da koşulamadı; ana ajan test planını yeniden ele almalı.',
      bulgular: [geriBildirim.ozet || '-'],
    },
  }
}

// ---------------------------------------------------------------- tek görev
async function yurut(k) {
  let basamak = k.basamak === 'T0' ? 'T1' : k.basamak
  let retSayisi = 0
  let sonRet = null
  const gecmis = []
  const kod = kodKarti(k)

  if (kod) {
    const engel = await testOnce(k, basamak, gecmis)
    if (engel) return engel
  }

  for (let tur = 0; tur < 10; tur++) {
    const surec = tur === 0 ? 'is' : retSayisi === 0 ? 'yukseltme' : 'duzeltme'
    const is = await agent(isciIstemi(k, surec, sonRet), {
      agentType: ISCI[basamak], schema: ISCI_SEMA, label: `${k.id} işçi ${basamak}`, phase: 'İş',
    })
    if (!is) return { id: k.id, durum: 'hata', basamak, gecmis, neden: 'işçi ajan sonuç döndürmedi' }

    // Kod kartı: yeşil kapı. Geçmezse denetçi ÇAĞRILMAZ; çıktı kuyruğuyla düzeltme turu (ret sayılır).
    const yesil = kod ? await kapi(k, 'yesil') : null
    if (yesil && !yesil.gecti) {
      gecmis.push({ basamak, surec, karar: 'yesil-gecmedi' })
      sonRet = {
        duzeltme_talimati: `Yeşil test kapısı geçmedi (çıkış ${yesil.cikis_kodu}). Testleri değiştirmeden kodu düzelt.`,
        bulgular: [yesil.ozet || '-', yesil.cikti_kuyrugu ? `Çıktı kuyruğu:\n${yesil.cikti_kuyrugu}` : ''].filter(Boolean),
      }
    } else {
      const mercekler = basamak === 'T3' || basamak === 'T4'
        ? ['doğruluk: iddialar ve sayılar kaynağıyla tutuyor mu', 'kanıt ve kapsam: her kriter kanıtlı ve eksiksiz mi']
        : ['doğruluk ve kapsam: her kriter kanıtla karşılanıyor mu']
      if (kod) mercekler.push(TEST_MERCEGI)
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
      // Test kalitesi reddini işçi düzeltemez (testler kilitli): ana ajan kilidi açıp yeniden planlar.
      const testReddi = kod ? kararlar.find(testKalitesiReddi) : null
      if (testReddi) {
        log(`${k.id}: denetçi test kalitesini reddetti → ana ajan \`kart test-kilit-ac\` ile kilidi açıp yeniden planlamalı`)
        return { id: k.id, durum: 'reddedildi', neden: 'test-kalitesi', basamak, son_ret: testReddi, gecmis }
      }
      sonRet = ret || { duzeltme_talimati: 'Denetçi sonuç döndürmedi; işi kanıtlarıyla yeniden sun.', bulgular: [] }
    }

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
