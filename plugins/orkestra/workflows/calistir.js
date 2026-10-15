export const meta = {
  name: 'calistir',
  description: 'Orkestra görev kartlarını bağımlılık sırasıyla, bağımsız olanları paralel yürütür; her işi ayrı bir denetçiden geçirir, iki retten sonra basamak yükseltir. Test ve ön kontrol kapıları model çağırmadan CLI is-bitti içinde koşar; TDD yalnız tdd=true kod kartında.',
  whenToUse: '/orkestra:is skill\'i görev kartlarını oluşturduktan sonra; args = { gorevler: [kart JSON...] }',
  phases: [
    { title: 'Test', detail: 'tdd=true kod kartında: kabul kriterlerinden test yazarı; kırmızı kapı is-bitti içinde (CLI)' },
    { title: 'İş', detail: 'basamağa uygun işçi ajanı' },
    { title: 'Denetim', detail: 'işçiden ayrı denetçi; T3+ için iki mercek, kod kartında ek test kalitesi merceği; mercekler T4 dışında tek çağrıda' },
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
// Mercekler yalnız bu basamaklarda ayrı denetçi çağrılarına bölünür; diğerlerinde tek çağrıda birleşir.
const MERCEK_AYRI_BASAMAKLAR = ['T4']
const AYNI_BASAMAKTA_EN_COK_RET = 2
// Kod kartı: kırmızı kapı geçmezse test yazarına geri bildirimle en çok bu kadar YENİDEN deneme (toplam 1 + 2).
const KIRMIZI_EN_COK_YENIDEN_DENEME = 2
const TEST_YAZARI = 'orkestra:test-yazari'
// Kart başına ajan tavanı (TOK-3): aşılınca kart 'tavan' sonucuyla durur, ana ajan beklemede yapar. args.kart_ajan_tavani ezer.
const VARSAYILAN_KART_AJAN_TAVANI = 8
const TEST_MERCEGI = 'test kalitesi: her kriter test_alani\'ndaki bir testle karşılanıyor mu, negatif/uç durum var mı, totolojik assert, skip/xfail ya da aşırı mock var mı, son koşu geçen yeşil ve test dosyaları kilitle aynı mı; test yetersizse bulguyu \'TEST:\' önekiyle yaz'

const RET_NEDEN_ACIKLAMA = {
  'kapsam-eksik': 'bir ya da daha çok kriter karşılanmamış',
  'bicim': 'içerik doğru ama biçim/şema/yer yanlış',
  'sayi-tutarsiz': 'sayılar kaynakla ya da birbiriyle tutmuyor',
  'kanit-yok': 'iddialar kanıtsız (dosya:satır, komut çıktısı yok)',
  'talimat-ihlali': 'kart ya da protokol talimatı çiğnenmiş (yazma alanı, sır vb.)',
  'kriter-belirsiz': 'kabul kriteri belirsiz ya da çelişkili (kart düzeltilmeli)',
  'yetenek-yetersiz': 'iş bu basamağın yeteneğini aşıyor (üst basamak gerekir)',
  'ortam': 'başarısızlık kodun değil ortamın: yük altında zamanlama, başka kartın değişikliği, eksik araç/izin; kodu ya da modeli değiştirmek çözmez',
}

const ISCI_SEMA = {
  type: 'object',
  properties: {
    ozet: { type: 'string' },
    ciktilar: { type: 'array', items: { type: 'string' } },
    kanit: { type: 'array', items: { type: 'string' } },
    acik_sorular: { type: 'array', items: { type: 'string' } },
    // is-bitti kapısının sonucu (CLI koşar): gecti | gecmedi (denemeler bitti) | kilitli (isleniyor çıkış 6) | butce (çıkış 7)
    kapi: { type: 'string', enum: ['gecti', 'gecmedi', 'kilitli', 'butce', 'alan-cakismasi'] },
    kapi_cikis: { type: 'integer' },
    kapi_ozeti: { type: 'string' },
  },
  required: ['ozet', 'ciktilar', 'kanit', 'kapi'],
}
// Ret nedeni kodları (scripts/ret_nedeni.py ile aynı): dikkat grubu → işçi düzeltir; kriter-belirsiz → kart; yetenek-yetersiz → basamak;
// ortam → ana ajan (yeniden deneme/yükseltme yok).
const RET_NEDENLERI = ['kapsam-eksik', 'bicim', 'sayi-tutarsiz', 'kanit-yok', 'talimat-ihlali', 'kriter-belirsiz', 'yetenek-yetersiz', 'ortam']
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
// ---------------------------------------------------------------- yardımcılar
const kodKarti = k => k.sinif === 'kod'
const tddKarti = k => kodKarti(k) && k.tdd !== false
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

// Birden çok mercekten gelen retlerden nedene göre öncelikli olanı seçer: kriter-belirsiz > yetenek-yetersiz > ortam > ilk ret.
function retSec(kararlar) {
  const retler = kararlar.filter(d => d.karar !== 'onay')
  return retler.find(d => d.neden === 'kriter-belirsiz') || retler.find(d => d.neden === 'yetenek-yetersiz') || retler.find(d => d.neden === 'ortam') || retler[0]
}

// Ret sonrası bir sonraki adım (saf karar): 'kart' | 'ortam' | 'yukselt' | 'son' | 'devam'.
// Neden yoksa ya da dikkat grubundaysa mevcut iki-ret kuralı geçerlidir.
function retSonrasi(neden, retSayisi, sonBasamak) {
  if (neden === 'kriter-belirsiz') return 'kart'
  if (neden === 'ortam') return 'ortam'
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

// Kapı özeti normalize (saf): rakamlar, süreler, mutlak yollar ve hex kimlikler atılır; yalnız bunlarla ayrışan
// iki özet aynı kapı hatasıdır (ör. yük altında değişen süre/sıra/geçici dizin).
function kapiOzetiNormalize(m) {
  return String(m || '').toLowerCase()
    .replace(/[a-z]:[\\/][^\s'"]*/g, ' ')
    .replace(/(^|[\s'"(=])\/[^\s'"]+/g, '$1 ')
    .replace(/\b[0-9a-f]{7,}\b/g, ' ')
    .replace(/\d+/g, ' ')
    .replace(/\s+/g, ' ').trim()
}

// Denetçi modeli (saf): basamak modeli; toplam ret eşiğinden sonra opus (T4'te xhigh).
function denetciModeli(basamak, toplamRet) {
  const d = DENETCI[basamak]
  if (toplamRet >= DENETCI_OPUS_RET_ESIGI && d.model !== 'opus') return { model: 'opus', effort: basamak === 'T4' ? 'xhigh' : 'high' }
  return d
}

// İşçi ve test yazarı için ortak kapı protokolü: kapılar is-bitti içinde CLI'de koşar (ayrı kapı ajanı yok).
const KAPI_PROTOKOLU = [
  'Protokol: `orkestra kart durum <id> isleniyor` → iş → `orkestra kart durum <id> is-bitti --ozet ... --cikti ...`.',
  '- isleniyor çıkış 6 verirse kart kilitli: HİÇBİR şey yapma, hemen kapi="kilitli" döndür.',
  '- isleniyor çıkış 5 verirse yazma alanı başka açık kartla çakışıyor: HİÇBİR şey yapma, hemen kapi="alan-cakismasi", kapi_ozeti=CLI mesajı döndür.',
  '- isleniyor çıkış 7 verirse kart bütçesi doldu: HİÇBİR şey yapma, hemen kapi="butce", kapi_ozeti=CLI mesajı döndür.',
  '- is-bitti test ve ön kontrol kapılarını kendisi koşar (Bash timeout 600000 ver; testi ayrıca koşma). Çıkış 4 → kayıt yapılmadı: çıktıdaki düşen test/ihlale göre düzelt ve is-bitti\'yi yeniden çalıştır; en çok 3 deneme.',
  '- Sonuç: kapı geçtiyse kapi="gecti"; denemeler bittiyse kapi="gecmedi", kapi_cikis=son çıkış kodu, kapi_ozeti=son çıktının son 30 satırı.',
  'Son yanıtın şemaya uygun olsun.',
].join('\n')

// ---------------------------------------------------------------- istemler
function isciIstemi(k, surec, ret) {
  return [
    `#GOREV:${k.id} #SUREC:${surec}`,
    `Görev: ${k.baslik}`,
    k.soru ? `Soru: ${k.soru}` : '',
    k.girdi ? `Girdi: ${k.girdi}` : '',
    'Kabul kriterleri:',
    ...k.kabul_kriterleri.map((c, i) => `  ${i + 1}. ${c}`),
    `Yazma alanı: ${(k.yazma_alani || []).join(', ') || '(sınırsız)'}`,
    testBilgisi(k),
    kodKarti(k) ? (tddKarti(k) ? 'Testleri geçirecek kodu yaz; testi değiştirme.' : 'Kodu ve test_alani\'ndaki testleri birlikte yaz (her kriter için en az bir test).') : '',
    ret ? `ÖNCEKİ DENETİM RET VERDİ.${ret.neden ? ` Ret nedeni: ${ret.neden} — ${RET_NEDEN_ACIKLAMA[ret.neden] || ''}.` : ''} Düzeltme talimatı: ${ret.duzeltme_talimati || '-'}\nBulgular: ${(ret.bulgular || []).join(' | ')}` : '',
    KAPI_PROTOKOLU,
  ].filter(Boolean).join('\n')
}

function testYazariIstemi(k, geriBildirim) {
  return [
    `#GOREV:${k.id} #SUREC:test-yaz`,
    `Görev: ${k.baslik} — uygulama kodundan ÖNCE kabul kriterlerinden test yaz.`,
    k.soru ? `Soru: ${k.soru}` : '',
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
    'Kırmızı teyidi is-bitti koşar: kod yokken testler başarısız olmalı; geçerse is-bitti çıkış 4 verir, testleri güçlendir.',
    KAPI_PROTOKOLU,
  ].filter(Boolean).join('\n')
}

// oncekiRet: önceki denetimin reti (varsa yalnız karşılanmayan kriterler + gerileme denetlenir); yükseltme sonrası ilk denetimde null.
function denetimIstemi(k, is, mercekler, oncekiRet) {
  const liste = [].concat(mercekler)
  return [
    `#GOREV:${k.id} #SUREC:denetim`,
    `Denetlenecek görev: ${k.baslik}`,
    'Kabul kriterleri:',
    ...k.kabul_kriterleri.map((c, i) => `  ${i + 1}. ${c}`),
    `İşçinin bildirdiği çıktılar: ${(is.ciktilar || []).join(', ') || '-'}`,
    `İşçinin özeti (güvenme, kendin doğrula): ${is.ozet}`,
    ...liste.map(m => `Mercek: ${m}`),
    liste.length > 1 ? 'Mercekleri SIRAYLA tek denetimde uygula; birinde bile karşılanmayan varsa karar ret.' : '',
    oncekiRet
      ? `Önceki denetimde karşılanmayan kriterler: ${(oncekiRet.bulgular || []).join(' | ') || '-'}. Yalnız bunları ve düzeltmenin yeni bir gerileme getirip getirmediğini (değişen dosyaların diff'i) denetle; önceki denetimde KARŞILANDI denen kriterleri yeniden kanıtlama.`
      : '',
    testBilgisi(k),
    'Test ve ön kontrol kapıları işçinin is-bitti\'sinde CLI tarafından koşuldu ve geçti (kayıt: `orkestra kart goster <id>` → test_kosulari, onkontrol_kosulari). Testi YENİDEN KOŞMA; kayda güven, değişen dosyaların diff\'ine ve kriterlere bak.',
    `Ret verirsen nedeni şu kodlardan tek biri seç (öncelik: kriter belirsizse kriter-belirsiz; işin zorluğu basamağı aşıyorsa yetenek-yetersiz; başarısızlık kodun değil test/araç ortamının (yük altında zamanlama, başka kartın değişikliği, eksik araç/izin) ise ortam; aksi halde dikkat grubundan en belirgini): ${RET_NEDENLERI.join(', ')}. CLI'ya \`--neden <kod>\` ile yaz, şemadaki 'neden' alanına da koy.`,
    'Çıktıları kendin aç, her kriteri kanıtla değerlendir, kararı `orkestra kart denetim <id> --karar onay|ret [--neden <kod>] --gerekce ... --talimat ...` ile yaz, son yanıtın şemaya uygun olsun.',
  ].filter(Boolean).join('\n')
}

// ---------------------------------------------------------------- kapı (CLI is-bitti sonucu)
// Kapılar ayrı ajan değildir: işçi/test yazarı `kart durum is-bitti` çalıştırınca CLI testi ve ön kontrolü koşar,
// geçmezse kaydı reddeder (çıkış 4) ve ajan aynı oturumda düzeltir. Ajanın bildirdiği sonuç burada okunur;
// yanlış bildirim onaya dönüşemez: denetçi CLI'si yeşil kayıt ve is-bitti olmadan onay yazmaz.
function kapiSonucu(is) {
  return {
    gecti: is.kapi === 'gecti', cikis_kodu: typeof is.kapi_cikis === 'number' ? is.kapi_cikis : 4,
    ozet: is.kapi_ozeti || '-', cikti_kuyrugu: is.kapi_ozeti || '',
  }
}

// CLI/yapılandırma hatası (çıkış 2 ya da metin): yeniden deneme/yükseltme anlamsız, kart düzeltilmeli. Çıkış 4 = gerçek test başarısızlığı.
const CLI_HATA_KALIPLARI = ['hiçbir proje dosyasına uymuyor', 'kilit yok', 'test_komutu/test_alani yok', 'kapsamıyor']
// Kalıplar yalnız CLI'ın kendi 'orkestra:' önekli satırlarında aranır: işçinin bildirdiği kapı özeti test çıktısını da
// içerir (pytest satırındaki 'kilit yok' / 'zaman aşımı' gibi kelimeler sınıflamayı bozmasın).
function cliSatirlari(r) {
  return [r.ozet || '', r.cikti_kuyrugu || ''].join('\n').split(/\r?\n/).filter(l => l.trim().startsWith('orkestra:'))
}
function kapiCliHatasi(r) {
  if (!r || r.gecti) return false
  if (r.cikis_kodu === 2) return true
  const metin = cliSatirlari(r).join('\n')
  return CLI_HATA_KALIPLARI.some(p => metin.includes(p))
}
// Kapı komutu zaman aşımına uğradı: yeniden deneme/düzeltme/yükseltme anlamsız.
function kapiZamanAsimiMi(r) {
  if (!r || r.gecti) return false
  if (r.cikis_kodu === -1) return true
  return cliSatirlari(r).join('\n').includes('zaman aşımı')
}
function zamanAsimiSonucu(k, basamak, gecmis, r, asama) {
  gecmis.push({ basamak, surec: 'test-kapisi', asama, karar: 'zaman-asimi' })
  log(`${k.id}: ${asama} kapı zaman aşımına uğradı → kart düzeltilmeli`)
  return {
    id: k.id, durum: 'kart-duzeltilmeli', neden: 'kapi-zaman-asimi', basamak, gecmis,
    son_ret: {
      duzeltme_talimati: 'Test kapısı zaman aşımına uğradı (is-bitti en çok 540 sn); kartın test_komutu\'nu daraltın.',
      bulgular: [r.ozet || '-'],
    },
  }
}
function cliHatasiSonucu(k, basamak, gecmis, r, asama) {
  gecmis.push({ basamak, surec: 'test-kapisi', asama, karar: 'cli-hatasi' })
  log(`${k.id}: ${asama} kapı CLI/yapılandırma hatası → kart düzeltilmeli`)
  return {
    id: k.id, durum: 'kart-duzeltilmeli', neden: 'kapi-cli-hatasi', basamak, gecmis,
    son_ret: {
      duzeltme_talimati: `Test kapısı CLI/yapılandırma hatası verdi (çıkış ${r.cikis_kodu}); kartın test_komutu/test_alani/kilit ayarı ana ajanca düzeltilmeli.`,
      bulgular: [r.ozet || '-'],
    },
  }
}
function butceSonucu(k, basamak, gecmis, r) {
  log(`${k.id}: kart bütçesi doldu → durduruldu; ana ajan inceler ya da \`orkestra kart butce ${k.id} --usd\` ile açar`)
  return { id: k.id, durum: 'butce', neden: (r && r.kapi_ozeti) || 'kart bütçesi doldu', basamak, gecmis }
}
function kilitliSonucu(k, basamak, gecmis) {
  log(`${k.id}: kart kilitli (kapalı ya da başka koşuda işleniyor) → bu koşuda atlandı`)
  return { id: k.id, durum: 'kilitli', neden: 'kart kapalı ya da başka koşuda işleniyor', basamak, gecmis }
}

// isleniyor çıkış 5: yazma alanı başka açık kartla çakışıyor. İşçi başarısızlığı değil: ret sayılmaz, basamak yükseltilmez.
function alanCakismasiSonucu(k, basamak, gecmis, r) {
  log(`${k.id}: yazma alanı çakışması (isleniyor çıkış 5) → bu koşuda atlandı; ret sayılmadı, yükseltme yok`)
  return { id: k.id, durum: 'alan-cakismasi', neden: (r && r.kapi_ozeti) || 'yazma alanı başka açık kartla çakışıyor', basamak, gecmis }
}

// ---------------------------------------------------------------- kart ajan tavanı
const ajanSayaci = {}
const KART_AJAN_TAVANI = (args && Number.isInteger(args.kart_ajan_tavani) && args.kart_ajan_tavani > 0)
  ? args.kart_ajan_tavani : VARSAYILAN_KART_AJAN_TAVANI
const tavanda = (k, gerekli) => (ajanSayaci[k.id] || 0) + (gerekli || 1) > KART_AJAN_TAVANI
function kartAjani(k, istem, o) {
  ajanSayaci[k.id] = (ajanSayaci[k.id] || 0) + 1
  return agent(istem, o)
}
function tavanSonucu(k, basamak, gecmis, sonRet) {
  log(`${k.id}: kart ajan tavanı (${KART_AJAN_TAVANI}) doldu → durduruldu; ana ajan kartı beklemede yapmalı`)
  return { id: k.id, durum: 'tavan', neden: `kart başına ${KART_AJAN_TAVANI} ajan tavanı`, basamak, son_ret: sonRet, gecmis }
}

// tdd=true kod kartında işten önce: test yazarı (kırmızı kapı onun is-bitti'sinde). null → işe geç; nesne → kartın son sonucu.
async function testOnce(k, basamak, gecmis) {
  let geriBildirim = null
  for (let deneme = 0; deneme <= KIRMIZI_EN_COK_YENIDEN_DENEME; deneme++) {
    if (tavanda(k)) return tavanSonucu(k, basamak, gecmis, null)
    const t = await kartAjani(k, testYazariIstemi(k, geriBildirim), {
      agentType: TEST_YAZARI, schema: ISCI_SEMA, label: `${k.id} test yazarı`, phase: 'Test',
    })
    if (!t) return { id: k.id, durum: 'hata', basamak, gecmis, neden: 'test yazarı sonuç döndürmedi' }
    if (t.kapi === 'kilitli') return kilitliSonucu(k, basamak, gecmis)
    if (t.kapi === 'butce') return butceSonucu(k, basamak, gecmis, t)
    if (t.kapi === 'alan-cakismasi') return alanCakismasiSonucu(k, basamak, gecmis, t)
    const r = kapiSonucu(t)
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
async function yurut(k, bagBekle) {
  let basamak = k.basamak === 'T0' ? 'T1' : k.basamak
  let retSayisi = 0
  let sonRet = null
  let toplamRet = 0 // kartın tüm basamaklardaki ret sayısı (denetçi modeli için)
  let denetimRet = null // son LLM denetçi reti: yeniden denetim yalnız bunların karşılanmasına bakar; yükseltmede sıfırlanır
  let oncekiKapiHam = null
  let oncekiKapiOzeti = null // son turdaki geçmeyen kapının normalize özeti (kapı geçince sıfırlanır)
  let oncekiBasamakRet = null // yükseltmeyi tetikleyen, önceki basamağın son reti
  const gecmis = []
  const kod = kodKarti(k)

  if (tddKarti(k)) {
    const engel = await testOnce(k, basamak, gecmis)
    if (engel) return engel
  }
  if (bagBekle) { // erken test: testler bağımlılıkları beklemeden yazıldı; işçi turu onaydan sonra
    const eksik = (await bagBekle).filter(x => x.durum !== 'onaylandi').map(x => x.id)
    if (eksik.length) {
      log(`${k.id}: testler yazıldı, kilitli; bağımlılık onaylanmadı (${eksik.join(', ')}) → işçi turu açılmadı`)
      return { id: k.id, durum: 'atlandi', neden: `bağımlılık onaylanmadı: ${eksik.join(', ')}`, gecmis }
    }
  }

  for (let tur = 0; tur < 10; tur++) {
    if (tavanda(k)) return tavanSonucu(k, basamak, gecmis, sonRet)
    const surec = tur === 0 ? 'is' : retSayisi === 0 ? 'yukseltme' : 'duzeltme'
    const is = await kartAjani(k, isciIstemi(k, surec, sonRet), {
      agentType: ISCI[basamak], schema: ISCI_SEMA, label: `${k.id} işçi ${basamak}`, phase: 'İş',
    })
    if (!is) return { id: k.id, durum: 'hata', basamak, gecmis, neden: 'işçi ajan sonuç döndürmedi' }
    if (is.kapi === 'kilitli') return kilitliSonucu(k, basamak, gecmis)
    if (is.kapi === 'butce') return butceSonucu(k, basamak, gecmis, is)
    if (is.kapi === 'alan-cakismasi') return alanCakismasiSonucu(k, basamak, gecmis, is)

    // Kapı (CLI is-bitti: test + ön kontrol) geçmediyse denetçi ÇAĞRILMAZ; çıktıyla düzeltme turu (ret sayılır).
    const kapi = kapiSonucu(is)
    if (!kapi.gecti && kapiZamanAsimiMi(kapi)) return zamanAsimiSonucu(k, basamak, gecmis, kapi, 'yesil')
    if (!kapi.gecti && kapiCliHatasi(kapi)) return cliHatasiSonucu(k, basamak, gecmis, kapi, 'yesil')
    if (kapi.gecti) oncekiKapiOzeti = null
    if (!kapi.gecti) {
      // Aynı kartta arka arkaya iki kapı hatası normalize edilince aynıysa sorun kod/model değil ortamdır.
      const norm = kapiOzetiNormalize(kapi.ozet)
      // Kod kartında birebir aynı özet deterministik gerçek test hatasıdır (kod düzeltir, eski akış); yalnız rakam/süre/yol
      // farkıyla ayrışan özet kararsız ortamı gösterir. Kod dışı kartta birebir tekrar da ortam sayılır.
      const ham = String(kapi.ozet || '')
      const ozdes = kod && ham === oncekiKapiHam
      if (oncekiKapiOzeti !== null && norm === oncekiKapiOzeti && !ozdes) {
        gecmis.push({ basamak, surec, karar: 'ayni-kapi-hatasi' })
        log(`${k.id}: is-bitti kapısı arka arkaya aynı hatayla geçmedi → ortam sorunu; ana ajan kartı beklemede yapmalı (yükseltme yok)`)
        return {
          id: k.id, durum: 'ortam', neden: 'ayni-kapi-hatasi', basamak, gecmis,
          son_ret: { duzeltme_talimati: 'is-bitti kapısı iki turda aynı hatayla geçmedi (normalize özet aynı); ortam kaynaklı olabilir, ana ajan ortamı/testi incelemeli.', bulgular: [kapi.ozet || '-'] },
        }
      }
      oncekiKapiOzeti = norm
      oncekiKapiHam = ham
      gecmis.push({ basamak, surec, karar: kod ? 'yesil-gecmedi' : 'on-kontrol-ret' })
      sonRet = {
        yesil: true, neden: kod ? undefined : 'talimat-ihlali',
        duzeltme_talimati: `is-bitti kapısı geçmedi (çıkış ${kapi.cikis_kodu}). ${kod ? 'Testleri değiştirmeden kodu düzelt.' : 'Ön kontrol ihlalini düzelt.'}`,
        bulgular: [kapi.ozet || '-'],
      }
    } else {
      const dm = denetciModeli(basamak, toplamRet)
      const mercekler = basamak === 'T3' || basamak === 'T4'
        ? ['doğruluk: iddialar ve sayılar kaynağıyla tutuyor mu', 'kanıt ve kapsam: her kriter kanıtlı ve eksiksiz mi']
        : ['doğruluk ve kapsam: her kriter kanıtla karşılanıyor mu']
      if (kod) mercekler.push(TEST_MERCEGI)
      // Maliyet: T1-T3'te tüm mercekler TEK denetçi çağrısında (aynı dosyaları bir kez okur); yalnız T4'te ayrı, bağımsız denetçiler.
      const gruplar = MERCEK_AYRI_BASAMAKLAR.includes(basamak) ? mercekler.map(m => [m]) : [mercekler]
      if (tavanda(k, gruplar.length)) return tavanSonucu(k, basamak, gecmis, sonRet)
      const kararlar = (await parallel(gruplar.map(m => () =>
        kartAjani(k, denetimIstemi(k, is, m, denetimRet), {
          agentType: 'orkestra:denetci', model: dm.model, ...(dm.effort ? { effort: dm.effort } : {}),
          schema: DENETIM_SEMA, label: `${k.id} denetim ${basamak}`, phase: 'Denetim',
        })))).filter(Boolean)

      // Tüm merceklerin onayı gerekir; tek ret yeter.
      const ret = retSec(kararlar)
      gecmis.push({ basamak, surec, karar: kararlar.length === 0 ? 'denetim-yok' : ret ? 'ret' : 'onay', ...(ret && ret.neden ? { neden: ret.neden } : {}) })
      if (kararlar.length > 0 && !ret) {
        return { id: k.id, durum: 'onaylandi', basamak, ozet: is.ozet, ciktilar: is.ciktilar, kanit: is.kanit, gecmis }
      }
      // Test kalitesi reddini TDD kartında işçi düzeltemez (testler kilitli): ana ajan kilidi açıp yeniden planlar.
      const testReddi = tddKarti(k) ? kararlar.find(testKalitesiReddi) : null
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
    if (retSayisi === 1 && sonRet.neden !== 'kriter-belirsiz' && sonRet.neden !== 'ortam' && ayniRet(oncekiBasamakRet, sonRet)) {
      log(`${k.id}: yükseltme sonrası ilk ret öncekiyle aynı (tekrarlayan-ret) → ${basamak} basamağında kapatıldı`)
      return { id: k.id, durum: 'reddedildi', neden: 'tekrarlayan-ret', basamak, son_ret: sonRet, gecmis }
    }
    oncekiBasamakRet = null
    const adim = retSonrasi(sonRet.neden, retSayisi, i === SIRA.length - 1)
    if (adim === 'kart') {
      log(`${k.id}: ret nedeni kriter-belirsiz → yeniden deneme yok, kart ana ajana döner`)
      return { id: k.id, durum: 'kart-duzeltilmeli', neden: 'kriter-belirsiz', basamak, son_ret: sonRet, gecmis }
    }
    if (adim === 'ortam') {
      log(`${k.id}: ret nedeni ortam → yeniden deneme/yükseltme yok; ana ajan kartı beklemede yapmalı`)
      return { id: k.id, durum: 'ortam', neden: 'ortam', basamak, son_ret: sonRet, gecmis }
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
// hedef, bağımlılık zinciri üzerinden kendine dönüyor mu (döngü)?
function donguda(hedef, id, gorulen) {
  for (const d of (kimlik[id].bagimliliklar || []).filter(x => kimlik[x])) {
    if (d === hedef) return true
    if (gorulen.has(d)) continue
    gorulen.add(d)
    if (donguda(hedef, d, gorulen)) return true
  }
  return false
}
function calistir(id, yol) {
  if (yol.includes(id)) return Promise.resolve({ id, durum: 'hata', neden: `bağımlılık döngüsü: ${[...yol, id].join(' → ')}` })
  if (!soz[id]) {
    const k = kimlik[id]
    const bag = (k.bagimliliklar || []).filter(d => kimlik[d])
    const bagP = Promise.all(bag.map(d => calistir(d, [...yol, id])))
    // Erken test: bağımlılığı olan kod kartında test yazarı + kırmızı kapı bağımlılıkları beklemeden başlar; işçi turu onaydan sonra.
    // Döngüdeki kartta erken başlama yok (eski yol: önce bağımlılıklar çözülür).
    if (tddKarti(k) && bag.length > 0 && !donguda(id, id, new Set())) {
      soz[id] = yurut(k, bagP)
    } else {
      soz[id] = bagP.then(sonuclar => {
        const eksik = sonuclar.filter(s => s.durum !== 'onaylandi').map(s => s.id)
        if (eksik.length) return { id, durum: 'atlandi', neden: `bağımlılık onaylanmadı: ${eksik.join(', ')}` }
        return yurut(k)
      })
    }
  }
  return soz[id]
}

log(`${kartlar.length} kart; bağımsız olanlar paralel koşuyor.`)
const sonuclar = await Promise.all(kartlar.map(k => calistir(k.id, [])))
const say = d => sonuclar.filter(s => s.durum === d).length
log(`Bitti: ${say('onaylandi')} onaylandı, ${say('reddedildi')} reddedildi, ${say('kart-duzeltilmeli')} kart düzeltilmeli, ${say('atlandi')} atlandı, ${say('kilitli')} kilitli, ${say('tavan')} tavan, ${say('butce')} bütçe, ${say('alan-cakismasi')} alan çakışması, ${say('ortam')} ortam, ${say('hata')} hata.`)
const ajanToplam = Object.values(ajanSayaci).reduce((a, b) => a + b, 0)
log(`Ajan: ${ajanToplam} (kart başına tavan ${KART_AJAN_TAVANI}).`)
return { sonuclar }
