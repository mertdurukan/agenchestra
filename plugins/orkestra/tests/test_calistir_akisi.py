"""workflows/calistir.js akış testleri (kod kartı için test-önce akışı).

`python -m unittest discover -s plugins/orkestra/tests -p test_calistir_akisi.py -v`

İki katman:
- Statik testler (node GEREKMEZ, her zaman koşar): betik metninde yeni aşamalar, test-kos çağrıları,
  kart alanları ve kod-dışı yolun korunduğu.
- Akış testleri (node GEREKİR): betik sahte `agent/parallel/log/args` ile node'da koşturulur, çağrı sırası
  ve sonuç senaryo bazında sınanır. node yoksa açık gerekçeyle skip edilir. node yolu `ORKESTRA_NODE`
  ortam değişkeniyle de verilebilir (ör. Electron ikilisi; ELECTRON_RUN_AS_NODE=1 her koşuda verilir).
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BETIK = os.path.join(KOK, "workflows", "calistir.js")
SKILL = os.path.join(KOK, "skills", "is", "SKILL.md")
NODE = os.environ.get("ORKESTRA_NODE") or shutil.which("node")
NODE_YOK_GEREKCE = ("node bulunamadı (PATH'te yok, ORKESTRA_NODE boş): calistir.js akış senaryoları "
                    "koşturulamadı; statik testler yine de koşar.")

# Sahte çalışma zamanı: betiği async fonksiyon gövdesi olarak çalıştırır, her agent çağrısını kaydeder.
# Kapılar CLI `is-bitti` içinde koşar (ayrı kapı ajanı yok): test yazarı ve işçi `kapi` alanıyla sonucu bildirir.
# Senaryo anahtarları: kirmizi (test yazarının kapısı), yesil (kod kartı işçisinin kapısı), onkontrol (kod dışı işçinin
# kapısı), denetim, kart_ajan_tavani. Kapı girdileri: true | false | 'kilitli' | null (ajan sonuç vermez) |
# {gecti, cikis_kodu, ozet, cikti_kuyrugu} | {gecti:false, ihlaller:[{tur, ayrinti}]} | ham {kapi, kapi_cikis, kapi_ozeti}.
KAPI_JS = r"""
function kapiYanit(g, asama) {
  if (g === null) return null
  if (g === true) return { kapi: 'gecti' }
  if (g === false) return { kapi: 'gecmedi', kapi_cikis: 4, kapi_ozeti: asama + ' false\nKUYRUK-' + asama }
  if (g === 'kilitli') return { kapi: 'kilitli' }
  if (g.kapi) return g
  if (g.gecti === true) return { kapi: 'gecti' }
  const ihlal = (g.ihlaller || [])[0]
  const ozet = ihlal ? 'ön kontrol ' + ihlal.tur + ': ' + ihlal.ayrinti : (g.ozet || asama + ' false')
  return { kapi: 'gecmedi', kapi_cikis: typeof g.cikis_kodu === 'number' ? g.cikis_kodu : 4,
           kapi_ozeti: ozet + (g.cikti_kuyrugu ? '\n' + g.cikti_kuyrugu : '') }
}
"""

KOSUM_JS = r"""
const fs = require('fs')
const [betikYolu, senaryoYolu] = process.argv.slice(-2)
const kaynak = fs.readFileSync(betikYolu, 'utf8').replace(/^export\s+const\s+meta/m, 'const meta')
const sen = JSON.parse(fs.readFileSync(senaryoYolu, 'utf8'))
const cagrilar = [], loglar = [], sayac = {}
function sira(ad, liste, varsayilan) {
  const i = (sayac[ad] = (sayac[ad] === undefined ? -1 : sayac[ad]) + 1)
  return Array.isArray(liste) && i < liste.length ? liste[i] : varsayilan
}
""" + KAPI_JS + r"""
async function agent(istem, o) {
  cagrilar.push({ agentType: o.agentType, phase: o.phase, label: o.label, model: o.model || null,
                  ilk: istem.split('\n')[0], istem })
  if (o.agentType === 'orkestra:test-yazari') {
    const y = kapiYanit(sira('kirmizi', sen.kirmizi, true), 'kirmizi')
    return y && Object.assign({ ozet: 'test yazıldı', ciktilar: ['t.py'], kanit: ['-'] }, y)
  }
  if (o.agentType === 'orkestra:denetci') return sira('denetim', sen.denetim, { karar: 'onay', bulgular: [] })
  const kod = istem.includes('Sınıf: kod')
  const y = kod ? kapiYanit(sira('yesil', sen.yesil, true), 'yesil') : kapiYanit(sira('onkontrol', sen.onkontrol, true), 'onkontrol')
  return y && Object.assign({ ozet: 'iş yapıldı', ciktilar: ['x'], kanit: ['-'] }, y)
}
async function parallel(fns) { return Promise.all(fns.map(f => f())) }
function log(m) { loglar.push(String(m)) }
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor
new AsyncFunction('agent', 'parallel', 'log', 'args', kaynak)(agent, parallel, log, { gorevler: sen.gorevler, kart_ajan_tavani: sen.kart_ajan_tavani })
  .then(sonuc => process.stdout.write(JSON.stringify({ sonuc, cagrilar, loglar })))
  .catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(1) })
