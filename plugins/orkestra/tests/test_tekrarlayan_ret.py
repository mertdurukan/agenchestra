"""calistir.js tekrarlayan-ret kuralı testleri.

`python -m unittest discover -s plugins/orkestra/tests -p test_tekrarlayan_ret.py -v`

- Saf fonksiyonlar (retImzasi, ayniRet) betik metninden çıkarılıp node ile sınanır.
- Akış: test_calistir_akisi.py'deki sahte çalışma zamanı (KOSUM_JS) ile yurut() koşturulur.
node yoksa (PATH / ORKESTRA_NODE) açık gerekçeyle skip edilir.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from test_calistir_akisi import BETIK, KOSUM_JS, NODE, NODE_YOK_GEREKCE, kart, kod_karti

SAF_JS = r"""
const fs = require('fs')
const [betikYolu, girdiYolu] = process.argv.slice(-2)
const js = fs.readFileSync(betikYolu, 'utf8')
const bas = js.indexOf('function retNormalize')
const son = js.indexOf('// ----', bas)
const { retImzasi, ayniRet } = new Function(js.slice(bas, son) + '\nreturn { retImzasi, ayniRet }')()
const vakalar = JSON.parse(fs.readFileSync(girdiYolu, 'utf8'))
process.stdout.write(JSON.stringify(vakalar.map(([a, b]) => ({ ayni: ayniRet(a, b), imza_a: retImzasi(a) }))))
"""


def calistir_node(betik_metni, *argumanlar):
    env = dict(os.environ, ELECTRON_RUN_AS_NODE="1")
    p = subprocess.run([NODE, betik_metni, *argumanlar], capture_output=True, env=env, timeout=60)
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    return json.loads(p.stdout.decode("utf-8"))


def ret(talimat="Kanıtı ekle.", bulgular=("kriter 1 kanıtsız",), **ek):
    return dict({"karar": "ret", "duzeltme_talimati": talimat, "bulgular": list(bulgular)}, **ek)


@unittest.skipUnless(NODE, NODE_YOK_GEREKCE)
class SafFonksiyonTestleri(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ork_tekrar_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def karsilastir(self, *ciftler):
        saf = os.path.join(self.tmp, "saf.js")
        girdi = os.path.join(self.tmp, "girdi.json")
        with open(saf, "w", encoding="utf-8") as f:
            f.write(SAF_JS)
        with open(girdi, "w", encoding="utf-8") as f:
            json.dump(ciftler, f, ensure_ascii=False)
        with open(BETIK, encoding="utf-8") as f:
            self.assertIn("function retNormalize", f.read())
        return calistir_node(saf, BETIK, girdi)

    def test_ayni_ret_ayni(self):
        s, = self.karsilastir([ret(), ret()])
        self.assertTrue(s["ayni"])

    def test_bosluk_buyuk_harf_noktalama_farki_ayni(self):
        a = ret("Kanıtı ekle.", ["Kriter 1 kanıtsız", "sayı tutmuyor"])
        b = ret("  KANITI   ekle!!\n", ["sayı  tutmuyor...", "kriter 1 kanıtsız;"])  # sıra da farklı
        s, = self.karsilastir([a, b])
        self.assertTrue(s["ayni"])

    def test_farkli_talimat_farkli(self):
        s, = self.karsilastir([ret("Kanıtı ekle."), ret("Biçimi düzelt.")])
        self.assertFalse(s["ayni"])

    def test_farkli_bulgu_farkli(self):
        s, = self.karsilastir([ret(bulgular=["kriter 1 kanıtsız"]), ret(bulgular=["kriter 2 kanıtsız"])])
        self.assertFalse(s["ayni"])

    def test_bulgu_sayisi_farki_farkli(self):
        s, = self.karsilastir([ret(bulgular=["a"]), ret(bulgular=["a", "b"])])
        self.assertFalse(s["ayni"])

    def test_yedek_ret_tekrar_sayilmaz(self):
        y = {"duzeltme_talimati": "Denetçi sonuç döndürmedi; işi kanıtlarıyla yeniden sun.", "bulgular": [], "yedek": True}
        s, = self.karsilastir([y, dict(y)])
        self.assertFalse(s["ayni"])
        self.assertIsNone(s["imza_a"])

    def test_yesil_ret_imzasiz(self):
        y = {"duzeltme_talimati": "Yeşil geçmedi.", "bulgular": ["x"], "yesil": True}
        s, = self.karsilastir([y, dict(y)])
        self.assertFalse(s["ayni"])
        self.assertIsNone(s["imza_a"])

    def test_null_ret_tekrar_sayilmaz(self):
        s, = self.karsilastir([None, None])
        self.assertFalse(s["ayni"])


@unittest.skipUnless(NODE, NODE_YOK_GEREKCE)
class AkisTestleri(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ork_tekrar_akis_")
        self.kosum = os.path.join(self.tmp, "kosum.js")
        with open(self.kosum, "w", encoding="utf-8") as f:
            f.write(KOSUM_JS)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def kos(self, gorevler, **senaryo):
        yol = os.path.join(self.tmp, "senaryo.json")
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(dict(senaryo, gorevler=gorevler), f, ensure_ascii=False)
        c = calistir_node(self.kosum, BETIK, yol)
        return c["sonuc"]["sonuclar"][0], c["cagrilar"], c["loglar"]

    def test_ayni_basamakta_iki_ayni_ret_yukseltir_kapanmaz(self):
        s, c, loglar = self.kos([kart()], denetim=[ret(), ret(" KANITI ekle "), {"karar": "onay", "bulgular": []}])
        self.assertEqual(s["durum"], "onaylandi")
        self.assertEqual(s["basamak"], "T3")
        self.assertFalse(any("tekrarlayan-ret" in m for m in loglar))

    def test_yukseltme_sonrasi_ilk_ret_ayniysa_tekrarlayan_ret(self):
        s, c, loglar = self.kos([kart()], denetim=[ret(), ret(), ret(" KANITI ekle! "), ret()])
        self.assertEqual(s["durum"], "reddedildi")
        self.assertEqual(s["neden"], "tekrarlayan-ret")
        self.assertEqual(s["basamak"], "T3")
        self.assertEqual(len([x for x in c if x["phase"] == "İş"]), 3)  # T2, T2, T3; T3'te ikinci tura girilmedi
        self.assertTrue(any("tekrarlayan-ret" in m for m in loglar))

    def test_yukseltme_sonrasi_farkli_ret_akis_surer(self):
        s, c, loglar = self.kos([kart()], denetim=[
            ret(), ret(), ret("Biçimi düzelt.", ["biçim"]), {"karar": "onay", "bulgular": []}])
        self.assertEqual(s["durum"], "onaylandi")
        self.assertEqual(s["basamak"], "T3")
        self.assertFalse(any("tekrarlayan-ret" in m for m in loglar))

    def test_yetenek_yetersiz_yukseltmesinden_sonra_ayni_ret_yakalanir(self):
        r = ret(neden="yetenek-yetersiz")
        s, c, loglar = self.kos([kart()], denetim=[r, r, r])
        self.assertEqual(s["durum"], "reddedildi")
        self.assertEqual(s["neden"], "tekrarlayan-ret")
        self.assertEqual(s["basamak"], "T3")

    def test_yedek_ret_tekrar_sayilmaz(self):
        s, c, loglar = self.kos([kart()], denetim=[None, None, None, None, {"karar": "onay", "bulgular": []}],
                              kart_ajan_tavani=20)  # 5 işçi + 5 denetçi: varsayılan tavan (8) altında kalmaz
        self.assertEqual(s["durum"], "onaylandi")
        self.assertNotEqual(s.get("neden"), "tekrarlayan-ret")
        self.assertFalse(any("tekrarlayan-ret" in m for m in loglar))

    def test_yesil_kapi_ayni_ciktilar_tekrar_sayilmaz(self):
        s, c, loglar = self.kos([kod_karti()], yesil=[False] * 20)
        self.assertNotEqual(s.get("neden"), "tekrarlayan-ret")
        self.assertEqual([x["agentType"] for x in c if x["phase"] == "İş"],
                         ["orkestra:isci-t2"] * 2 + ["orkestra:isci-t3"] * 2 + ["orkestra:isci-t4"] * 2)
        self.assertFalse(any(x["agentType"] == "orkestra:denetci" for x in c))


if __name__ == "__main__":
    unittest.main()
