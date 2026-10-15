"""is_yonlendirme: konu skoru, yönlendirme kararı, kapanış/bayat tespiti (G-062).

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
        for ad in ("tokenler", "skorla", "yonlendir", "kapanis_adaylari"):
            self.assertTrue(callable(getattr(iy, ad, None)), ad)


class TokenlerTest(unittest.TestCase):
    def test_turkce_yonlendirme_ortak_kok(self):
        a = iy.tokenler("İş yönlendirmesini düzelt")
        b = iy.tokenler("is yonlendirme")
        self.assertTrue(a & b, (a, b))

    def test_buyuk_i_noktali_kucuk_harfe(self):
        self.assertEqual(iy.tokenler("İSTANBUL"), iy.tokenler("istanbul"))
        self.assertEqual(iy.tokenler("ISTANBUL"), iy.tokenler("istanbul"))

    def test_bes_karakter_kirpma(self):
        self.assertEqual(iy.tokenler("planlama"), {"planl"})
        self.assertEqual(iy.tokenler("planlama"), iy.tokenler("planlanan"))

    def test_kume_doner(self):
        self.assertIsInstance(iy.tokenler("kalibrasyon envanter"), (set, frozenset))
        self.assertEqual(len(iy.tokenler("kalibrasyon envanter")), 2)

    def test_kisa_sozcukler_atilir(self):
        self.assertEqual(iy.tokenler("ve ab x 1 12"), set())

    def test_durak_sozcukler_atilir(self):
        self.assertEqual(iy.tokenler("bir için bu ve"), set())

    def test_durak_ve_anlamli_karisik(self):
        self.assertEqual(iy.tokenler("bir kalibrasyon için"), iy.tokenler("kalibrasyon"))

    def test_noktalama_ayirir_rakam_korunur(self):
        t = iy.tokenler("rapor-2026, sevkiyat/plan!")
        self.assertIn("2026", t)
        self.assertNotIn("rapor-", t)
        self.assertTrue({"rapor", "sevki"} <= t)

    def test_bos_girdi(self):
        self.assertEqual(iy.tokenler(""), set())
        self.assertEqual(iy.tokenler("   ,.! "), set())


class SkorlaTest(unittest.TestCase):
    def test_baslik_iki_puan(self):
        r = dict(iy.skorla("kalibrasyon", [is_("A", "Kalibrasyon raporu")]))
        self.assertEqual(r["A"], 2)

    def test_klasor_iki_puan(self):
        r = dict(iy.skorla("kalibrasyon", [is_("A", "Başka konu", "001-kalibrasyon")]))
        self.assertEqual(r["A"], 2)

    def test_todo_bir_puan(self):
        r = dict(iy.skorla("kalibrasyon", [is_("A", "Başka konu", "", ["kalibrasyon yap"])]))
        self.assertEqual(r["A"], 1)

    def test_birlesik_puan(self):
        isler = [is_("A", "Kalibrasyon envanter", "", ["muhasebe kapat"])]
        r = dict(iy.skorla("kalibrasyon envanter muhasebe", isler))
        self.assertEqual(r["A"], 5)

    def test_eslesme_yok_sifir(self):
        r = dict(iy.skorla("sevkiyat", [is_("A", "Kalibrasyon")]))
        self.assertEqual(r["A"], 0)

    def test_azalan_sira(self):
        isler = [is_("A", "Kalibrasyon"),
                 is_("B", "Kalibrasyon envanter muhasebe"),
                 is_("C", "Sevkiyat")]
        r = iy.skorla("kalibrasyon envanter muhasebe", isler)
        self.assertEqual([i for i, _ in r], ["B", "A", "C"])
        self.assertEqual([s for _, s in r], [6, 2, 0])

    def test_bos_listeler(self):
        self.assertEqual(iy.skorla("kalibrasyon", []), [])
        r = iy.skorla("", [is_("A", "Kalibrasyon")])
        self.assertEqual(dict(r)["A"], 0)


class YonlendirTest(unittest.TestCase):
    def setUp(self):
        self.A = is_("A-1", "Kalibrasyon envanter muhasebe sevkiyat")
        self.B = is_("B-1", "Fiyatlandirma")

    def test_bagli_yok_eslesme_yok_yeni(self):
        r = iy.yonlendir("tamamen alakasiz vitrin", [self.A, self.B], None)
        self.assertEqual(r["tur"], "yeni")
        self.assertIsNone(r["is"])
        self.assertIn("orkestra is ac", r["satir"])

    def test_bos_is_listesi_yeni(self):
        r = iy.yonlendir("kalibrasyon", [], None)
        self.assertEqual(r["tur"], "yeni")

    def test_dusuk_skor_bagli_yok_yeni(self):
        # tek başlık eşleşmesi = 2 puan (<3)
        r = iy.yonlendir("kalibrasyon", [self.A], None)
        self.assertEqual(r["tur"], "yeni")

    def test_bagli_yok_eslesme_3_ve_ustu_degistir(self):
        r = iy.yonlendir("kalibrasyon envanter", [self.B, self.A], None)
        self.assertEqual(r["tur"], "degistir")
        self.assertEqual(r["is"], "A-1")
        self.assertIn("orkestra is devam A-1", r["satir"])

    def test_bagli_dusuk_baska_yuksek_degistir(self):
        r = iy.yonlendir("kalibrasyon envanter muhasebe", [self.A, self.B], "B-1")
        self.assertEqual(r["tur"], "degistir")
        self.assertEqual(r["is"], "A-1")
        self.assertIn("orkestra is devam A-1", r["satir"])

    def test_bagli_zaten_en_iyi_none(self):
        r = iy.yonlendir("kalibrasyon envanter muhasebe", [self.A, self.B], "A-1")
        self.assertIsNone(r)

    def test_fark_3ten_az_none(self):
        # A=6, C=4 -> fark 2
        c = is_("C-1", "Kalibrasyon envanter")
        r = iy.yonlendir("kalibrasyon envanter muhasebe", [self.A, c], "C-1")
        self.assertIsNone(r)

    def test_bagli_yarisindan_az_degilse_none(self):
        # en iyi 8, bagli 4: fark 4 (>=3) ama bagli en iyinin yarisindan az degil
        a = is_("A-2", "Kalibrasyon envanter muhasebe sevkiyat")
        c = is_("C-2", "Kalibrasyon envanter")
        r = iy.yonlendir("kalibrasyon envanter muhasebe sevkiyat", [a, c], "C-2")
        self.assertIsNone(r)

    def test_bagli_yarisindan_az_ve_fark_yeterli_degistir(self):
        # en iyi 8, bagli 2: yarisindan az ve fark 6
        a = is_("A-2", "Kalibrasyon envanter muhasebe sevkiyat")
        c = is_("C-2", "Kalibrasyon")
        r = iy.yonlendir("kalibrasyon envanter muhasebe sevkiyat", [a, c], "C-2")
        self.assertEqual(r["tur"], "degistir")
        self.assertEqual(r["is"], "A-2")

    def test_eslesme_yok_bagli_var_none(self):
        r = iy.yonlendir("tamamen alakasiz vitrin", [self.A, self.B], "B-1")
        self.assertIsNone(r)

    def test_en_iyi_skor_3ten_az_bagli_var_none(self):
        # A=2 (<3), bagli B=0: rahatsiz etme
        r = iy.yonlendir("kalibrasyon", [self.A, self.B], "B-1")
        self.assertIsNone(r)

    def test_bos_istek_istisna_yok(self):
        for bagli in (None, "B-1"):
            r = iy.yonlendir("", [self.A, self.B], bagli)
            self.assertIn(None if r is None else r["tur"], (None, "yeni"))


class SatirTest(unittest.TestCase):
    def _kontrol(self, r):
        self.assertIsNotNone(r)
        s = r["satir"]
        self.assertIsInstance(s, str)
        self.assertNotIn("\n", s)
        self.assertNotIn("\r", s)
        self.assertLessEqual(len(s), 200)
        self.assertTrue("orkestra is devam" in s or "orkestra is ac" in s, s)

    def test_yeni_satiri(self):
        r = iy.yonlendir("yeni konu", [is_("A", "Kalibrasyon")], None)
        self._kontrol(r)
        self.assertIn("orkestra is ac", r["satir"])

    def test_degistir_satiri_id_icerir(self):
        isler = [is_("A-9", "Kalibrasyon envanter muhasebe")]
        r = iy.yonlendir("kalibrasyon envanter", isler, None)
        self._kontrol(r)
        self.assertIn("orkestra is devam A-9", r["satir"])

    def test_cok_uzun_baslik_ve_satir_sinirli(self):
        uzun = "Kalibrasyon envanter muhasebe " * 40 + "\n ikinci satır"
        isler = [is_("A-7", uzun, "klasor " * 50)]
        r = iy.yonlendir("kalibrasyon envanter muhasebe", isler, None)
        self._kontrol(r)

    def test_cok_uzun_istek_yeni_satir_sinirli(self):
        r = iy.yonlendir("alakasiz\nsatir " * 100, [is_("A", "Kalibrasyon")], None)
        self._kontrol(r)


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