"""


def kart(**ek):
    k = {"id": "G-900", "baslik": "örnek", "basamak": "T2", "girdi": "",
         "kabul_kriterleri": ["a çalışır", "b hata verir"], "yazma_alani": ["src/a.py"], "bagimliliklar": []}
    k.update(ek)
    return k


def kod_karti(**ek):
    return kart(sinif="kod", test_komutu="python -m pytest tests", test_alani=["tests/test_a.py"], **ek)


def yurut_kaynagi(metin):
    """`async function yurut` gövdesi (bir sonraki bölüm başlığına kadar)."""
    bas = metin.index("async function yurut(")
    son = metin.index("// ----", bas)
    return metin[bas:son]


# ---------------------------------------------------------------- statik (node gerekmez)
class StatikTestler(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(BETIK, encoding="utf-8") as f:
            cls.js = f.read()
        with open(SKILL, encoding="utf-8") as f:
            cls.skill = f.read()

    def test_meta_phases_test_is_denetim(self):
        meta = self.js[: self.js.index("\n}\n")]
        basliklar = re.findall(r"title:\s*'([^']+)'", meta)
        self.assertEqual(basliklar, ["Test", "İş", "Denetim"])

    def test_kapi_ajani_yok(self):
        self.assertNotIn("phase: 'Kapı'", self.js)
        self.assertNotIn("phase: 'Ön kontrol'", self.js)
        self.assertNotIn("KAPI_AJANI", self.js)
        self.assertNotIn("function onKontrol", self.js)
        self.assertNotIn("function kapi(", self.js)
        self.assertNotIn("kart test-kos", self.js)

    def test_test_yazari_ve_asama_etiketleri(self):
        self.assertIn("'orkestra:test-yazari'", self.js)
        self.assertIn("#SUREC:test-yaz", self.js)
        self.assertIn("phase: 'Test'", self.js)
        self.assertIn("phase: 'İş'", self.js)
        self.assertIn("phase: 'Denetim'", self.js)

    def test_isci_semasinda_kapi_alani(self):
        self.assertRegex(self.js, r"required:\s*\[[^\]]*'kapi'")
        self.assertRegex(self.js, r"kapi:\s*\{\s*type:\s*'string',\s*enum:\s*\['gecti',\s*'gecmedi',\s*'kilitli',\s*'butce',\s*'alan-cakismasi'\]")
        self.assertIn("kapi_cikis", self.js)
        self.assertIn("kapi_ozeti", self.js)

    def test_kart_alanlari_okunur(self):
        for ifade in ("k.sinif === 'kod'", "k.test_komutu", "k.test_alani", "k.tdd !== false"):
            self.assertIn(ifade, self.js)

    def test_ret_nedenleri_ve_test_merceği(self):
        self.assertIn("'kirmizi-teyit'", self.js)
        self.assertIn("'test-kalitesi'", self.js)
        self.assertIn("'TEST:'", self.js)
        self.assertIn("test kalitesi:", self.js)
        self.assertRegex(self.js, r"KIRMIZI_EN_COK_YENIDEN_DENEME\s*=\s*2\b")
        self.assertRegex(self.js, r"VARSAYILAN_KART_AJAN_TAVANI\s*=\s*8\b")

    def test_isci_kapisi_denetciden_once(self):
        g = yurut_kaynagi(self.js)
        self.assertLess(g.index("kapiSonucu(is)"), g.index("'orkestra:denetci'"))
        self.assertLess(g.index("testOnce(k"), g.index("agentType: ISCI[basamak]"))

    def test_tdd_ve_kod_dali(self):
        g = yurut_kaynagi(self.js)
        # Test-önce yalnız tdd kod kartında; mercek ve test-kalitesi reddi buna göre.
        self.assertRegex(g, r"if \(tddKarti\(k\)\) \{\s*const engel = await testOnce")
        self.assertIn("if (kod) mercekler.push(TEST_MERCEGI)", g)
        self.assertIn("const testReddi = tddKarti(k) ?", g)
        # Eski mercekler, denetçi tablosu, ret eşiği ve yükseltme birebir duruyor.
        for eski in ("'doğruluk: iddialar ve sayılar kaynağıyla tutuyor mu'",
                     "'kanıt ve kapsam: her kriter kanıtlı ve eksiksiz mi'",
                     "'doğruluk ve kapsam: her kriter kanıtla karşılanıyor mu'",
                     "T1: { model: 'haiku' }",
                     "T4: { model: 'opus', effort: 'xhigh' }",
                     "const AYNI_BASAMAKTA_EN_COK_RET = 2",
                     "aynı basamakta iki ret →"):
            self.assertIn(eski, self.js)

    def test_kapi_protokolu_isci_ve_test_yazari_istemlerinde(self):
        self.assertIn("const KAPI_PROTOKOLU", self.js)
        self.assertGreaterEqual(len(re.findall(r"^\s+KAPI_PROTOKOLU,$", self.js, re.M)), 2)

    def test_skill_planlama_ve_elle_dagitim(self):
        s = self.skill
        for ifade in ("`sinif`", "test_komutu", "test_alani", "kart test-kilit-ac",
                      "orkestra:test-yazari", "#SUREC:test-yaz", "kirmizi-teyit", "test-kalitesi"):
            self.assertIn(ifade, s)
        elle = s[s.index("elle dağıt"):]
        self.assertIn("orkestra:test-yazari", elle)


# ---------------------------------------------------------------- akış (node gerekir)
@unittest.skipUnless(NODE, NODE_YOK_GEREKCE)
class AkisTestleri(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ork_calistir_")
        self.kosum = os.path.join(self.tmp, "kosum.js")
        with open(self.kosum, "w", encoding="utf-8") as f:
            f.write(KOSUM_JS)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def kos(self, gorevler, **senaryo):
        yol = os.path.join(self.tmp, "senaryo.json")
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(dict(senaryo, gorevler=gorevler), f, ensure_ascii=False)
        env = dict(os.environ, ELECTRON_RUN_AS_NODE="1")
        p = subprocess.run([NODE, self.kosum, BETIK, yol], capture_output=True, env=env, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr.decode("utf-8", "replace"))
        cikti = json.loads(p.stdout.decode("utf-8"))
        cagrilar = cikti["cagrilar"]
        # Kapı / ön kontrol ajanı artık yok: hiçbir koşuda bu aşamalarda çağrı olmamalı.
        self.assertEqual([c for c in cagrilar if c["phase"] in ("Kapı", "Ön kontrol")], [])
        return cikti["sonuc"]["sonuclar"][0], cagrilar, cikti["loglar"]

    @staticmethod
    def adimlar(cagrilar):
        def ad(c):
            if c["agentType"] == "orkestra:test-yazari":
                return "test"
            if c["agentType"] == "orkestra:denetci":
                return "denetim"
            return "is"
        return [ad(c) for c in cagrilar]

    # --- kod olmayan kart
    def test_kod_olmayan_kart_akisi(self):
        s, c, _ = self.kos([kart()])
        self.assertEqual(s["durum"], "onaylandi")
        self.assertEqual(self.adimlar(c), ["is", "denetim"])
        self.assertEqual(c[0]["agentType"], "orkestra:isci-t2")
        self.assertEqual(c[1]["model"], "sonnet")
        self.assertNotIn("test-yaz", " ".join(x["istem"] for x in c))
        self.assertNotIn("Sınıf: kod", c[0]["istem"])

    def test_kod_olmayan_kart_t3_iki_mercek_ve_yukseltme(self):
        # T3: iki mercek TEK denetçi çağrısında; T4: mercekler ayrı, bağımsız denetçilerde.
        s, c, _ = self.kos([kart(basamak="T3")], denetim=[
            {"karar": "ret", "bulgular": ["x"]},
            {"karar": "ret", "bulgular": ["TEST: kod kartı değil, özel sayılmaz"]},
            {"karar": "onay", "bulgular": []}, {"karar": "onay", "bulgular": []},
        ])
        self.assertEqual(self.adimlar(c), ["is", "denetim", "is", "denetim", "is", "denetim", "denetim"])
        ilk = [x["istem"] for x in c if x["agentType"] == "orkestra:denetci"][0]
        self.assertEqual(ilk.count("Mercek: "), 2)
        self.assertIn("tek denetimde uygula", ilk)
        isciler = [x["agentType"] for x in c if x["phase"] == "İş"]
        self.assertEqual(isciler, ["orkestra:isci-t3", "orkestra:isci-t3", "orkestra:isci-t4"])
        self.assertEqual(s["durum"], "onaylandi")
        self.assertNotIn("neden", s)

    # --- kırmızı geçmez (test yazarının is-bitti kapısı)
    def test_kirmizi_hic_gecmez_kart_reddedilir(self):
        s, c, _ = self.kos([kod_karti()], kirmizi=[False, False, False])
        self.assertEqual(s["durum"], "reddedildi")
        self.assertEqual(s["neden"], "kirmizi-teyit")
        self.assertEqual(self.adimlar(c), ["test"] * 3)  # 1 + en çok 2 yeniden deneme; işçi hiç açılmaz
        self.assertTrue(all(x["ilk"].endswith("#SUREC:test-yaz") for x in c))
        self.assertEqual(c[0]["phase"], "Test")
        self.assertIn("is-bitti", c[0]["istem"])
        self.assertEqual([g["karar"] for g in s["gecmis"] if g.get("asama") == "kirmizi"], ["gecmedi"] * 3)

    def test_kirmizi_ikinci_denemede_gecer_geri_bildirimle(self):
        s, c, _ = self.kos([kod_karti()], kirmizi=[False, True])
        self.assertEqual(s["durum"], "onaylandi")
        self.assertEqual(self.adimlar(c)[:3], ["test", "test", "is"])
        self.assertNotIn("ÖNCEKİ KIRMIZI", c[0]["istem"])
        self.assertIn("ÖNCEKİ KIRMIZI", c[1]["istem"])
        self.assertIn("KUYRUK-kirmizi", c[1]["istem"])

    # --- yeşil geçmez → denetçi çağrılmaz
    def test_yesil_gecmez_denetci_cagrilmaz_duzeltme_turu(self):
        s, c, _ = self.kos([kod_karti()], yesil=[False, True])
        self.assertEqual(self.adimlar(c), ["test", "is", "is", "denetim"])
        isler = [x for x in c if x["phase"] == "İş"]
        self.assertTrue(isler[1]["ilk"].endswith("#SUREC:duzeltme"))
        self.assertIn("KUYRUK-yesil", isler[1]["istem"])
        self.assertIn("is-bitti kapısı geçmedi", isler[1]["istem"])
        self.assertEqual(s["durum"], "onaylandi")
        self.assertIn("yesil-gecmedi", [g.get("karar") for g in s["gecmis"]])

    def test_yesil_hep_gecmez_yukseltir_denetci_hic_cagrilmaz(self):
        s, c, _ = self.kos([kod_karti()], yesil=[False] * 20)
        self.assertNotIn("denetim", self.adimlar(c))
        isciler = [x["agentType"] for x in c if x["phase"] == "İş"]
        self.assertEqual(isciler, ["orkestra:isci-t2"] * 2 + ["orkestra:isci-t3"] * 2 + ["orkestra:isci-t4"] * 2)
        self.assertEqual(s["durum"], "reddedildi")
        self.assertNotEqual(s.get("neden"), "test-kalitesi")

    # --- kod dışı kartta ön kontrol ihlali (işçinin is-bitti kapısı)
    def test_kod_disi_kapi_gecmez_talimat_ihlali_denetci_yok(self):
        s, c, _ = self.kos([kart()], onkontrol=[False, True])
        self.assertEqual(self.adimlar(c), ["is", "is", "denetim"])
        self.assertIn("Ret nedeni: talimat-ihlali", c[1]["istem"])
        self.assertIn("on-kontrol-ret", [g.get("karar") for g in s["gecmis"]])
        self.assertEqual(s["durum"], "onaylandi")

    # --- mutlu yol
    def test_mutlu_yol(self):
        s, c, _ = self.kos([kod_karti()])
        self.assertEqual(self.adimlar(c), ["test", "is", "denetim"])
        mercekler = [x["istem"] for x in c if x["agentType"] == "orkestra:denetci"]
        self.assertTrue(any("Mercek: test kalitesi" in m for m in mercekler))
        self.assertIn("Test alanı", c[1]["istem"])
        self.assertIn("tests/test_a.py", c[1]["istem"])
        self.assertIn("Testleri geçirecek kodu yaz", c[1]["istem"])
        self.assertEqual(s["durum"], "onaylandi")

    def test_istemlerde_kapi_protokolu(self):
        _, c, _ = self.kos([kod_karti()])
        for x in c:
            if x["agentType"] == "orkestra:denetci":
                self.assertNotIn("Protokol:", x["istem"])
                continue
            self.assertIn("Protokol: `orkestra kart durum <id> isleniyor`", x["istem"])
            for deger in ("kilitli", "butce", "gecti", "gecmedi"):
                self.assertIn('kapi="%s"' % deger, x["istem"])

    def test_mutlu_yol_t3_uc_mercek(self):
        # Üç mercek (doğruluk, kanıt/kapsam, test kalitesi) T3'te tek denetçi çağrısında.
        _, c, _ = self.kos([kod_karti(basamak="T3")])
        self.assertEqual(self.adimlar(c).count("denetim"), 1)
        istem = [x["istem"] for x in c if x["agentType"] == "orkestra:denetci"][0]
        self.assertEqual(istem.count("Mercek: "), 3)

    def test_mutlu_yol_t4_mercekler_ayri(self):
        _, c, _ = self.kos([kod_karti(basamak="T4")])
        self.assertEqual(self.adimlar(c).count("denetim"), 3)

    # --- tdd:false kod kartı
    def test_tdd_false_test_yazari_yok_isci_sonra_denetci(self):
        s, c, _ = self.kos([kod_karti(tdd=False)])
        self.assertEqual(s["durum"], "onaylandi")
        self.assertEqual(self.adimlar(c), ["is", "denetim"])
        self.assertEqual([x for x in c if x["agentType"] == "orkestra:test-yazari"], [])
        self.assertIn("Kodu ve test_alani'ndaki testleri birlikte yaz", c[0]["istem"])
        self.assertTrue(any("Mercek: test kalitesi" in x["istem"] for x in c if x["agentType"] == "orkestra:denetci"))

    def test_tdd_false_test_onekli_ret_normal_duzeltme(self):
        s, c, _ = self.kos([kod_karti(tdd=False)], denetim=[
            {"karar": "ret", "bulgular": ["TEST: negatif durum yok"], "duzeltme_talimati": "x"},
            {"karar": "onay", "bulgular": []},
        ])
        self.assertEqual(s["durum"], "onaylandi")
        self.assertNotEqual(s.get("neden"), "test-kalitesi")
        self.assertEqual(self.adimlar(c), ["is", "denetim", "is", "denetim"])

    # --- kilitli kart
    def test_isci_kilitli_denetci_yok(self):
        s, c, loglar = self.kos([kart()], onkontrol=["kilitli"])
        self.assertEqual(s["durum"], "kilitli")
        self.assertEqual(self.adimlar(c), ["is"])
        self.assertTrue(any("kilitli" in m for m in loglar))

    def test_kod_karti_isci_kilitli_denetci_yok(self):
        s, c, _ = self.kos([kod_karti()], yesil=["kilitli"])
        self.assertEqual(s["durum"], "kilitli")
        self.assertEqual(self.adimlar(c), ["test", "is"])

    # --- bütçe doldu (isleniyor çıkış 7)
    def test_isci_butce_denetci_yok(self):
        s, c, loglar = self.kos([kart()], onkontrol=[{"kapi": "butce", "kapi_ozeti": "orkestra: G bütçe — doldu"}])
        self.assertEqual(s["durum"], "butce")
        self.assertEqual(self.adimlar(c), ["is"])
        self.assertIn("bütçe", s["neden"])
        self.assertTrue(any("bütçe" in m for m in loglar))

    def test_test_yazari_butce_aninda_durur(self):
        s, c, _ = self.kos([kod_karti()], kirmizi=[{"kapi": "butce"}])
        self.assertEqual(s["durum"], "butce")
        self.assertEqual(self.adimlar(c), ["test"])

    # --- alan çakışması (isleniyor çıkış 5): ret/yükseltme sayılmaz
    def test_isci_alan_cakismasi_ret_ve_yukseltme_yok(self):
        s, c, loglar = self.kos([kart()], onkontrol=[{"kapi": "alan-cakismasi", "kapi_ozeti": "G-900 isleniyor'a geçemez — çakışma: G-1"}])
        self.assertEqual(s["durum"], "alan-cakismasi")
        self.assertEqual(self.adimlar(c), ["is"])  # tek işçi çağrısı: yeniden deneme/yükseltme yok
        self.assertEqual([x for x in c if x["agentType"] == "orkestra:denetci"], [])
        self.assertEqual(s["basamak"], "T2")  # basamak yükselmedi
        self.assertFalse(any(g.get("surec") == "yukseltme" for g in s["gecmis"]))
        self.assertFalse(any("ret" in str(g.get("karar", "")) for g in s["gecmis"]))
        self.assertIn("çakışma", s["neden"])
        self.assertTrue(any("çıkış 5" in m for m in loglar))

    def test_kod_karti_isci_alan_cakismasi(self):
        s, c, _ = self.kos([kod_karti()], yesil=[{"kapi": "alan-cakismasi"}])
        self.assertEqual(s["durum"], "alan-cakismasi")
        self.assertEqual(self.adimlar(c), ["test", "is"])

    def test_test_yazari_alan_cakismasi_aninda_durur(self):
        s, c, _ = self.kos([kod_karti()], kirmizi=[{"kapi": "alan-cakismasi"}])
        self.assertEqual(s["durum"], "alan-cakismasi")
        self.assertEqual(self.adimlar(c), ["test"])

    def test_test_yazari_kilitli_aninda_kilitli(self):
        s, c, _ = self.kos([kod_karti()], kirmizi=["kilitli"])
        self.assertEqual(s["durum"], "kilitli")
        self.assertEqual(self.adimlar(c), ["test"])

    # --- kart ajan tavanı
    @staticmethod
    def hep_ret(n=20):
        return [{"karar": "ret", "bulgular": ["b%d" % i], "duzeltme_talimati": "t%d" % i} for i in range(n)]

    def test_kart_ajan_tavani_arguman_ezer(self):
        s, c, loglar = self.kos([kart()], kart_ajan_tavani=2, denetim=self.hep_ret())
        self.assertEqual(s["durum"], "tavan")
        self.assertEqual(self.adimlar(c), ["is", "denetim"])  # 2 ajan; üçüncü çağrı açılmadı
        self.assertIn("2", s["neden"])
        self.assertTrue(any("tavan" in m for m in loglar))

    def test_kart_ajan_tavani_varsayilan_sekiz(self):
        s, c, _ = self.kos([kart()], denetim=self.hep_ret())
        self.assertEqual(s["durum"], "tavan")
        self.assertEqual(len(c), 8)

    def test_tavan_denetim_grubundan_once_kontrol_edilir(self):
        # T4 kod kartı üç ayrı denetçi çağrısı ister; tavan 3 ise işçi (1) + 3 denetçi sığmaz → denetçi hiç açılmaz.
        s, c, _ = self.kos([kod_karti(basamak="T4", tdd=False)], kart_ajan_tavani=3)
        self.assertEqual(s["durum"], "tavan")
        self.assertEqual(self.adimlar(c), ["is"])

    # --- TEST: reddi
    def test_test_onekli_ret_kart_reddedilir(self):
        s, c, loglar = self.kos([kod_karti()], denetim=[
            {"karar": "ret", "bulgular": ["TEST: kriter 2 için negatif durum yok"], "duzeltme_talimati": "x"},
        ])
        self.assertEqual(s["durum"], "reddedildi")
        self.assertEqual(s["neden"], "test-kalitesi")
        self.assertEqual(self.adimlar(c).count("is"), 1)  # işçiye düzeltme turu açılmaz
        self.assertTrue(any("test-kilit-ac" in m for m in loglar))

    def test_test_oneki_talimatta_da_taninir(self):
        s, _, _ = self.kos([kod_karti()], denetim=[
            {"karar": "ret", "bulgular": ["kriter 1: eksik"], "duzeltme_talimati": "TEST: totolojik assert"},
            {"karar": "onay", "bulgular": []},
        ])
        self.assertEqual(s["neden"], "test-kalitesi")

    def test_test_onekisiz_ret_normal_duzeltme(self):
        s, c, _ = self.kos([kod_karti()], denetim=[
            {"karar": "ret", "bulgular": ["kriter 1: kanıt yok"]}, {"karar": "onay", "bulgular": []},
        ])
        self.assertEqual(s["durum"], "onaylandi")
        self.assertEqual(self.adimlar(c), ["test", "is", "denetim", "is", "denetim"])


if __name__ == "__main__":
    unittest.main()
