"""workflows/calistir.js PAR-2/4/5 testleri: kapı birleştirme, kapı semaforu, erken test.

Betik sahte `agent/parallel/log/args` ile node'da koşturulur (test_calistir_akisi.py ile aynı yöntem);
node yoksa gerekçeli skip edilir. node yolu `ORKESTRA_NODE` ile de verilebilir.

Sahte kapı ajanı, gerçek ajanın istemdeki talimatı izlemesini taklit eder: `--asama X` komutu geçerse ve istemde
`on_kontrol.py` varsa ön kontrol sonucunu da döner; kapı geçmediyse on_kontrol=null döner. Dönüş hem düz alanlarla
(gecti/cikis_kodu/ozet) hem {yesil|kirmizi: {...}, on_kontrol} biçimiyle verilir; böylece testler dönüş zarfının
ayrıntısına değil, çağrı sayısı/sırası/eşzamanlılık davranışına bağlıdır.
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
NODE = os.environ.get("ORKESTRA_NODE") or shutil.which("node")
NODE_YOK_GEREKCE = ("node bulunamadı (PATH'te yok, ORKESTRA_NODE boş): calistir.js paralel/kapı senaryoları "
                    "koşturulamadı; statik testler yine de koşar.")

KOSUM_JS = r"""
const fs = require('fs')
const [betikYolu, senaryoYolu] = process.argv.slice(-2)
const kaynak = fs.readFileSync(betikYolu, 'utf8').replace(/^export\s+const\s+meta/m, 'const meta')
const sen = JSON.parse(fs.readFileSync(senaryoYolu, 'utf8'))
const kart = sen.kartlar || {}
const cagrilar = [], loglar = [], sayac = {}
let seq = 0, kapiAktif = 0, kapiEnCok = 0, yazarAktif = 0, yazarEnCok = 0
const bekle = ms => new Promise(r => setTimeout(r, ms || 0))
function sira(anahtar, liste, varsayilan) {
  const i = (sayac[anahtar] = (sayac[anahtar] === undefined ? -1 : sayac[anahtar]) + 1)
  return Array.isArray(liste) && i < liste.length ? liste[i] : varsayilan
}
function kapiSonucu(g) {
  if (g === true || g === false) return { gecti: g, cikis_kodu: g ? 0 : 4, ozet: 'kapi ' + g, cikti_kuyrugu: '' }
  return Object.assign({ gecti: false, cikis_kodu: 4, ozet: '', cikti_kuyrugu: '' }, g)
}
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
    return bitir({ ozet: 'test yazıldı', ciktilar: ['t.py'], kanit: ['-'] })
  }
  if (o.phase === 'Ön kontrol') {
    await bekle((sen.gecikme || {}).onkontrol)
    return bitir(/taban$/.test(o.label) ? { gecti: true, ihlaller: [] } : sira('onk:' + id, ks.onkontrol, { gecti: true, ihlaller: [] }))
  }
  if (o.phase === 'Kapı') {
    kapiAktif++; kapiEnCok = Math.max(kapiEnCok, kapiAktif)
    await bekle((sen.gecikme || {}).kapi)
    kapiAktif--
    const m = /--asama (kirmizi|yesil)/.exec(istem)
    const asama = m ? m[1] : 'yesil'
    const k = kapiSonucu(sira(asama + ':' + id, ks[asama], true))
    const onkVar = /on_kontrol\.py/.test(istem)
    const onk = k.gecti && onkVar
      ? (asama === 'kirmizi' ? { gecti: true, ihlaller: [] } : sira('onk:' + id, ks.onkontrol, { gecti: true, ihlaller: [] }))
      : null
    return bitir(Object.assign({}, k, { [asama]: k, yesil: k, on_kontrol: onk }))
  }
  if (o.agentType === 'orkestra:denetci') {
    await bekle(((sen.gecikme || {}).denetim || {})[id])
    return bitir(sira('den:' + id, ks.denetim, { karar: 'onay', bulgular: [] }))
  }
  await bekle(((sen.gecikme || {}).isci || {})[id])
  return bitir({ ozet: 'iş yapıldı', ciktilar: ['x.py'], kanit: ['-'] })
}
async function parallel(fns) { return Promise.all(fns.map(f => f())) }
function log(m) { loglar.push(String(m)) }
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor
new AsyncFunction('agent', 'parallel', 'log', 'args', kaynak)(agent, parallel, log, { gorevler: sen.gorevler })
  .then(sonuc => process.stdout.write(JSON.stringify({ sonuc, cagrilar, loglar, kapiEnCok, yazarEnCok })))
  .catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(1) })
