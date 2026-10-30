"""Yetim iş kaydı (I-223): merkez kayıt silinmiş bir worktree klasörünü gösterir, iş klasörü ana ağaçta durur.

Düzen: <proje>/.claude/orkestra (durum dizini), <proje>/Claude_Orkestrasyon/<ad>/is.json (ana ağaç),
kayıtlı yol <proje>/.claude/worktrees/<wt>/Claude_Orkestrasyon/<ad> (silinmiş).
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

AD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AD, "..", "scripts"))
import is_kaydi as IK  # noqa: E402
import panel  # noqa: E402
import test_cekirdek as TC  # noqa: E402


def _yaz(yol, veri):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False)


def _oku(yol):
    with open(yol, encoding="utf-8") as f:
        return json.load(f)


class Duzen:
    """Geçici proje: ana ağaç klasörleri ve silinmiş worktree yolunu gösteren merkez kayıtlar."""

    def kur(self):
        self.proje = tempfile.mkdtemp(prefix="ork_yetim_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(self.sd)
        self.isler = {}
        return self

    def sil(self):
        shutil.rmtree(self.proje, ignore_errors=True)

    def ana(self, ad):
        return os.path.join(self.proje, "Claude_Orkestrasyon", ad)

    def wt(self, ad, wt="wt1"):
        return os.path.join(self.proje, ".claude", "worktrees", wt, "Claude_Orkestrasyon", ad)

    def is_json(self, klasor, i, baslik, durum="kapandi"):
        _yaz(os.path.join(klasor, "is.json"), {"id": i, "baslik": baslik, "durum": durum, "olusturma": "2026-10-20T10:00:00"})

    def kayit(self, i, klasor, baslik, durum="kapandi"):
        self.isler[i] = {"klasor": klasor, "baslik": baslik, "durum": durum, "olusturma": "2026-10-20T10:00:00"}
        _yaz(os.path.join(self.sd, "isler.json"), {"sayac": 300, "isler": self.isler})

    def merkez(self):
        return _oku(os.path.join(self.sd, "isler.json"))


class Coz(unittest.TestCase):
    def setUp(self):
        self.d = Duzen().kur()

    def tearDown(self):
        self.d.sil()

    def test_coz_gecerli_yol_oldugu_gibi(self):
        k = self.d.ana("102-a")
        self.d.is_json(k, "I-171", "A işi")
        self.d.kayit("I-171", k, "A işi")
        self.assertEqual(IK.klasor_coz(self.d.sd, self.d.isler["I-171"], "I-171"), k)

    def test_coz_worktree_soneki_ana_agaca_baglanir(self):
        self.d.is_json(self.d.ana("102-a"), "I-171", "A işi")
        self.d.kayit("I-171", self.d.wt("102-a"), "A işi")
        self.assertEqual(os.path.normcase(IK.klasor_coz(self.d.sd, self.d.isler["I-171"], "I-171")),
                         os.path.normcase(self.d.ana("102-a")))

    def test_coz_kimlik_uyusmazsa_baglamaz(self):
        self.d.is_json(self.d.ana("102-a"), "I-999", "Başka iş")  # aynı ad, başka kimlik
        self.d.kayit("I-171", self.d.wt("102-a"), "A işi")
        self.assertIsNone(IK.klasor_coz(self.d.sd, self.d.isler["I-171"], "I-171"))

    def test_coz_eslesmesiz_none(self):
        self.d.kayit("I-166", self.d.wt("90-yok"), "Yok olan iş")
        self.assertIsNone(IK.klasor_coz(self.d.sd, self.d.isler["I-166"], "I-166"))

    def test_is_al_yetim_kaydi_onarilmadan_okunur(self):
        self.d.is_json(self.d.ana("102-a"), "I-171", "A işi", "acik")
        self.d.kayit("I-171", self.d.wt("102-a"), "A işi", "acik")
        kayit = IK.is_al(self.d.sd, "I-171")
        self.assertIsNotNone(kayit)
        self.assertEqual(kayit["id"], "I-171")

    def test_is_al_eslesmesiz_none_kalir(self):
        self.d.kayit("I-166", self.d.wt("90-yok"), "Yok olan iş")
        self.assertIsNone(IK.is_al(self.d.sd, "I-166"))

    def test_is_liste_cozulmus_klasoru_verir(self):
        self.d.is_json(self.d.ana("102-a"), "I-171", "A işi")
        self.d.kayit("I-171", self.d.wt("102-a"), "A işi")
        g = IK.is_liste(self.d.sd)[0]
        self.assertEqual(os.path.normcase(g["klasor"]), os.path.normcase(self.d.ana("102-a")))


class Kalici(unittest.TestCase):
    def setUp(self):
        self.d = Duzen().kur()

    def tearDown(self):
        self.d.sil()

    def test_klasor_kalici_cozulmus_yolu_yazar_eskisini_saklar(self):
        self.d.is_json(self.d.ana("102-a"), "I-171", "A işi")
        self.d.kayit("I-171", self.d.wt("102-a"), "A işi")
        yeni = IK.klasor_kalici(self.d.sd, "I-171")
        g = self.d.merkez()["isler"]["I-171"]
        self.assertEqual(os.path.normcase(g["klasor"]), os.path.normcase(self.d.ana("102-a")))
        self.assertEqual(g["klasor_onceki"], self.d.wt("102-a"))
        self.assertEqual(yeni, g["klasor"])
        self.assertIsNone(IK.klasor_kalici(self.d.sd, "I-171"))   # ikinci çağrı değişiklik yapmaz

    def test_klasor_kalici_cozulemeyeni_degistirmez(self):
        self.d.kayit("I-166", self.d.wt("90-yok"), "Yok olan iş")
        self.assertIsNone(IK.klasor_kalici(self.d.sd, "I-166"))
        self.assertEqual(self.d.merkez()["isler"]["I-166"]["klasor"], self.d.wt("90-yok"))


class YetimTara(unittest.TestCase):
    def setUp(self):
        self.d = Duzen().kur()
        d = self.d
        d.is_json(d.ana("102-a"), "I-171", "A işi", "acik")           # sonek ile bağlanır
        d.kayit("I-171", d.wt("102-a"), "A işi", "acik")
        d.is_json(d.ana("110-gercek-ad"), "I-179", "Gerçek ad işi")    # kayıtlı klasör adı yanlış: tarama bağlar
        d.kayit("I-179", d.wt("110-yanlis-ad"), "Gerçek ad işi")
        d.is_json(d.ana("120-b"), "I-164", "Yinelenen iş")             # kendi kimlikli klasörü yok, başlık I-164 ile aynı
        d.kayit("I-163", d.wt("119-b"), "Yinelenen iş")
        d.kayit("I-166", d.wt("90-yok"), "Hiçbir yerde yok")           # eşleşmesiz
        d.is_json(d.ana("130-saglam"), "I-200", "Sağlam iş")           # yetim değil
        d.kayit("I-200", d.ana("130-saglam"), "Sağlam iş")

    def tearDown(self):
        self.d.sil()

    def test_yinelenen_kapsayici_ic_ice_yazilmis(self):
        k = os.path.join(self.d.proje, ".claude", "worktrees", "wt1", "Claude_Orkestrasyon", "Claude_Orkestrasyon", "119-b")
        self.d.kayit("I-174", k, "Yinelenen iş", "acik")   # kapsayıcı iç içe yazılmış; I-164 klasörü ana ağaçta
        r = IK.yetim_onar(self.d.sd)
        self.assertIn("I-174", [x["id"] for x in r["yinelenen"]])

    def test_sinif_sayilari(self):
        r = IK.yetim_onar(self.d.sd)
        self.assertEqual(sorted(x["id"] for x in r["baglanabilir"]), ["I-171", "I-179"])
        self.assertEqual([x["id"] for x in r["yinelenen"]], ["I-163"])
        self.assertEqual([x["id"] for x in r["eslesmesiz"]], ["I-166"])

    def test_kuru_kosu_yazmaz(self):
        once = open(os.path.join(self.d.sd, "isler.json"), "rb").read()
        r = IK.yetim_onar(self.d.sd)
        self.assertFalse(r["yazildi"])
        self.assertEqual(open(os.path.join(self.d.sd, "isler.json"), "rb").read(), once)
        self.assertFalse(os.path.isdir(os.path.join(self.d.sd, "yedek")))

    def test_uygula_yedek_alir_ve_yalniz_baglanabilir_yazar(self):
        r = IK.yetim_onar(self.d.sd, uygula=True)
        self.assertTrue(r["yazildi"])
        self.assertTrue(r["yedek"] and os.path.exists(r["yedek"]))
        m = self.d.merkez()["isler"]
        self.assertEqual(os.path.normcase(m["I-171"]["klasor"]), os.path.normcase(self.d.ana("102-a")))
        self.assertEqual(os.path.normcase(m["I-179"]["klasor"]), os.path.normcase(self.d.ana("110-gercek-ad")))
        self.assertEqual(m["I-163"]["klasor"], self.d.wt("119-b"))   # yinelenen değişmez
        self.assertEqual(m["I-166"]["klasor"], self.d.wt("90-yok"))  # eşleşmesiz değişmez

    def test_ikinci_kosu_baglanabilir_sifir(self):
        IK.yetim_onar(self.d.sd, uygula=True)
        r = IK.yetim_onar(self.d.sd)
        self.assertEqual(r["baglanabilir"], [])
        self.assertEqual(len(r["yinelenen"]), 1)
        self.assertEqual(len(r["eslesmesiz"]), 1)


class Cli(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown
    cli = TC.Cekirdek.cli

    def yetim_kur(self):
        d = Duzen()
        d.proje, d.sd, d.isler = self.proje, self.sd, {}
        d.is_json(d.ana("102-a"), "I-171", "A işi", "acik")
        d.kayit("I-171", d.wt("102-a"), "A işi", "acik")
        d.kayit("I-166", d.wt("90-yok"), "Yok olan iş")
        return d

    def test_onar_yetim_kuru_kosu_siniflari_yazar(self):
        self.yetim_kur()
        r = self.cli("is", "onar", "--yetim")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("bağlanabilir 1", r.stdout)
        self.assertIn("eşleşmesiz 1", r.stdout)

    def test_onar_yetim_uygula_sonra_sifir(self):
        self.yetim_kur()
        self.assertEqual(self.cli("is", "onar", "--yetim", "--uygula").returncode, 0)
        self.assertIn("bağlanabilir 0", self.cli("is", "onar", "--yetim").stdout)

    def test_devam_yetim_kaydi_kalici_onarir(self):
        d = self.yetim_kur()
        r = self.cli("is", "devam", "I-171")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(os.path.normcase(d.merkez()["isler"]["I-171"]["klasor"]), os.path.normcase(d.ana("102-a")))
        self.assertTrue(os.path.exists(os.path.join(d.merkez()["isler"]["I-171"]["klasor"], "is.json")))


class PanelIleti(unittest.TestCase):
    def setUp(self):
        self.d = Duzen().kur()

    def tearDown(self):
        self.d.sil()

    def yanit(self, is_id):
        with mock.patch.object(panel, "_alan_sd", return_value=({"id": "x", "ad": "x", "yol": self.d.proje}, self.d.sd)):
            return panel._teknik_json("x", is_id, None)

    def test_cozulemeyen_kayit_nedeni_ve_komutu_soyler(self):
        self.d.kayit("I-166", self.d.wt("90-yok"), "Yok olan iş")
        y = self.yanit("I-166")
        self.assertEqual(y["kod"], 404)
        self.assertIn("klasörü yok", y["hata"])
        self.assertIn("orkestra is onar --yetim", y["hata"])

    def test_kayit_hic_yoksa_eski_ileti(self):
        _yaz(os.path.join(self.d.sd, "isler.json"), {"sayac": 1, "isler": {}})
        y = self.yanit("I-170")
        self.assertEqual(y["hata"], "İş bulunamadı: I-170")

    def test_cozulebilen_yetim_acilir(self):
        self.d.is_json(self.d.ana("102-a"), "I-171", "A işi", "acik")
        self.d.kayit("I-171", self.d.wt("102-a"), "A işi", "acik")
        self.assertTrue(self.yanit("I-171").get("acik"))


if __name__ == "__main__":
    unittest.main()
