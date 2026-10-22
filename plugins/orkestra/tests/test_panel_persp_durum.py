"""Panel durum satırları: /onaylar.json arka_plan (yalnız perspektif ve uygulama), /isler.json arka_plan (sohbet). Todo sayımı panelde yok."""
import os
import sys
import tempfile
import unittest
from unittest import mock

AD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AD, "..", "scripts"))
import ork_lib as L  # noqa: E402
import niyet  # noqa: E402
import onay  # noqa: E402
import panel  # noqa: E402
import perspektif  # noqa: E402


class PerspektifSeridi(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.proje = os.path.join(self.t.name, "proje")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(self.sd)
        self.alan = {"id": "alan-x", "ad": "proje", "yol": self.proje, "orkestra": True, "sohbet": 1, "son": "x"}
        self.yama = mock.patch.object(L, "calisma_alanlari", lambda: [self.alan])
        self.yama.start()

    def tearDown(self):
        self.yama.stop()
        self.t.cleanup()

    def test_arka_plan_bos_iken_liste_bos(self):
        self.assertEqual(panel._onaylar_json("alan-x")["arka_plan"], [])
        self.assertNotIn("todo", panel._isler_json("alan-x"))
        self.assertNotIn("todo", panel._onaylar_json("alan-x"))

    def test_perspektif_ve_uygulama_suruyorsa_listelenir(self):
        with mock.patch.object(perspektif, "durum", return_value={"calisiyor": "2026-10-16T21:00:00+03:00"}), \
                mock.patch.object(onay, "uygulama_durumu", return_value={"baslangic": "2026-10-16T21:05:00+03:00"}):
            bp = panel._onaylar_json("alan-x")["arka_plan"]
        self.assertEqual([x["tur"] for x in bp], ["perspektif", "uygulama"])

    def test_perspektif_esik_durumu_panele_aktarilir(self):
        d = {"son_perspektif": "2026-10-16T20:44:00+03:00", "gun_once": 5, "oturum_sayaci": 133,
             "zamani_geldi": True, "calisiyor": None, "okunmamis_rapor": None}
        with mock.patch.object(perspektif, "durum", return_value=d):
            durum = panel._onaylar_json("alan-x")["perspektif"]["durum"]
        self.assertEqual((durum["gun_once"], durum["oturum_sayaci"], durum["zamani_geldi"]), (5, 133, True))

    def test_arka_plan_isi_suren_sohbet_listelenir(self):
        satir = {"arka_plan": True, "bekleyen": "claude", "ne": "Uzun tarama", "kisa": "abc"}
        diger = {"arka_plan": True, "bekleyen": "beklemede", "ne": "Ölü iş", "kisa": "def"}
        with mock.patch.object(niyet, "gorunum", return_value={"oturumlar": [satir, diger]}):
            self.assertEqual(panel._onaylar_json("alan-x")["arka_plan"], [])  # sohbet görevi Onaylar'da yok
            bp = panel._isler_json("alan-x")["arka_plan"]
        self.assertEqual([x["ad"] for x in bp], ["Uzun tarama"])

    def test_tur_surerken_calisan_sohbet_listelenir(self):
        calisan = {"arka_plan": False, "bekleyen": "claude", "ne": "Sürüyor", "kisa": "ghi"}
        bekleyen = {"arka_plan": False, "bekleyen": "sen", "ne": "Sıra sende", "kisa": "jkl"}
        with mock.patch.object(niyet, "gorunum", return_value={"oturumlar": [calisan, bekleyen]}):
            bp = panel._isler_json("alan-x")["arka_plan"]
        self.assertEqual([x["ad"] for x in bp], ["Sürüyor"])

    def test_sayfa_ogeleri_var(self):
        assets = os.path.join(AD, "..", "assets")
        with open(os.path.join(assets, "onaylar.html"), encoding="utf-8") as f:
            self.assertIn('id="perspDurum"', f.read())
        with open(os.path.join(assets, "onaylar.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn("perspDurumCiz", js)
        self.assertNotIn("yapıldı", js)  # todo sayımı İşler sayfasında
        with open(os.path.join(assets, "isler.html"), encoding="utf-8") as f:
            self.assertIn('id="durumSeridi"', f.read())
        with open(os.path.join(assets, "isler.js"), encoding="utf-8") as f:
            ijs = f.read()
        self.assertIn("durumSeridiCiz", ijs)
        self.assertNotIn("Todo: ${", ijs)  # durum şeridinde todo sayımı yok


if __name__ == "__main__":
    unittest.main()