"""


def kod_karti(id_="G-900", **ek):
    k = {"id": id_, "baslik": "örnek " + id_, "basamak": "T2", "girdi": "", "sinif": "kod",
         "kabul_kriterleri": ["a çalışır", "b hata verir"], "yazma_alani": ["src/a.py"],
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

    def test_semafor_sabiti_varsayilan_iki(self):
        with open(BETIK, encoding="utf-8") as f:
            js = f.read()
        self.assertRegex(js, r"KAPI_ES_ZAMANLI\s*=\s*2\b")


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
        return c["sonuc"]["sonuclar"], c["cagrilar"], c["loglar"]

    @staticmethod
    def adimlar(cagrilar, id_=None):
        def ad(c):
            if c["agentType"] == "orkestra:test-yazari":
                return "test"
            if c["phase"] == "Kapı":
                return "kapi-" + re.search(r"--asama (\w+)", c["istem"]).group(1)
            if c["phase"] == "Ön kontrol":
                return "onk"
            if c["agentType"] == "orkestra:denetci":
                return "denetim"
            return "is"
        return [ad(c) for c in cagrilar if id_ is None or c["id"] == id_]

    # ---- Kriter 1: mutlu yol
    def test_mutlu_yol_ayri_on_kontrol_cagrisi_yok_ve_iki_eksik_cagri(self):
        s, c, _ = self.kos([kod_karti()])
        self.assertEqual(s[0]["durum"], "onaylandi")
        self.assertEqual([x for x in c if x["phase"] == "Ön kontrol"], [])
        self.assertEqual(self.adimlar(c),
                         ["test", "kapi-kirmizi", "is", "kapi-yesil", "denetim", "denetim"])
        self.assertEqual(len(c), 6)  # bugün 8 (taban + kontrol ayrı ajan): 2 eksik

    def test_kapi_istemleri_test_kos_sonra_on_kontrol_icerir(self):
        _, c, _ = self.kos([kod_karti()])
        kapilar = [x for x in c if x["phase"] == "Kapı"]
        self.assertEqual(len(kapilar), 2)
        kir, yes = kapilar
        self.assertIn("--asama kirmizi", kir["istem"])
        self.assertIn("--asama yesil", yes["istem"])
        for k, alt in ((kir, "taban"), (yes, "kontrol")):
            self.assertIn("on_kontrol.py", k["istem"])
            self.assertRegex(k["istem"], r"on_kontrol\.py[^\n]*\b%s\b" % alt)
            self.assertLess(k["istem"].index("test-kos"), k["istem"].index("on_kontrol.py"))
        self.assertIn("x.py", yes["istem"])  # kontrol, işçinin bildirdiği çıktılarla koşar (--ciktilar)
        self.assertEqual(kir["agentType"], "orkestra:isci-t1")
        self.assertEqual(yes["agentType"], "orkestra:isci-t1")

    def test_kod_olmayan_kart_davranisi_ayni(self):
        s, c, _ = self.kos([duz_kart()])
        self.assertEqual(s[0]["durum"], "onaylandi")
        self.assertEqual(self.adimlar(c), ["onk", "is", "onk", "denetim"])
        self.assertEqual([x for x in c if x["phase"] == "Kapı"], [])
        self.assertIn("taban", c[0]["label"])
        self.assertIn("kontrol", c[2]["label"])

    # ---- Kriter 2: yeşil geçmez / on_kontrol / sınıflama
    def test_yesil_gecmeyince_denetci_yok_ayri_on_kontrol_yok_duzeltme_turu(self):
        s, c, _ = self.kos([kod_karti()], kartlar={"G-900": {"yesil": [False, True]}})
        self.assertEqual(self.adimlar(c),
                         ["test", "kapi-kirmizi", "is", "kapi-yesil", "is", "kapi-yesil", "denetim", "denetim"])
        isler = [x for x in c if x["phase"] == "İş"]
        self.assertTrue(isler[1]["ilk"].endswith("#SUREC:duzeltme"))
        self.assertIn("Yeşil test kapısı geçmedi", isler[1]["istem"])
        self.assertEqual(s[0]["durum"], "onaylandi")

    def test_yesil_hep_gecmez_yukselir_denetci_hic_yok(self):
        s, c, _ = self.kos([kod_karti()], kartlar={"G-900": {"yesil": [False] * 20}})
        self.assertNotIn("denetim", self.adimlar(c))
        self.assertEqual([x["agentType"] for x in c if x["phase"] == "İş"],
                         ["orkestra:isci-t2"] * 2 + ["orkestra:isci-t3"] * 2 + ["orkestra:isci-t4"] * 2)
        self.assertEqual(s[0]["durum"], "reddedildi")

    def test_yesil_gecer_on_kontrol_ihlali_denetciyi_atlar_duzeltme_turu(self):
        ihlal = {"gecti": False, "ihlaller": [{"tur": "kapsam", "ayrinti": "src/b.py"}]}
        s, c, _ = self.kos([kod_karti()], kartlar={"G-900": {"onkontrol": [ihlal]}})
        self.assertEqual(self.adimlar(c),
                         ["test", "kapi-kirmizi", "is", "kapi-yesil", "is", "kapi-yesil", "denetim", "denetim"])
        isler = [x for x in c if x["phase"] == "İş"]
        self.assertIn("ön kontrol kapsam", isler[1]["istem"])
        self.assertEqual(s[0]["durum"], "onaylandi")

    def test_yesil_zaman_asimi_kart_duzeltilmeli(self):
        z = {"gecti": False, "cikis_kodu": -1, "ozet": "orkestra: zaman aşımı (1800 sn)"}
        s, c, _ = self.kos([kod_karti()], kartlar={"G-900": {"yesil": [z]}})
        self.assertEqual(s[0]["durum"], "kart-duzeltilmeli")
        self.assertEqual(s[0]["neden"], "kapi-zaman-asimi")
        self.assertEqual(self.adimlar(c), ["test", "kapi-kirmizi", "is", "kapi-yesil"])

    def test_yesil_cli_hatasi_kart_duzeltilmeli(self):
        h = {"gecti": False, "cikis_kodu": 2, "ozet": "orkestra: test_komutu/test_alani yok"}
        s, c, _ = self.kos([kod_karti()], kartlar={"G-900": {"yesil": [h]}})
        self.assertEqual(s[0]["durum"], "kart-duzeltilmeli")
        self.assertEqual(s[0]["neden"], "kapi-cli-hatasi")
        self.assertEqual(self.adimlar(c), ["test", "kapi-kirmizi", "is", "kapi-yesil"])

    def test_kirmizi_zaman_asimi_ve_cli_hatasi_siniflamasi(self):
        z = {"gecti": False, "cikis_kodu": -1, "ozet": "zaman aşımı"}
        s, c, _ = self.kos([kod_karti()], kartlar={"G-900": {"kirmizi": [z]}})
        self.assertEqual(s[0]["neden"], "kapi-zaman-asimi")
        self.assertEqual(self.adimlar(c), ["test", "kapi-kirmizi"])
        h = {"gecti": False, "cikis_kodu": 2, "ozet": "kilit yok"}
        s, c, _ = self.kos([kod_karti()], kartlar={"G-900": {"kirmizi": [h]}})
        self.assertEqual(s[0]["neden"], "kapi-cli-hatasi")

    def test_kirmizi_gecmez_yeniden_deneme_bugunku_gibi_ve_is_acilmaz(self):
        s, c, _ = self.kos([kod_karti()], kartlar={"G-900": {"kirmizi": [False, False, False]}})
        self.assertEqual(s[0]["durum"], "reddedildi")
        self.assertEqual(s[0]["neden"], "kirmizi-teyit")
        self.assertEqual(self.adimlar(c), ["test", "kapi-kirmizi"] * 3)
        self.assertEqual([x for x in c if x["phase"] in ("İş", "Ön kontrol")], [])

    # ---- Kriter 3: semafor
    def test_uc_bagimsiz_kod_kartinda_en_cok_iki_es_zamanli_kapi(self):
        kartlar = [kod_karti("G-910"), kod_karti("G-911"), kod_karti("G-912")]
        s, c, _ = self.kos(kartlar, gecikme={"kapi": 150})
        self.assertEqual([x["durum"] for x in s], ["onaylandi"] * 3)
        self.assertLessEqual(self.cikti["kapiEnCok"], 2)
        self.assertEqual(self.cikti["kapiEnCok"], 2)  # sınır gerçekten kullanılıyor (tam seri değil)
        kapilar = [x for x in c if x["phase"] == "Kapı"]
        self.assertEqual(len(kapilar), 6)

    def test_semafor_yalniz_kapi_cagrilarini_sinirlar(self):
        kartlar = [kod_karti("G-910"), kod_karti("G-911"), kod_karti("G-912")]
        self.kos(kartlar, gecikme={"yazar": 150, "kapi": 20})
        self.assertEqual(self.cikti["yazarEnCok"], 3)  # test yazarları sınırsız
        self.assertLessEqual(self.cikti["kapiEnCok"], 2)

    def test_semafor_hata_yolunda_kilitlenmez(self):
        kartlar = [kod_karti("G-910"), kod_karti("G-911"), kod_karti("G-912")]
        s, _, _ = self.kos(kartlar, gecikme={"kapi": 30},
                           kartlar={"G-910": {"kirmizi": [False] * 5}, "G-911": {"kirmizi": [False] * 5}})
        self.assertEqual([x["durum"] for x in s], ["reddedildi", "reddedildi", "onaylandi"])
        self.assertLessEqual(self.cikti["kapiEnCok"], 2)

    # ---- Kriter 4: erken test
    def test_bagimli_kartin_test_yazari_bagimlilik_denetimi_bitmeden_baslar_isci_sonra(self):
        a, b = kod_karti("G-920"), kod_karti("G-921", bagimliliklar=["G-920"])
        s, c, _ = self.kos([a, b], gecikme={"denetim": {"G-920": 150}, "kapi": 10})
        self.assertEqual([x["durum"] for x in s], ["onaylandi", "onaylandi"])
        a_den = [x for x in c if x["id"] == "G-920" and x["agentType"] == "orkestra:denetci"]
        b_yazar = [x for x in c if x["id"] == "G-921" and x["agentType"] == "orkestra:test-yazari"][0]
        b_isci = [x for x in c if x["id"] == "G-921" and x["phase"] == "İş"][0]
        self.assertLess(b_yazar["bas"], min(x["son"] for x in a_den))
        self.assertGreater(b_isci["bas"], max(x["son"] for x in a_den))

    def test_bagimli_kartin_kirmizi_kapisi_da_beklemeden_kosar(self):
        a, b = kod_karti("G-920"), kod_karti("G-921", bagimliliklar=["G-920"])
        _, c, _ = self.kos([a, b], gecikme={"denetim": {"G-920": 150}, "kapi": 10})
        b_kir = [x for x in c if x["id"] == "G-921" and x["phase"] == "Kapı"][0]
        a_den_son = max(x["son"] for x in c if x["id"] == "G-920" and x["agentType"] == "orkestra:denetci")
        self.assertIn("--asama kirmizi", b_kir["istem"])
        self.assertLess(b_kir["bas"], a_den_son)

    def test_bagimlilik_reddedilirse_kart_atlandi_testler_yazildi_kilitli_notu(self):
        a, b = kod_karti("G-920"), kod_karti("G-921", bagimliliklar=["G-920"])
        s, c, loglar = self.kos([a, b], kartlar={"G-920": {"yesil": [False] * 20}}, gecikme={"isci": {"G-920": 20}})
        self.assertEqual(s[0]["durum"], "reddedildi")
        self.assertEqual(s[1]["durum"], "atlandi")
        self.assertIn("G-920", s[1].get("neden", ""))
        self.assertEqual(self.adimlar(c, "G-921"), ["test", "kapi-kirmizi"])  # işçi hiç açılmadı
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
