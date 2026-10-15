"""workflows/calistir.js erken test (PAR-4) ve paralel yürütme testleri.

Betik sahte `agent/parallel/log/args` ile node'da koşturulur (test_calistir_akisi.py ile aynı yöntem);
node yoksa gerekçeli skip edilir. node yolu `ORKESTRA_NODE` ile de verilebilir.

Kapılar artık `kart durum is-bitti` (CLI) içinde koşar; ayrı kapı / ön kontrol ajanı ve kapı semaforu yoktur.
Sahte ajan kart başına senaryo okur (`kartlar[id]`): kirmizi (test yazarının kapısı), yesil (kod kartı işçisi),
onkontrol (kod dışı işçi), denetim. Girdiler: true | false | {gecti, cikis_kodu, ozet} (test_calistir_akisi.KAPI_JS).
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from test_calistir_akisi import KAPI_JS

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BETIK = os.path.join(KOK, "workflows", "calistir.js")
NODE = os.environ.get("ORKESTRA_NODE") or shutil.which("node")
NODE_YOK_GEREKCE = ("node bulunamadı (PATH'te yok, ORKESTRA_NODE boş): calistir.js paralel senaryoları "
                    "koşturulamadı; statik testler yine de koşar.")

KOSUM_JS = r"""
const fs = require('fs')
const [betikYolu, senaryoYolu] = process.argv.slice(-2)
const kaynak = fs.readFileSync(betikYolu, 'utf8').replace(/^export\s+const\s+meta/m, 'const meta')
const sen = JSON.parse(fs.readFileSync(senaryoYolu, 'utf8'))
const kart = sen.kartlar || {}
const cagrilar = [], loglar = [], sayac = {}
let seq = 0, yazarAktif = 0, yazarEnCok = 0
const bekle = ms => new Promise(r => setTimeout(r, ms || 0))
function sira(anahtar, liste, varsayilan) {
  const i = (sayac[anahtar] = (sayac[anahtar] === undefined ? -1 : sayac[anahtar]) + 1)
  return Array.isArray(liste) && i < liste.length ? liste[i] : varsayilan
}
""" + KAPI_JS + r"""
async function agent(istem, o) {
  const id = String(o.label).split(' ')[0]
  const ks = kart[id] || {}
  const c = { agentType: o.agentType, phase: o.phase, label: o.label, model: o.model || null,
              ilk: istem.split('\n')[0], istem, id, bas: ++seq }
  cagrilar.push(c)
  const bitir = r => { c.son = ++seq; return r }
  if (o.agentType === 'orkestra:test-yazari') {
    yazarAktif++; yazarEnCok = Math.max(yazarEnCok, yazarAktif)
    await bekle((sen.gecikme || {}).yazar)
    yazarAktif--
    const y = kapiYanit(sira('kir:' + id, ks.kirmizi, true), 'kirmizi')
    return bitir(y && Object.assign({ ozet: 'test yazıldı', ciktilar: ['t.py'], kanit: ['-'] }, y))
  }
  if (o.agentType === 'orkestra:denetci') {
    await bekle(((sen.gecikme || {}).denetim || {})[id])
    return bitir(sira('den:' + id, ks.denetim, { karar: 'onay', bulgular: [] }))
  }
  await bekle(((sen.gecikme || {}).isci || {})[id])
  const kod = istem.includes('Sınıf: kod')
  const y = kod ? kapiYanit(sira('yes:' + id, ks.yesil, true), 'yesil') : kapiYanit(sira('onk:' + id, ks.onkontrol, true), 'onkontrol')
  return bitir(y && Object.assign({ ozet: 'iş yapıldı', ciktilar: ['x.py'], kanit: ['-'] }, y))
}
async function parallel(fns) { return Promise.all(fns.map(f => f())) }
function log(m) { loglar.push(String(m)) }
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor
new AsyncFunction('agent', 'parallel', 'log', 'args', kaynak)(agent, parallel, log, { gorevler: sen.gorevler })
  .then(sonuc => process.stdout.write(JSON.stringify({ sonuc, cagrilar, loglar, yazarEnCok })))
  .catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(1) })
