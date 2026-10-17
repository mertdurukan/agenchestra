"""atomik_yaz başarısızlıkta .tmp_* bırakmaz; tmp_temizle yalnız eski .tmp_* dosyalarını siler."""
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import ork_lib as L  # noqa: E402


class TmpTemizleTest(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.d = self._t.name

    def _tmp(self):
        return [a for a in os.listdir(self.d) if a.startswith(".tmp_")]

    def test_basarili_yazim_tmp_birakmaz(self):
        L.atomik_yaz(os.path.join(self.d, "a.json"), "{}")
        self.assertEqual(self._tmp(), [])

    def test_replace_hatasi_tmp_birakir_mi_hayir(self):
        with mock.patch("os.replace", side_effect=OSError("disk")):
            with self.assertRaises(OSError):
                L.atomik_yaz(os.path.join(self.d, "a.json"), "{}")
        self.assertEqual(self._tmp(), [])

    def test_yalniz_eski_tmp_silinir(self):
        eski, yeni, baska = (os.path.join(self.d, a) for a in (".tmp_eski", ".tmp_yeni", "kalir.json"))
        for y in (eski, yeni, baska):
            open(y, "w").close()
        gecmis = time.time() - 7200
        os.utime(eski, (gecmis, gecmis))
        os.utime(baska, (gecmis, gecmis))
        self.assertEqual(L.tmp_temizle(self.d), 1)
        self.assertEqual(sorted(os.listdir(self.d)), [".tmp_yeni", "kalir.json"])

    def test_olmayan_dizin_hata_vermez(self):
        self.assertEqual(L.tmp_temizle(os.path.join(self.d, "yok")), 0)


if __name__ == "__main__":
    unittest.main()
