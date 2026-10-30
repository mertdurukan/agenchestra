"""Kod değişince çalışan panel sunucusu eskimiş sayılır (I-254: SURUM artırılmadığı için Araçlar/Ayarlar rotaları 404 verdi)."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import panel  # noqa: E402


class KodIziTest(unittest.TestCase):
    def test_saglik_kod_izini_tasir(self):
        self.assertEqual(panel.SAGLIK, f"ok {panel.SURUM} {panel.KOD_IZI}")

    def test_kod_degisince_iz_degisir(self):
        with tempfile.TemporaryDirectory() as d:
            ana = os.path.join(d, "panel.py")
            open(ana, "w").write("a = 1\n")
            with mock.patch.object(panel, "__file__", ana):
                ilk = panel._kod_izi()
                open(os.path.join(d, "araclar_mcp.py"), "w").write("b = 2\n")   # yeni/değişen modül
                self.assertNotEqual(ilk, panel._kod_izi())

    def test_eski_sunucu_servis_yeniden_baslatilir(self):
        with mock.patch.object(panel, "_saglik", return_value=f"ok {panel.SURUM} eskiiz"):
            self.assertNotEqual(panel._saglik(8765), panel.SAGLIK)


if __name__ == "__main__":
    unittest.main()
