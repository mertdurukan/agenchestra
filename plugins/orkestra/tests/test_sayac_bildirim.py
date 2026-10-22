"""Tekrar sayacı. `python -m pytest plugins/orkestra/tests/test_sayac_bildirim.py -q`

5. tekrarda ve her 5'in katında bildirim gider; metin toplam sayıyı içerir; aynı eşik iki kez bildirilmez.
Gerçek PowerShell çalışmaz; gonder() yerine sahte kullanılır.
"""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import bildirim  # noqa: E402
import sayac  # noqa: E402


class SayacTesti(unittest.TestCase):
    def setUp(self):
        self.sd = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.sd, True)

    def test_5_ve_10da_bildirim(self):
        with mock.patch.object(bildirim, "gonder", return_value=True) as g:
            for _ in range(4):
                sayac.artir(self.sd, "docx donusum")
            g.assert_not_called()
            sayac.artir(self.sd, "docx donusum")
            self.assertEqual(g.call_count, 1)
            self.assertIn("toplam 5", g.call_args[0][1])
            for _ in range(4):
                sayac.artir(self.sd, "docx donusum")
            self.assertEqual(g.call_count, 1)
            self.assertEqual(sayac.artir(self.sd, "docx donusum"), 10)
            self.assertEqual(g.call_count, 2)
            self.assertIn("toplam 10", g.call_args[0][1])

    def test_anahtarlar_ayri_sayilir(self):
        with mock.patch.object(bildirim, "gonder", return_value=True) as g:
            for _ in range(3):
                sayac.artir(self.sd, "a")
                sayac.artir(self.sd, "b")
            g.assert_not_called()

    def test_anahtar_normallesir(self):
        self.assertEqual(sayac.anahtar("Isci-T2", "  Rapor   Yaz "), "isci-t2 | rapor yaz")


if __name__ == "__main__":
    unittest.main()
