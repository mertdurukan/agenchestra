"""G-055: on_kontrol test koşusu tekilleştirme (PAR-1). Geçici projede; test_kos sayaçla sarılır, ağ/model yok."""
import contextlib
import datetime
import io
import json
import os
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import on_kontrol as OK  # noqa: E402

KIMLIK = "t.py::test_a"
YENI = "t.py::test_yeni"


def _zaman(saniye_fark=0.0):
    t = datetime.datetime.now().astimezone() + datetime.timedelta(seconds=saniye_fark)
    return t.isoformat(timespec="seconds")


class Tekil(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = self.tmp.name
        self.gd = os.path.join(self.p, ".claude", "orkestra", "gorevler")
        os.makedirs(self.gd)
        os.makedirs(os.path.join(self.p, "src"))
        self.cikti = os.path.join(self.p, "src", "x.txt")
        with open(self.cikti, "wb") as f:
            f.write(b"a\n")
        self.sayac = 0
        self.fake = {"cikis": 0, "basarisiz": []}
        self._orijinal = OK.test_kos

        def sahte(komut, cwd):
            self.sayac += 1
            return dict(self.fake)

        OK.test_kos = sahte

    def tearDown(self):
        OK.test_kos = self._orijinal
        self.tmp.cleanup()

    def kart(self, kosular=None, sinif="kod", **ek):
        k = {"id": "G-1", "sinif": sinif, "yazma_alani": ["src/*.txt"], "test_komutu": "x", "test_kosulari": kosular or []}
        k.update(ek)
        with open(os.path.join(self.gd, "G-1.json"), "w", encoding="utf-8") as f:
            json.dump(k, f)

    def kos(self, *args):
        cikti = io.StringIO()
        with contextlib.redirect_stdout(cikti):
            kod = OK.main(list(args) + ["--proje", self.p])
        return kod, json.loads(cikti.getvalue())

    def yesil(self, gecti=True, zaman=None, asama="yesil"):
        return {"zaman": zaman or _zaman(), "sira": 2, "asama": asama, "cikis_kodu": 0 if gecti else 1,
                "gecti": gecti, "dusenler": [], "kok": self.p.replace("\\", "/")}

    def kirmizi(self, dusenler=(KIMLIK,), gecti=True):
        r = {"zaman": _zaman(), "sira": 1, "asama": "kirmizi", "cikis_kodu": 1, "gecti": gecti}
        if dusenler is not None:
            r["dusenler"] = list(dusenler)
        return r

    def taban_kos(self, taban_basarisiz=()):
        """Taban dosyasını doğrudan yazar (taban alt komutundan bağımsız); sayaç etkilenmez."""
        kayit = {"zaman": _zaman(), "dosyalar": {OK._norm(self.cikti): OK.dosya_ozeti(self.cikti)},
                 "test": {"cikis": 1 if taban_basarisiz else 0, "basarisiz": list(taban_basarisiz)}}
        with open(os.path.join(self.gd, "G-1.onkontrol.json"), "w", encoding="utf-8") as f:
            json.dump(kayit, f)

    def mtime(self, fark):
        t = datetime.datetime.now().timestamp() + fark
        os.utime(self.cikti, (t, t))

    def kontrol(self):
        return self.kos("kontrol", "G-1", "--ciktilar", "src/x.txt")

    # ---- kriter 1: geçerli yeşil kayıt -> koşmaz
    def test_gecerli_yesil_kosmaz(self):
        self.kart([self.kirmizi(), self.yesil()])
        self.taban_kos()
        self.mtime(-100)
        kod, s = self.kontrol()
        self.assertEqual(self.sayac, 0)
        self.assertEqual(s["test_kaynagi"], "yesil-kaydi")
        self.assertEqual(kod, 0)
        self.assertTrue(s["gecti"])

    def test_yesil_kaydi_yeni_hatayi_yok_sayar(self):
        # test_kos çağrılsaydı yeni hata dönerdi; yeşil kayıt varken ihlal üretilmemeli
        self.fake = {"cikis": 1, "basarisiz": [YENI]}
        self.kart([self.yesil()])
        self.taban_kos([KIMLIK])
        self.mtime(-100)
        kod, s = self.kontrol()
        self.assertEqual(self.sayac, 0)
        self.assertEqual(s["test_kaynagi"], "yesil-kaydi")
        self.assertNotIn("yeni-test-hatasi", [i["tur"] for i in s["ihlaller"]])
        self.assertEqual(kod, 0)

    def test_yesil_kaydi_digger_ihlalleri_kaldirmaz(self):
        # yeşil kayıt yalnız test koşusunu atlatır; kapsam ihlali yine yakalanır
        self.kart([self.yesil()])
        self.taban_kos()
        self.mtime(-100)
        kod, s = self.kos("kontrol", "G-1", "--ciktilar", "src/x.txt,dis/y.txt")
        self.assertEqual(self.sayac, 0)
        self.assertEqual(s["test_kaynagi"], "yesil-kaydi")
        self.assertEqual([i["tur"] for i in s["ihlaller"]], ["kapsam"])
        self.assertEqual(kod, 4)

    # ---- kriter 2: bayat / geçmemiş / yok -> koşar
    def test_bayat_yesil_kosar(self):
        self.kart([self.yesil()])
        self.taban_kos()
        self.mtime(+100)  # çıktı kayıttan sonra değişti
        kod, s = self.kontrol()
        self.assertEqual(self.sayac, 1)
        self.assertEqual(s["test_kaynagi"], "kosu")

    def test_bayat_yesilde_yeni_hata_yakalanir(self):
        self.fake = {"cikis": 1, "basarisiz": [YENI]}
        self.kart([self.yesil()])
        self.taban_kos()
        self.mtime(+100)
        kod, s = self.kontrol()
        self.assertEqual(self.sayac, 1)
        self.assertEqual([i["tur"] for i in s["ihlaller"]], ["yeni-test-hatasi"])
        self.assertEqual(kod, 4)

    def test_gecmeyen_yesil_kosar(self):
        self.kart([self.yesil(gecti=False)])
        self.taban_kos()
        self.mtime(-100)
        _, s = self.kontrol()
        self.assertEqual(self.sayac, 1)
        self.assertEqual(s["test_kaynagi"], "kosu")

    def test_yesil_kaydi_yok_kosar(self):
        self.kart([])
        self.taban_kos()
        self.mtime(-100)
        _, s = self.kontrol()
        self.assertEqual(self.sayac, 1)
        self.assertEqual(s["test_kaynagi"], "kosu")

    def test_yalniz_kirmizi_kaydi_yesil_sayilmaz(self):
        self.kart([self.kirmizi()])
        self.taban_kos()
        self.mtime(-100)
        _, s = self.kontrol()
        self.assertEqual(self.sayac, 1)
        self.assertEqual(s["test_kaynagi"], "kosu")

    def test_en_son_yesil_gecmediyse_eski_gecen_yetmez(self):
        self.kart([self.yesil(zaman=_zaman(-50)), self.yesil(gecti=False, zaman=_zaman(-10))])
        self.taban_kos()
        self.mtime(-100)
        _, s = self.kontrol()
        self.assertEqual(self.sayac, 1)
        self.assertEqual(s["test_kaynagi"], "kosu")

    # ---- kriter 3: taban kırmızı kaydından
    def test_taban_kirmizi_kaydindan_kosmaz(self):
        self.kart([self.kirmizi((KIMLIK, "t.py::test_b"))])
        kod, _ = self.kos("taban", "G-1")
        self.assertEqual(kod, 0)
        self.assertEqual(self.sayac, 0)
        with open(os.path.join(self.gd, "G-1.onkontrol.json"), encoding="utf-8") as f:
            kayit = json.load(f)
        self.assertEqual(kayit["test"]["basarisiz"], [KIMLIK, "t.py::test_b"])

    def test_taban_kayit_yoksa_kosar(self):
        self.fake = {"cikis": 1, "basarisiz": ["t.py::test_z"]}
        self.kart([])
        self.kos("taban", "G-1")
        self.assertEqual(self.sayac, 1)
        with open(os.path.join(self.gd, "G-1.onkontrol.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["test"]["basarisiz"], ["t.py::test_z"])

    def test_taban_kimliksiz_kirmizi_kosar(self):
        for dusenler in (None, []):
            with self.subTest(dusenler=dusenler):
                self.sayac = 0
                self.kart([self.kirmizi(dusenler)])
                self.kos("taban", "G-1")
                self.assertEqual(self.sayac, 1)

    def test_taban_kod_olmayan_kartta_kosar(self):
        self.kart([self.kirmizi()], sinif="analitik")
        self.kos("taban", "G-1")
        self.assertEqual(self.sayac, 1)

    def test_taban_gecmeyen_kirmizi_kosar(self):
        self.kart([self.kirmizi(gecti=False)])
        self.kos("taban", "G-1")
        self.assertEqual(self.sayac, 1)

    def test_taban_yesil_kaydi_kirmizi_sayilmaz(self):
        self.kart([self.yesil()])
        self.kos("taban", "G-1")
        self.assertEqual(self.sayac, 1)

    def test_kirmizi_tabanli_kontrol_onceden_dusen_ve_yeni(self):
        # taban kırmızı kaydından, kontrol yeşil kaydı olmadığından koşar: eski düşen onceden_dusen, yeni düşen ihlal
        self.kart([self.kirmizi()])
        self.kos("taban", "G-1")
        self.assertEqual(self.sayac, 0)
        self.fake = {"cikis": 1, "basarisiz": [KIMLIK, YENI]}
        _, s = self.kontrol()
        self.assertEqual(self.sayac, 1)
        self.assertEqual(s["test_kaynagi"], "kosu")
        self.assertEqual(s["onceden_dusen"], [KIMLIK])
        self.assertEqual([i["ayrinti"] for i in s["ihlaller"]], [[YENI]])


if __name__ == "__main__":
    unittest.main()
