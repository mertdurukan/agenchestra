export const meta = {
  name: 'calistir',
  description: 'Orkestra görev kartlarını bağımlılık sırasıyla, bağımsız olanları paralel yürütür; her işi ayrı bir denetçiden geçirir, iki retten sonra basamak yükseltir. Kod kartında (sinif=kod) önce test yazılır, kırmızı/yeşil test kapısından geçilir.',
  whenToUse: '/orkestra:is skill\'i görev kartlarını oluşturduktan sonra; args = { gorevler: [kart JSON...] }',
  phases: [
    { title: 'Test', detail: 'kod kartında: kabul kriterlerinden test yazarı (koddan önce)' },
    { title: 'Kapı', detail: 'kod kartında: kırmızı (kod yokken başarısız) ve yeşil (koddan sonra geçer) test kapısı' },
    { title: 'Ön kontrol', detail: 'T0: işçiden sonra, denetçiden önce model çağırmayan kapı (satır sonu, BOM, kapsam, yeni test hatası)' },
    { title: 'İş', detail: 'basamağa uygun işçi ajanı' },
    { title: 'Denetim', detail: 'işçiden ayrı denetçi; T3+ için iki mercek; kod kartında ek test kalitesi merceği' },
  ],
}

// ---------------------------------------------------------------- ayarlar
const SIRA = ['T1', 'T2', 'T3', 'T4']
const ISCI = { T1: 'orkestra:isci-t1', T2: 'orkestra:isci-t2', T3: 'orkestra:isci-t3', T4: 'orkestra:isci-t4' }
// Denetçi işçiyle AYNI basamak modelinde çalışır (maliyet: Opus denetim ~0,59$, Sonnet ~0,12$); asla altında değil.
// İstisna: kartta toplam ret sayısı DENETCI_OPUS_RET_ESIGI'ne ulaştıktan sonraki denetimler opus (T4'te xhigh).
const DENETCI = {
  T1: { model: 'haiku' },
  T2: { model: 'sonnet', effort: 'medium' },
  T3: { model: 'opus', effort: 'high' },
  T4: { model: 'opus', effort: 'xhigh' },
}
const DENETCI_OPUS_RET_ESIGI = 2
const AYNI_BASAMAKTA_EN_COK_RET = 2
// Kod kartı: kırmızı kapı geçmezse test yazarına geri bildirimle en çok bu kadar YENİDEN deneme (toplam 1 + 2).
const KIRMIZI_EN_COK_YENIDEN_DENEME = 2
const TEST_YAZARI = 'orkestra:test-yazari'
const KAPI_AJANI = 'orkestra:isci-t1'
// Test kapısı komutunun varsayılan zaman aşımı (sn). CLI varsayılanı 600 sn paralel yükte tam paket için yetmiyor;
// kartta sayısal pozitif `test_zaman_asimi` varsa o kullanılır.
const VARSAYILAN_KAPI_ZAMAN_ASIMI = 1800
// T0 ön kontrol kapısı (scripts/on_kontrol.py): model çağırmadan satır sonu/BOM/kapsam/yeni test hatası denetler.
const PLUGIN_KOKU = (typeof process !== 'undefined' && process.env && process.env.CLAUDE_PLUGIN_ROOT) || '${CLAUDE_PLUGIN_ROOT}'
const ON_KONTROL_NEDEN = {
  'kapsam': 'talimat-ihlali', 'satir-sonu': 'talimat-ihlali', 'bom': 'talimat-ihlali',
  'yeni-test-hatasi': 'kapsam-eksik', 'eksik-token': 'kapsam-eksik',
}
const TEST_MERCEGI = 'test kalitesi: her kriter test_alani\'ndaki bir testle karşılanıyor mu, negatif/uç durum var mı, totolojik assert, skip/xfail ya da aşırı mock var mı, son koşu geçen yeşil ve test dosyaları kilitle aynı mı; test yetersizse bulguyu \'TEST:\' önekiyle yaz'