"""


def kod_karti(id_="G-900", **ek):
    k = {"id": id_, "baslik": "örnek " + id_, "basamak": "T2", "girdi": "", "sinif": "kod",
         "kabul_kriterleri": ["a çalışır", "b hata verir"], "yazma_alani": ["src/" + id_ + ".py"],
         "bagimliliklar": [], "test_komutu": "python -m pytest tests", "test_alani": ["tests/test_a.py"]}
    k.update(ek)
    return k


def duz_kart(id_="G-901", **ek):
    k = {"id": id_, "baslik": "düz " + id_, "basamak": "T2", "girdi": "",
         "kabul_kriterleri": ["a çalışır"], "yazma_alani": ["src/a.py"], "bagimliliklar": []}
    k.update(ek)
    return k


class StatikTestler(unittest.TestCase):
    """node gerekmez."""

    def test_kapi_semaforu_ve_kapi_ajani_yok(self):
        with open(BETIK, encoding="utf-8") as f:
            js = f.read()
        self.assertNotIn("KAPI_ES_ZAMANLI", js)
        self.assertNotIn("phase: 'Kapı'", js)
        self.assertNotIn("phase: 'Ön kontrol'", js)

    def test_erken_test_tdd_kartina_baglidir(self):
        with open(BETIK, encoding="utf-8") as f:
            js = f.read()
        self.assertIn("if (tddKarti(k) && bag.length > 0", js)


@unittest.skipUnless(NODE, NODE_YOK_GEREKCE)
class AkisTestleri(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ork_paralel_")
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
        p = subprocess.run([NODE, self.kosum, BETIK, yol], capture_output=True, env=env, timeout=90)
        self.assertEqual(p.returncode, 0, p.stderr.decode("utf-8", "replace"))
        c = json.loads(p.stdout.decode("utf-8"))
        self.cikti = c
        self.assertEqual([x for x in c["cagrilar"] if x["phase"] in ("Kapı", "Ön kontrol")], [])
        return c["sonuc"]["sonuclar"], c["cagrilar"], c["loglar"]

    @staticmethod
    def adimlar(cagrilar, id_=None):
        def ad(c):
            if c["agentType"] == "orkestra:test-yazari":
                return "test"
            if c["agentType"] == "orkestra:denetci":
                return "denetim"
            return "is"
        return [ad(c) for c in cagrilar if id_ is None or c["id"] == id_]

    # ---- mutlu yol
    def test_mutlu_yol_kapi_ve_on_kontrol_ajani_yok(self):
        s, c, _ = self.kos([kod_karti()])
        self.assertEqual(s[0]["durum"], "onaylandi")
        self.assertEqual(self.adimlar(c), ["test", "is", "denetim"])
        self.assertEqual(len(c), 3)  # eskiden 8 (taban + kontrol, iki kapı, iki mercek ayrı ajan)

    def test_kod_olmayan_kart_davranisi(self):
        s, c, _ = self.kos([duz_kart()])
        self.assertEqual(s[0]["durum"], "onaylandi")
        self.assertEqual(self.adimlar(c), ["is", "denetim"])

    # ---- yeşil geçmez / sınıflama (işçinin is-bitti kapısı)
    def test_yesil_gecmeyince_denetci_yok_duzeltme_turu(self):
        s, c, _ = self.kos([kod_karti()], kartlar={"G-900": {"yesil": [False, True]}})
        self.assertEqual(self.adimlar(c), ["test", "is", "is", "denetim"])
        isler = [x for x in c if x["phase"] == "İş"]
        self.assertTrue(isler[1]["ilk"].endswith("#SUREC:duzeltme"))
        self.assertIn("is-bitti kapısı geçmedi", isler[1]["istem"])
        self.assertEqual(s[0]["durum"], "onaylandi")

    def test_yesil_hep_gecmez_yukselir_denetci_hic_yok(self):
        s, c, _ = self.kos([kod_karti()], kartlar={"G-900": {"yesil": [False] * 20}})
        self.assertNotIn("denetim", self.adimlar(c))
        self.assertEqual([x["agentType"] for x in c if x["phase"] == "İş"],
                         ["orkestra:isci-t2"] * 2 + ["orkestra:isci-t3"] * 2 + ["orkestra:isci-t4"] * 2)
        self.assertEqual(s[0]["durum"], "reddedildi")

    def test_kod_disi_kapi_ihlali_denetciyi_atlar_duzeltme_turu(self):
        ihlal = {"gecti": False, "ihlaller": [{"tur": "kapsam", "ayrinti": "src/b.py"}]}
        s, c, _ = self.kos([duz_kart()], kartlar={"G-901": {"onkontrol": [ihlal]}})
        self.assertEqual(self.adimlar(c), ["is", "is", "denetim"])
        isler = [x for x in c if x["phase"] == "İş"]
        self.assertIn("ön kontrol kapsam", isler[1]["istem"])
        self.assertIn("Ret nedeni: talimat-ihlali", isler[1]["istem"])
        self.assertEqual(s[0]["durum"], "onaylandi")

    def test_yesil_zaman_asimi_kart_duzeltilmeli(self):
        z = {"gecti": False, "cikis_kodu": -1, "ozet": "orkestra: zaman aşımı (1800 sn)"}
        s, c, _ = self.kos([kod_karti()], kartlar={"G-900": {"yesil": [z]}})
        self.assertEqual(s[0]["durum"], "kart-duzeltilmeli")
        self.assertEqual(s[0]["neden"], "kapi-zaman-asimi")
        self.assertEqual(self.adimlar(c), ["test", "is"])

    def test_yesil_cli_hatasi_kart_duzeltilmeli(self):
        h = {"gecti": False, "cikis_kodu": 2, "ozet": "orkestra: test_komutu/test_alani yok"}
        s, c, _ = self.kos([kod_karti()], kartlar={"G-900": {"yesil": [h]}})
        self.assertEqual(s[0]["durum"], "kart-duzeltilmeli")
        self.assertEqual(s[0]["neden"], "kapi-cli-hatasi")
        self.assertEqual(self.adimlar(c), ["test", "is"])

    def test_kirmizi_zaman_asimi_ve_cli_hatasi_siniflamasi(self):
        z = {"gecti": False, "cikis_kodu": -1, "ozet": "zaman aşımı"}
        s, c, _ = self.kos([kod_karti()], kartlar={"G-900": {"kirmizi": [z]}})
        self.assertEqual(s[0]["neden"], "kapi-zaman-asimi")
        self.assertEqual(self.adimlar(c), ["test"])
        h = {"gecti": False, "cikis_kodu": 2, "ozet": "kilit yok"}
        s, c, _ = self.kos([kod_karti()], kartlar={"G-900": {"kirmizi": [h]}})
        self.assertEqual(s[0]["neden"], "kapi-cli-hatasi")

    def test_kirmizi_gecmez_yeniden_deneme_ve_is_acilmaz(self):
        s, c, _ = self.kos([kod_karti()], kartlar={"G-900": {"kirmizi": [False, False, False]}})
        self.assertEqual(s[0]["durum"], "reddedildi")
        self.assertEqual(s[0]["neden"], "kirmizi-teyit")
        self.assertEqual(self.adimlar(c), ["test"] * 3)
        self.assertEqual([x for x in c if x["phase"] == "İş"], [])

    # ---- eşzamanlılık: kapı semaforu kalktı, test yazarları sınırsız
    def test_bagimsiz_kod_kartlari_paralel_test_yazarlari_sinirsiz(self):
        kartlar = [kod_karti("G-910"), kod_karti("G-911"), kod_karti("G-912")]
        s, c, _ = self.kos(kartlar, gecikme={"yazar": 150})
        self.assertEqual([x["durum"] for x in s], ["onaylandi"] * 3)
        self.assertEqual(self.cikti["yazarEnCok"], 3)

    # ---- yazma alanı çakışması: ajan açılmadan sıraya girer (ARK S3)
    def test_yazma_alani_cakisan_kartlar_ayni_anda_acilmaz_sirayla_koşar(self):
        kartlar = [kod_karti("G-920", yazma_alani=["src/ortak.py"]), kod_karti("G-921", yazma_alani=["src/ortak.py"])]
        s, c, _ = self.kos(kartlar, gecikme={"yazar": 150})
        self.assertEqual([x["durum"] for x in s], ["onaylandi"] * 2)
        self.assertEqual(self.cikti["yazarEnCok"], 1)
        self.assertTrue(any("G-921" in l and "çakışıyor" in l for l in self.cikti["loglar"]))

    def test_glob_oneki_ust_dizin_cakisir_kardes_dizin_cakismaz(self):
        kartlar = [kod_karti("G-930", yazma_alani=["src/**"]), kod_karti("G-931", yazma_alani=["src/a/x.py"]),
                   kod_karti("G-932", yazma_alani=["docs/y.md"])]
        s, c, _ = self.kos(kartlar, gecikme={"yazar": 150})
        self.assertEqual([x["durum"] for x in s], ["onaylandi"] * 3)
        loglar = [l for l in self.cikti["loglar"] if "çakışıyor" in l]
        self.assertTrue(any("G-931" in l for l in loglar))
        self.assertFalse(any("G-932" in l for l in loglar))

    def test_alani_olmayan_kart_sirayi_beklemez(self):
        kartlar = [duz_kart("G-940", yazma_alani=[]), duz_kart("G-941", yazma_alani=[])]
        self.kos(kartlar)
        self.assertFalse(any("çakışıyor" in l for l in self.cikti["loglar"]))

    def test_kirmizi_hata_yolunda_diger_kartlar_etkilenmez(self):
        kartlar = [kod_karti("G-910"), kod_karti("G-911"), kod_karti("G-912")]
        s, _, _ = self.kos(kartlar, kartlar={"G-910": {"kirmizi": [False] * 5}, "G-911": {"kirmizi": [False] * 5}})
        self.assertEqual([x["durum"] for x in s], ["reddedildi", "reddedildi", "onaylandi"])

    # ---- erken test
    def test_bagimli_kartin_test_yazari_bagimlilik_denetimi_bitmeden_baslar_isci_sonra(self):
        a, b = kod_karti("G-920"), kod_karti("G-921", bagimliliklar=["G-920"])
        s, c, _ = self.kos([a, b], gecikme={"denetim": {"G-920": 150}})
        self.assertEqual([x["durum"] for x in s], ["onaylandi", "onaylandi"])
        a_den = [x for x in c if x["id"] == "G-920" and x["agentType"] == "orkestra:denetci"]
        b_yazar = [x for x in c if x["id"] == "G-921" and x["agentType"] == "orkestra:test-yazari"][0]
        b_isci = [x for x in c if x["id"] == "G-921" and x["phase"] == "İş"][0]
        self.assertLess(b_yazar["bas"], min(x["son"] for x in a_den))
        self.assertGreater(b_isci["bas"], max(x["son"] for x in a_den))

    def test_bagimli_kartin_kirmizi_kapisi_test_yazarinda_beklemeden_biter(self):
        a, b = kod_karti("G-920"), kod_karti("G-921", bagimliliklar=["G-920"])
        _, c, _ = self.kos([a, b], gecikme={"denetim": {"G-920": 150}})
        b_yazar = [x for x in c if x["id"] == "G-921" and x["agentType"] == "orkestra:test-yazari"][0]
        a_den_son = max(x["son"] for x in c if x["id"] == "G-920" and x["agentType"] == "orkestra:denetci")
        self.assertIn("Kırmızı teyidi is-bitti koşar", b_yazar["istem"])  # kırmızı kapı test yazarının is-bitti'sinde
        self.assertLess(b_yazar["son"], a_den_son)

    def test_tdd_false_bagimli_kart_erken_test_yok_bagimliligi_bekler(self):
        a, b = kod_karti("G-920"), kod_karti("G-921", bagimliliklar=["G-920"], tdd=False)
        s, c, _ = self.kos([a, b], gecikme={"denetim": {"G-920": 150}})
        self.assertEqual([x["durum"] for x in s], ["onaylandi", "onaylandi"])
        self.assertEqual([x for x in c if x["id"] == "G-921" and x["agentType"] == "orkestra:test-yazari"], [])
        a_den_son = max(x["son"] for x in c if x["id"] == "G-920" and x["agentType"] == "orkestra:denetci")
        b_ilk = min(x["bas"] for x in c if x["id"] == "G-921")
        self.assertGreater(b_ilk, a_den_son)

    def test_bagimlilik_reddedilirse_kart_atlandi_testler_yazildi_kilitli_notu(self):
        a, b = kod_karti("G-920"), kod_karti("G-921", bagimliliklar=["G-920"])
        s, c, loglar = self.kos([a, b], kartlar={"G-920": {"yesil": [False] * 20}}, gecikme={"isci": {"G-920": 20}})
        self.assertEqual(s[0]["durum"], "reddedildi")
        self.assertEqual(s[1]["durum"], "atlandi")
        self.assertIn("G-920", s[1].get("neden", ""))
        self.assertEqual(self.adimlar(c, "G-921"), ["test"])  # işçi hiç açılmadı
        self.assertTrue(any("testler yazıldı, kilitli" in m and "G-921" in m for m in loglar), loglar)

    def test_kod_olmayan_bagimli_kart_bagimliligi_bekler(self):
        a, b = duz_kart("G-930"), duz_kart("G-931", bagimliliklar=["G-930"])
        s, c, _ = self.kos([a, b], gecikme={"denetim": {"G-930": 100}})
        self.assertEqual([x["durum"] for x in s], ["onaylandi", "onaylandi"])
        a_den_son = max(x["son"] for x in c if x["id"] == "G-930" and x["agentType"] == "orkestra:denetci")
        b_ilk = min(x["bas"] for x in c if x["id"] == "G-931")
        self.assertGreater(b_ilk, a_den_son)

    def test_bagimlilik_donguleri_korunur(self):
        a = kod_karti("G-940", bagimliliklar=["G-941"])
        b = kod_karti("G-941", bagimliliklar=["G-940"])
        s, c, _ = self.kos([a, b])  # asılı kalırsa subprocess timeout'u yakalar
        self.assertNotIn("onaylandi", [x["durum"] for x in s])
        self.assertEqual([x for x in c if x["phase"] == "İş"], [])


if __name__ == "__main__":
    unittest.main()
