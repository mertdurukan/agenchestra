"""is_yonlendirme: yeni görev satırı, kapanış/bayat tespiti (G-062).

Tüm veri sentetiktir; dosya/ağ yok. Yalnız modül kaynağı statik olarak okunur.
`python -m unittest discover -s plugins/orkestra/tests -p test_is_yonlendirme.py`
"""
import ast
import importlib.util
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODUL_YOLU = os.path.join(KOK, "scripts", "is_yonlendirme.py")

iy = None


def setUpModule():
    global iy
    assert os.path.isfile(MODUL_YOLU), "scripts/is_yonlendirme.py yok"
    spec = importlib.util.spec_from_file_location("is_yonlendirme", MODUL_YOLU)
    iy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(iy)


def is_(id_, baslik, klasor="", todolar=None):
    return {"id": id_, "baslik": baslik, "klasor_adi": klasor,
            "acik_todolar": list(todolar or [])}


class ArayuzTest(unittest.TestCase):
    def test_fonksiyonlar_var(self):
        for ad in ("yonlendir", "kapanis_adaylari"):
            self.assertTrue(callable(getattr(iy, ad, None)), ad)


class YonlendirTest(unittest.TestCase):
    ISLER = [is_("I-1", "Fatura raporlama"), is_("I-2", "Kampanya takvimi")]

    def _kontrol(self, s):
        self.assertIsInstance(s, str)
        self.assertNotIn(chr(10), s)
        self.assertLessEqual(len(s), iy.SATIR_SINIR)
        self.assertIn("orkestra is devam", s)
        self.assertIn("orkestra is ac", s)

    def test_baglisiz_acik_isler_ve_kural(self):
        s = iy.yonlendir(self.ISLER, None)
        self._kontrol(s)
        self.assertIn("bağlı iş yok", s)
        self.assertIn("I-1 Fatura raporlama", s)
        self.assertIn("I-2 Kampanya takvimi", s)

    def test_bagli_is_adi_satirda(self):
        s = iy.yonlendir(self.ISLER, "I-2")
        self._kontrol(s)
        self.assertIn("bağlı iş I-2 Kampanya takvimi", s)

    def test_acik_is_yoksa_yine_yeni_is_kurali(self):
        for girdi in ([], None, "x"):
            s = iy.yonlendir(girdi, None)
            self._kontrol(s)
            self.assertNotIn("Açık işler:", s)

    def test_bozuk_girdi_atlanir(self):
        s = iy.yonlendir([None, 5, {"baslik": "idsiz"}, is_("I-9", "Tek")], None)
        self.assertIn("I-9 Tek", s)
        self.assertNotIn("idsiz", s)

    def test_cok_is_ve_uzun_baslik_sinirli(self):
        isler = [is_("I-%d" % n, "Uzun başlık" + chr(10) + "ikinci satır " * 20) for n in range(20)]
        s = iy.yonlendir(isler, "I-3")
        self._kontrol(s)
        self.assertNotIn("I-10 ", s)