const RET_NEDEN_ACIKLAMA = {
  'kapsam-eksik': 'bir ya da daha çok kriter karşılanmamış',
  'bicim': 'içerik doğru ama biçim/şema/yer yanlış',
  'sayi-tutarsiz': 'sayılar kaynakla ya da birbiriyle tutmuyor',
  'kanit-yok': 'iddialar kanıtsız (dosya:satır, komut çıktısı yok)',
  'talimat-ihlali': 'kart ya da protokol talimatı çiğnenmiş (yazma alanı, sır vb.)',
  'kriter-belirsiz': 'kabul kriteri belirsiz ya da çelişkili (kart düzeltilmeli)',
  'yetenek-yetersiz': 'iş bu basamağın yeteneğini aşıyor (üst basamak gerekir)',
}

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
// Ret nedeni kodları (scripts/ret_nedeni.py ile aynı): dikkat grubu → işçi düzeltir; kriter-belirsiz → kart; yetenek-yetersiz → basamak.
const RET_NEDENLERI = ['kapsam-eksik', 'bicim', 'sayi-tutarsiz', 'kanit-yok', 'talimat-ihlali', 'kriter-belirsiz', 'yetenek-yetersiz']
const DENETIM_SEMA = {
  type: 'object',
  properties: {
    karar: { type: 'string', enum: ['onay', 'ret'] },
    neden: { type: 'string', enum: RET_NEDENLERI },
    bulgular: { type: 'array', items: { type: 'string' } },
    duzeltme_talimati: { type: 'string' },
  },
  required: ['karar', 'bulgular'],
}
// Ön kontrol ajanının dönüşü: on_kontrol.py'nin stdout JSON'u.
const ON_KONTROL_SEMA = {
  type: 'object',
  properties: {
    gecti: { type: 'boolean' },
    ihlaller: { type: 'array', items: { type: 'object', properties: { tur: { type: 'string' }, ayrinti: { type: 'string' } } } },
    uyarilar: { type: 'array', items: { type: 'string' } },
  },
  required: ['gecti'],
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
const testKoku = k => k.test_koku || 'proje kökü'

function testBilgisi(k) {
  if (!kodKarti(k)) return ''
  return [
    `Sınıf: kod. Test komutu: ${k.test_komutu || '-'}`,
    `Test alanı (kilitli testler; bu dosyalara YAZMA): ${testAlani(k)}`,
    `Test kökü (test komutu burada koşar, test alanı buna göredir): ${testKoku(k)}`,
  ].join('\n')
}

// Denetçi 'TEST:' önekli bulgu ya da talimat satırı yazdıysa ret test kalitesindendir.
function testKalitesiReddi(d) {
  if (!d || d.karar === 'onay') return false
  const satirlar = [...(d.bulgular || []), ...String(d.duzeltme_talimati || '').split('\n')]
  return satirlar.some(s => String(s).trim().toUpperCase().startsWith('TEST:'))
}

// Birden çok mercekten gelen retlerden nedene göre öncelikli olanı seçer: kriter-belirsiz > yetenek-yetersiz > ilk ret.
function retSec(kararlar) {
  const retler = kararlar.filter(d => d.karar !== 'onay')
  return retler.find(d => d.neden === 'kriter-belirsiz') || retler.find(d => d.neden === 'yetenek-yetersiz') || retler[0]
}

// Ret sonrası bir sonraki adım (saf karar): 'kart' | 'yukselt' | 'son' | 'devam'.
// Neden yoksa ya da dikkat grubundaysa mevcut iki-ret kuralı geçerlidir.
function retSonrasi(neden, retSayisi, sonBasamak) {
  if (neden === 'kriter-belirsiz') return 'kart'
  if (neden === 'yetenek-yetersiz') return sonBasamak ? 'son' : 'yukselt'
  if (retSayisi >= AYNI_BASAMAKTA_EN_COK_RET) return sonBasamak ? 'son' : 'yukselt'
  return 'devam'
}

// Tekrarlayan ret tespiti (saf). İmza: duzeltme_talimati + sıralı bulgular; küçük harf, noktalama ve boşluk normalize.
// Yeşil test kapısı retleri (yesil: true) da imzasızdır: o yol kilitli testle tanımlı basamak yükseltmesidir.
// Denetçi sonuç döndürmediğinde üretilen yedek ret (yedek: true) imzasızdır: bu altyapı arızasıdır, işçinin aynı hatayı
// tekrarı değildir; tekrar sayılırsa işçi suçsuz yere erken kapanırdı.
function retNormalize(m) {
  return String(m || '').toLowerCase().replace(/ı/g, 'i').replace(/\u0307/g, '').replace(/[^\p{L}\p{N}\s]/gu, ' ').replace(/\s+/g, ' ').trim()
}
function retImzasi(ret) {
  if (!ret || ret.yedek || ret.yesil) return null
  return JSON.stringify([retNormalize(ret.duzeltme_talimati), (ret.bulgular || []).map(retNormalize).sort()])
}
function ayniRet(a, b) {
  const x = retImzasi(a)
  return x !== null && x === retImzasi(b)
}

// Denetçi modeli (saf): basamak modeli; toplam ret eşiğinden sonra opus (T4'te xhigh).
function denetciModeli(basamak, toplamRet) {
  const d = DENETCI[basamak]
  if (toplamRet >= DENETCI_OPUS_RET_ESIGI && d.model !== 'opus') return { model: 'opus', effort: basamak === 'T4' ? 'xhigh' : 'high' }
  return d
}

// Ön kontrol ihlallerinden ret üretir (saf): kapsam/satir-sonu/bom → talimat-ihlali, aksi kapsam-eksik.
function onKontrolReti(r) {
  const ihlaller = r.ihlaller || []
  const neden = ihlaller.some(i => ON_KONTROL_NEDEN[i.tur] !== 'kapsam-eksik') ? 'talimat-ihlali' : 'kapsam-eksik'
  return {
    onkontrol: true, neden,
    bulgular: ihlaller.map(i => `ön kontrol ${i.tur}: ${i.ayrinti || '-'}`),
    duzeltme_talimati: 'Ön kontrol ihlallerini düzelt (dosya satır sonu/BOM, yazma alanı dışı çıktı, yeni başarısız test); ihlal giderilmeden denetçi çağrılmaz.',
  }
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
    ret ? `ÖNCEKİ DENETİM RET VERDİ.${ret.neden ? ` Ret nedeni: ${ret.neden} — ${RET_NEDEN_ACIKLAMA[ret.neden] || ''}.` : ''} Düzeltme talimatı: ${ret.duzeltme_talimati || '-'}\nBulgular: ${(ret.bulgular || []).join(' | ')}` : '',
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
    `Test kökü (test komutu burada koşar, test alanı buna göredir): ${testKoku(k)}`,
    `Uygulamanın yazma alanı (sen YAZMA): ${(k.yazma_alani || []).join(', ') || '-'}`,
    geriBildirim
      ? `ÖNCEKİ KIRMIZI TEYİDİ GEÇMEDİ (kod yokken testler başarısız olmalı). Kapı özeti: ${geriBildirim.ozet || '-'}` +
        (geriBildirim.cikti_kuyrugu ? `\nÇıktı kuyruğu:\n${geriBildirim.cikti_kuyrugu}` : '')
      : '',
    `Protokolünü izle: kart durum isleniyor → test yaz → \`orkestra kart test-kos ${k.id} --asama kirmizi\` → kart durum is-bitti. Son yanıtın şemaya uygun olsun.`,
  ].filter(Boolean).join('\n')
}

