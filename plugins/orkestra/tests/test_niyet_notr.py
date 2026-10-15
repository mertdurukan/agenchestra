"""G-095: bekleme nedeni çıkarılamayan tur 'sen' değil nötr durum; soru içeren tur 'sen'. Panel nötrü 'Seni bekliyor'a katmaz.

`py -3.13 -m pytest plugins/orkestra/tests/test_niyet_notr.py -q -p no:cacheprovider`
"""
import json
import os
import re
import sys
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import niyet  # noqa: E402
from test_kapanis_rozeti import KapanisTemel  # noqa: E402


class BeklemeIsareti(unittest.TestCase):
    def test_sonuclu_mesaj_bos(self):
        self.assertEqual(niyet.bekleme_nedeni(None, 0, "Dosyalar güncellendi. Testler geçti."), "")

    def test_soru_dolu(self):
        self.assertEqual(niyet.bekleme_nedeni(None, 0, "Hazır. Commit atılsın mı?"), "Commit atılsın mı?")

    def test_onay_bekleyen_cumle_dolu(self):
        self.assertIn("onayını bekliyorum", niyet.bekleme_nedeni(None, 0, "Plan hazır, onayını bekliyorum."))


class GorunumNotr(KapanisTemel):
    def test_bekleme_yok_notr(self):
        s = self._gorunum([(60, "istek", {"metin": "iş"}), (50, "tur", {"bekleme_yok": True})])
        self.assertEqual(s["bekleyen"], "notr")
        self.assertIsNone(s["bekleme"])

    def test_soru_varsa_sen(self):
        s = self._gorunum([(60, "istek", {"metin": "iş"}), (50, "tur", {"bekleme": "Devam edeyim mi?"})])
        self.assertEqual(s["bekleyen"], "sen")
        self.assertEqual(s["bekleme"], "Devam edeyim mi?")

    def test_eski_kayit_sen_kalir(self):
        s = self._gorunum([(60, "istek", {"metin": "iş"}), (50, "tur", {})])
        self.assertEqual(s["bekleyen"], "sen")

    def test_yeni_istek_notru_siler(self):
        s = self._gorunum([(60, "tur", {"bekleme_yok": True}), (2, "istek", {"metin": "devam"})])
        self.assertEqual(s["bekleyen"], "claude")


class IslerHtmlNotr(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(KOK, "assets", "isler.js"), encoding="utf-8") as f:  # sayfa betiği ayrı dosyada
            self.html = f.read()

    def test_notr_tanimli_ve_sakin(self):
        self.assertRegex(self.html, r"k === 'notr' \? \{ ad: '[^']+', renk: 'var\(--neutral\)' \}")
        self.assertRegex(self.html, r"BEKLEYEN_SIRA = \{[^}]*notr")

    def test_sayac_yalniz_sen(self):
        self.assertRegex(self.html, r"say\.sen \? `\$\{say\.sen\} seni bekliyor`")
        self.assertNotRegex(self.html, r"say\.notr[^;\n]*seni bekliyor")

    def test_nort_sen_karti_degil(self):
        govde = self.html[self.html.index("function sohbetKarti(r)"):self.html.index("function sohbetCiz()")]
        self.assertRegex(govde, r"const sen = r\.bekleyen === 'sen'")

    def test_simdi_html_notr_bilmez(self):
        metin = ""
        for ad in ("simdi.html", "simdi.js"):  # sayfa betiği ayrı dosyada
            with open(os.path.join(KOK, "assets", ad), encoding="utf-8") as f:
                metin += f.read()
        self.assertNotIn("bekleme", metin.replace("beklemeden", ""))


if __name__ == "__main__":
    unittest.main()