class KapanisTest(unittest.TestCase):
    SIMDI = datetime(2026, 10, 14, 12, 0, 0)

    def _o(self, id_, toplam, biten, acik, son):
        return {"id": id_, "toplam": toplam, "biten": biten, "acik_kart": acik,
                "son_dokunus": son}

    def _iso(self, gun, saat=0):
        return (self.SIMDI - timedelta(days=gun, hours=saat)).isoformat()

    def test_tum_biten_kapat(self):
        r = iy.kapanis_adaylari([self._o("A", 5, 5, 0, self._iso(1))], self.SIMDI)
        self.assertEqual(r["kapat"], ["A"])
        self.assertEqual(r["bayat"], [])

    def test_donus_bicimi(self):
        r = iy.kapanis_adaylari([], self.SIMDI)
        self.assertEqual(r, {"kapat": [], "bayat": []})

    def test_toplam_sifir_kapat_degil(self):
        r = iy.kapanis_adaylari([self._o("A", 0, 0, 0, self._iso(1))], self.SIMDI)
        self.assertNotIn("A", r["kapat"])

    def test_acik_kart_varsa_kapat_degil(self):
        r = iy.kapanis_adaylari([self._o("A", 3, 3, 1, self._iso(1))], self.SIMDI)
        self.assertNotIn("A", r["kapat"])

    def test_biten_eksikse_kapat_degil(self):
        r = iy.kapanis_adaylari([self._o("A", 3, 2, 0, self._iso(1))], self.SIMDI)
        self.assertNotIn("A", r["kapat"])

    def test_14_gun_bayat(self):
        r = iy.kapanis_adaylari([self._o("A", 4, 2, 0, self._iso(14))], self.SIMDI)
        self.assertEqual(r["bayat"], ["A"])
        self.assertEqual(r["kapat"], [])

    def test_14_gunden_eski_bayat(self):
        r = iy.kapanis_adaylari([self._o("A", 4, 2, 1, self._iso(60))], self.SIMDI)
        self.assertEqual(r["bayat"], ["A"])

    def test_13_gun_bayat_degil(self):
        r = iy.kapanis_adaylari([self._o("A", 4, 2, 1, self._iso(13, 23))], self.SIMDI)
        self.assertEqual(r["bayat"], [])

    def test_kapat_adayi_bayat_sayilmaz(self):
        r = iy.kapanis_adaylari([self._o("A", 2, 2, 0, self._iso(40))], self.SIMDI)
        self.assertEqual(r["kapat"], ["A"])
        self.assertEqual(r["bayat"], [])

    def test_son_dokunus_none_bayat_degil(self):
        r = iy.kapanis_adaylari([self._o("A", 4, 2, 1, None)], self.SIMDI)
        self.assertEqual(r["bayat"], [])

    def test_saat_dilimli_tarih(self):
        simdi = datetime(2026, 10, 14, 12, 0, 0, tzinfo=timezone(timedelta(hours=3)))
        eski = (simdi - timedelta(days=20)).isoformat()
        taze = (simdi - timedelta(days=2)).isoformat()
        r = iy.kapanis_adaylari([self._o("E", 4, 2, 1, eski),
                                 self._o("T", 4, 2, 1, taze)], simdi)
        self.assertEqual(r["bayat"], ["E"])

    def test_birden_cok_is_karisik(self):
        ozetler = [self._o("K1", 2, 2, 0, self._iso(1)),
                   self._o("B1", 5, 1, 2, self._iso(30)),
                   self._o("N1", 5, 1, 2, self._iso(1)),
                   self._o("K2", 1, 1, 0, self._iso(20))]
        r = iy.kapanis_adaylari(ozetler, self.SIMDI)
        self.assertEqual(sorted(r["kapat"]), ["K1", "K2"])
        self.assertEqual(r["bayat"], ["B1"])

    def test_bozuk_girdi_istisna_firlatmaz(self):
        iyi = self._o("OK", 2, 2, 0, self._iso(1))
        bozuklar = [
            None, 42, "metin", [], {},
            {"id": "X"},
            {"id": "X", "toplam": "çok", "biten": None, "acik_kart": "?"},
            {"id": "X", "toplam": 3, "biten": 3, "acik_kart": 0, "son_dokunus": "dun gibi"},
            {"id": "X", "toplam": 3, "biten": 1, "acik_kart": 1, "son_dokunus": 12345},
            {"toplam": 3, "biten": 3, "acik_kart": 0},
        ]
        r = iy.kapanis_adaylari(bozuklar + [iyi], self.SIMDI)
        self.assertIn("OK", r["kapat"])
        self.assertIsInstance(r["bayat"], list)

    def test_ozetler_bozuk_tipler(self):
        for girdi in (None, [], "x", 5):
            r = iy.kapanis_adaylari(girdi, self.SIMDI)
            self.assertEqual(r["kapat"], [])
            self.assertEqual(r["bayat"], [])


class StatikTest(unittest.TestCase):
    YASAK_ISIMLER = {"subprocess", "socket", "urllib", "http", "requests", "os",
                     "pathlib", "shutil", "tempfile", "ftplib", "smtplib", "ctypes"}

    def setUp(self):
        with open(MODUL_YOLU, encoding="utf-8") as f:
            self.kaynak = f.read()
        self.agac = ast.parse(self.kaynak)

    def _kok_moduller(self):
        out = set()
        for n in ast.walk(self.agac):
            if isinstance(n, ast.Import):
                out |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
                out.add(n.module.split(".")[0])
        return out

    def test_yalniz_standart_kutuphane(self):
        std = set(sys.stdlib_module_names) | {"__future__"}
        self.assertLessEqual(self._kok_moduller(), std)

    def test_dosya_ag_subprocess_yok(self):
        self.assertFalse(self._kok_moduller() & self.YASAK_ISIMLER)

    def test_open_ve_exec_cagrisi_yok(self):
        for n in ast.walk(self.agac):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                self.assertNotIn(n.func.id, {"open", "exec", "eval", "__import__"})
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                self.assertNotIn(n.func.attr, {"read_text", "write_text", "system", "popen"})


if __name__ == "__main__":
    unittest.main()