function kapiZamanAsimi(k) {
  const z = k.test_zaman_asimi
  return typeof z === 'number' && Number.isFinite(z) && z > 0 ? z : VARSAYILAN_KAPI_ZAMAN_ASIMI
}

function kapiIstemi(k, asama) {
  const komut = `orkestra kart test-kos ${k.id} --asama ${asama} --zaman-asimi ${kapiZamanAsimi(k)}`
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

// oncekiRet: önceki denetimin reti (varsa yalnız karşılanmayan kriterler + gerileme denetlenir); yükseltme sonrası ilk denetimde null.
function denetimIstemi(k, is, mercek, oncekiRet) {
  return [
    `#GOREV:${k.id} #SUREC:denetim`,
    `Denetlenecek görev: ${k.baslik}`,
    'Kabul kriterleri:',
    ...k.kabul_kriterleri.map((c, i) => `  ${i + 1}. ${c}`),
    `İşçinin bildirdiği çıktılar: ${(is.ciktilar || []).join(', ') || '-'}`,
    `İşçinin özeti (güvenme, kendin doğrula): ${is.ozet}`,
    `Mercek: ${mercek}`,
    oncekiRet
      ? `Önceki denetimde karşılanmayan kriterler: ${(oncekiRet.bulgular || []).join(' | ') || '-'}. Yalnız bunları ve düzeltmenin yeni bir gerileme getirip getirmediğini (değişen dosyaların diff'i) denetle; önceki denetimde KARŞILANDI denen kriterleri yeniden kanıtlama.`
      : '',
    testBilgisi(k),
    `Ret verirsen nedeni şu kodlardan tek biri seç (öncelik: kriter belirsizse kriter-belirsiz; işin zorluğu basamağı aşıyorsa yetenek-yetersiz; aksi halde dikkat grubundan en belirgini): ${RET_NEDENLERI.join(', ')}. CLI'ya \`--neden <kod>\` ile yaz, şemadaki 'neden' alanına da koy.`,
    'Çıktıları kendin aç, her kriteri kanıtla değerlendir, kararı `orkestra kart denetim <id> --karar onay|ret [--neden <kod>] --gerekce ... --talimat ...` ile yaz, son yanıtın şemaya uygun olsun.',
  ].filter(Boolean).join('\n')
}

// ---------------------------------------------------------------- test kapısı
async function kapi(k, asama) {
  const r = await agent(kapiIstemi(k, asama), {
    agentType: KAPI_AJANI, schema: KAPI_SEMA, label: `${k.id} kapı ${asama}`, phase: 'Kapı',
  })
  if (!r) return { gecti: false, cikis_kodu: -1, ajan_yok: true, ozet: 'kapı ajanı sonuç döndürmedi' }
  return r
}

// CLI/yapılandırma hatası (çıkış 2 ya da metin): yeniden deneme/yükseltme anlamsız, kart düzeltilmeli. Çıkış 4 = gerçek test başarısızlığı.
const CLI_HATA_KALIPLARI = ['hiçbir proje dosyasına uymuyor', 'kilit yok', 'test_komutu/test_alani yok', 'kapsamıyor']
function kapiCliHatasi(r) {
  if (!r || r.gecti || r.cikis_kodu === 4) return false
  if (r.cikis_kodu === 2) return true
  // Kuyrukta yalnız CLI'ın kendi 'orkestra:' önekli satırları sayılır (pytest çıktısındaki kalıp kelimeleri değil).
  const cliSatirlari = String(r.cikti_kuyrugu || '').split(/\r?\n/).filter(l => l.trim().startsWith('orkestra:'))
  const metin = [r.ozet || '', ...cliSatirlari].join('\n')
  return CLI_HATA_KALIPLARI.some(p => metin.includes(p))
}
// Kapı komutu zaman aşımına uğradı: yeniden deneme/düzeltme/yükseltme anlamsız. Kapı ajanının hiç sonuç döndürmemesi (ajan_yok) bu sınıfa girmez.
function kapiZamanAsimiMi(r) {
  if (!r || r.gecti || r.ajan_yok) return false
  if (r.cikis_kodu === -1) return true
  const cliSatirlari = String(r.cikti_kuyrugu || '').split(/\r?\n/).filter(l => l.trim().startsWith('orkestra:'))
  return [r.ozet || '', ...cliSatirlari].join('\n').includes('zaman aşımı')
}
function zamanAsimiSonucu(k, basamak, gecmis, r, asama) {
  gecmis.push({ basamak, surec: 'test-kapisi', asama, karar: 'zaman-asimi' })
  log(`${k.id}: ${asama} kapı zaman aşımına uğradı → kart düzeltilmeli`)
  const satir = [r.ozet || '-', r.cikti_kuyrugu ? `Çıktı kuyruğu:
${r.cikti_kuyrugu}` : ''].filter(Boolean)
  return {
    id: k.id, durum: 'kart-duzeltilmeli', neden: 'kapi-zaman-asimi', basamak, gecmis,
    son_ret: {
      duzeltme_talimati: `Test kapısı zaman aşımına uğradı (${kapiZamanAsimi(k)} sn); kartın test_komutu'nu daraltın ya da test_zaman_asimi değerini artırın.`,
      bulgular: satir,
    },
  }
}
function cliHatasiSonucu(k, basamak, gecmis, r, asama) {
  gecmis.push({ basamak, surec: 'test-kapisi', asama, karar: 'cli-hatasi' })
  log(`${k.id}: ${asama} kapı CLI/yapılandırma hatası → kart düzeltilmeli`)
  const satir = [r.ozet || '-', r.cikti_kuyrugu ? `Çıktı kuyruğu:
${r.cikti_kuyrugu}` : ''].filter(Boolean)
  return {
    id: k.id, durum: 'kart-duzeltilmeli', neden: 'kapi-cli-hatasi', basamak, gecmis,
    son_ret: {
      duzeltme_talimati: `Test kapısı CLI/yapılandırma hatası verdi (çıkış ${r.cikis_kodu}); kartın test_komutu/test_alani/kilit ayarı ana ajanca düzeltilmeli.`,
      bulgular: satir,
    },
  }
}

// T0 ön kontrol: kapı ajanıyla on_kontrol.py çalıştırır. null → ajan sonuç döndürmedi (kapı atlanır, ret değil).
async function onKontrol(k, alt, ciktilar) {
  const komut = `python "${PLUGIN_KOKU}/scripts/on_kontrol.py" ${alt} ${k.id}` +
    (alt === 'kontrol' ? ` --ciktilar ${(ciktilar || []).join(',')}` : '') +
    (alt === 'kontrol' && k.kaynak_dosya ? ` --kaynak ${k.kaynak_dosya}` : '')
  const r = await agent([
    `#GOREV:${k.id} #SUREC:on-kontrol`,
    `Görev: ${k.baslik} — T0 ön kontrol (${alt}). Yalnız komut çalıştır ve JSON'u aktar; HİÇBİR dosya yazma, kart durumunu DEĞİŞTİRME.`,
    `1. \`${komut}\` komutunu tek başına çalıştır (çıkış 0 geçti, 4 ihlal, 2 kullanım hatası).`,
    'Son yanıtın yalnız komutun stdout JSON\'u olsun: {"gecti": true|false, "ihlaller": [{"tur": "...", "ayrinti": "..."}], "uyarilar": []}',
  ].join('\n'), { agentType: KAPI_AJANI, schema: ON_KONTROL_SEMA, label: `${k.id} ön kontrol ${alt}`, phase: 'Ön kontrol' })
  if (!r) log(`${k.id}: ön kontrol ${alt} ajanı sonuç döndürmedi → kapı atlandı`)
  return r || null
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
    if (kapiZamanAsimiMi(r)) return zamanAsimiSonucu(k, basamak, gecmis, r, 'kirmizi')
    if (kapiCliHatasi(r)) return cliHatasiSonucu(k, basamak, gecmis, r, 'kirmizi')
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
  let toplamRet = 0 // kartın tüm basamaklardaki ret sayısı (denetçi modeli için)
  let denetimRet = null // son LLM denetçi reti: yeniden denetim yalnız bunların karşılanmasına bakar; yükseltmede sıfırlanır
  let oncekiBasamakRet = null // yükseltmeyi tetikleyen, önceki basamağın son reti
  const gecmis = []
  const kod = kodKarti(k)

  if (kod) {
    const engel = await testOnce(k, basamak, gecmis)
    if (engel) return engel
  }
  await onKontrol(k, 'taban') // T0: ilk işçi turundan önce taban; sonuç dosyaya yazılır, ret üretmez

  for (let tur = 0; tur < 10; tur++) {
    const surec = tur === 0 ? 'is' : retSayisi === 0 ? 'yukseltme' : 'duzeltme'
    const is = await agent(isciIstemi(k, surec, sonRet), {
      agentType: ISCI[basamak], schema: ISCI_SEMA, label: `${k.id} işçi ${basamak}`, phase: 'İş',
    })
    if (!is) return { id: k.id, durum: 'hata', basamak, gecmis, neden: 'işçi ajan sonuç döndürmedi' }

    // Kod kartı: yeşil kapı. Geçmezse denetçi ÇAĞRILMAZ; çıktı kuyruğuyla düzeltme turu (ret sayılır).
    const yesil = kod ? await kapi(k, 'yesil') : null
    if (yesil && kapiZamanAsimiMi(yesil)) return zamanAsimiSonucu(k, basamak, gecmis, yesil, 'yesil')
    if (yesil && kapiCliHatasi(yesil)) return cliHatasiSonucu(k, basamak, gecmis, yesil, 'yesil')
    // T0 ön kontrol: işçiden sonra, LLM denetçiden önce. Başarısız kapı ajanı ret sayılmaz (kapı atlanır).
    const onk = yesil && !yesil.gecti ? null : await onKontrol(k, 'kontrol', is.ciktilar)
    if (yesil && !yesil.gecti) {
      gecmis.push({ basamak, surec, karar: 'yesil-gecmedi' })
      sonRet = {
        yesil: true,
        duzeltme_talimati: `Yeşil test kapısı geçmedi (çıkış ${yesil.cikis_kodu}). Testleri değiştirmeden kodu düzelt.`,
        bulgular: [yesil.ozet || '-', yesil.cikti_kuyrugu ? `Çıktı kuyruğu:\n${yesil.cikti_kuyrugu}` : ''].filter(Boolean),
      }
    } else if (onk && onk.gecti === false) {
      // Ön kontrol ihlali: denetçi ÇAĞRILMAZ; normal ret sayılır.
      gecmis.push({ basamak, surec, karar: 'on-kontrol-ret' })
      sonRet = onKontrolReti(onk)
    } else {
      const dm = denetciModeli(basamak, toplamRet)
      const mercekler = basamak === 'T3' || basamak === 'T4'
        ? ['doğruluk: iddialar ve sayılar kaynağıyla tutuyor mu', 'kanıt ve kapsam: her kriter kanıtlı ve eksiksiz mi']
        : ['doğruluk ve kapsam: her kriter kanıtla karşılanıyor mu']
      if (kod) mercekler.push(TEST_MERCEGI)
      const kararlar = (await parallel(mercekler.map(m => () =>
        agent(denetimIstemi(k, is, m, denetimRet), {
          agentType: 'orkestra:denetci', model: dm.model, ...(dm.effort ? { effort: dm.effort } : {}),
          schema: DENETIM_SEMA, label: `${k.id} denetim ${basamak}`, phase: 'Denetim',
        })))).filter(Boolean)

      // Tüm merceklerin onayı gerekir; tek ret yeter.
      const ret = retSec(kararlar)
      gecmis.push({ basamak, surec, karar: kararlar.length === 0 ? 'denetim-yok' : ret ? 'ret' : 'onay', ...(ret && ret.neden ? { neden: ret.neden } : {}) })
      if (kararlar.length > 0 && !ret) {
        return { id: k.id, durum: 'onaylandi', basamak, ozet: is.ozet, ciktilar: is.ciktilar, kanit: is.kanit, gecmis }
      }
      // Test kalitesi reddini işçi düzeltemez (testler kilitli): ana ajan kilidi açıp yeniden planlar.
      const testReddi = kod ? kararlar.find(testKalitesiReddi) : null
      if (testReddi) {
        log(`${k.id}: denetçi test kalitesini reddetti → ana ajan \`kart test-kilit-ac\` ile kilidi açıp yeniden planlamalı`)
        return { id: k.id, durum: 'reddedildi', neden: 'test-kalitesi', basamak, son_ret: testReddi, gecmis }
      }
      if (ret) denetimRet = { ...ret, bulgular: kararlar.filter(d => d.karar !== 'onay').flatMap(d => d.bulgular || []) }
      sonRet = ret || { duzeltme_talimati: 'Denetçi sonuç döndürmedi; işi kanıtlarıyla yeniden sun.', bulgular: [], yedek: true }
    }

    retSayisi += 1
    toplamRet += 1
    const i = SIRA.indexOf(basamak)
    // Yükseltmeden sonra yeni basamağın İLK reti önceki basamağın son retiyle aynıysa daha güçlü model de aynı duvara
    // çarpmıştır: sorun yetenek değil kart/kriterdir. (Aynı basamaktaki tekrar mevcut iki-ret yükseltmesine gider.)
    if (retSayisi === 1 && sonRet.neden !== 'kriter-belirsiz' && ayniRet(oncekiBasamakRet, sonRet)) {
      log(`${k.id}: yükseltme sonrası ilk ret öncekiyle aynı (tekrarlayan-ret) → ${basamak} basamağında kapatıldı`)
      return { id: k.id, durum: 'reddedildi', neden: 'tekrarlayan-ret', basamak, son_ret: sonRet, gecmis }
    }
    oncekiBasamakRet = null
    const adim = retSonrasi(sonRet.neden, retSayisi, i === SIRA.length - 1)
    if (adim === 'kart') {
      log(`${k.id}: ret nedeni kriter-belirsiz → yeniden deneme yok, kart ana ajana döner`)
      return { id: k.id, durum: 'kart-duzeltilmeli', neden: 'kriter-belirsiz', basamak, son_ret: sonRet, gecmis }
    }
    if (adim === 'son') {
      return { id: k.id, durum: 'reddedildi', basamak, son_ret: sonRet, gecmis }
    }
    if (adim === 'yukselt') {
      basamak = SIRA[i + 1]
      retSayisi = 0
      oncekiBasamakRet = sonRet
      denetimRet = null // yükseltme sonrası ilk denetim tam denetimdir
      gecmis.push({ basamak, surec: 'yukseltme', karar: '-' })
      if (sonRet.neden === 'yetenek-yetersiz') log(`${k.id}: ret nedeni yetenek-yetersiz → ${basamak} basamağına yükseltildi`)
      else log(`${k.id}: aynı basamakta iki ret → ${basamak} basamağına yükseltildi`)
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
log(`Bitti: ${say('onaylandi')} onaylandı, ${say('reddedildi')} reddedildi, ${say('kart-duzeltilmeli')} kart düzeltilmeli, ${say('atlandi')} atlandı, ${say('hata')} hata.`)
return { sonuclar }
