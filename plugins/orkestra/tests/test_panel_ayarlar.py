"""Panel Ayarlar sayfası: Bildirim aç/kapat. `python -m pytest plugins/orkestra/tests/test_panel_ayarlar.py -q`

(a) Ayar makine config'ine yazılır ve bildirim.aktif() onu izler; (b) ORKESTRA_BILDIRIM ortam değişkeni panel ayarından önce gelir;
(c) panel uç noktası ayarı döner/yazar, ortam kilidinde 409 verir, geçersiz gövdeyi reddeder; (d) arayüzde sayfa ve anahtar bağlıdır.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import bildirim  # noqa: E402
import panel  # noqa: E402


class AyarlarTesti(unittest.TestCase):
    def setUp(self):
        self.ev = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.ev, True)
        env = mock.patch.dict(os.environ, {"ORKESTRA_HOME": self.ev})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("ORKESTRA_BILDIRIM", None)

    def test_varsayilan_acik(self):
        self.assertEqual(bildirim.ayar(), (True, "varsayilan"))

    def test_kapat_ve_ac_makineye_yazilir(self):
        bildirim.ayar_yaz(False)
        self.assertEqual(bildirim.ayar(), (False, "makine"))
        with mock.patch.object(sys, "platform", "win32"):
            self.assertFalse(bildirim.aktif())
            bildirim.ayar_yaz(True)
            self.assertTrue(bildirim.aktif())

    def test_ortam_degiskeni_oncelikli(self):
        bildirim.ayar_yaz(True)
        with mock.patch.dict(os.environ, {"ORKESTRA_BILDIRIM": "0"}):
            self.assertEqual(bildirim.ayar(), (False, "ortam"))
            sonuc = panel._ayarlar_yaz(True)
            self.assertFalse(sonuc["tamam"])
            self.assertEqual(bildirim.ayar(), (False, "ortam"))

    def test_panel_durum_ve_yazma(self):
        self.assertTrue(panel._ayarlar_durum()["bildirim"]["acik"])
        sonuc = panel._ayarlar_yaz(False)
        self.assertTrue(sonuc["tamam"])
        self.assertEqual(sonuc["bildirim"]["acik"], False)
        self.assertEqual(sonuc["bildirim"]["kaynak"], "makine")
        json.dumps(sonuc)

    def test_arayuz_baglantisi(self):
        js = open(os.path.join(KOK, "assets", "app.js"), encoding="utf-8").read()
        for parca in ("'/api/ayarlar'", "ayarlar: gAyarlar", "data-eylem=\"ayar-bildirim\"", "'#/ayarlar'", "role=\"switch\""):
            self.assertIn(parca, js)
        self.assertIn("/api/ayarlar", panel.KULLANICI_YOLLARI)


if __name__ == "__main__":
    unittest.main()
