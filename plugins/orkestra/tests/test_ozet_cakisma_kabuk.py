"""I-138 Kart E: ozet.yaz PermissionError'da işaret bırakır (P11); kabuk_kos penceresiz süreç açar (P13)."""
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import ork_lib as L  # noqa: E402
import ozet  # noqa: E402


class OzetCakisma(unittest.TestCase):
    def test_permissionerror_isaret_birakir_sonraki_yazim_siler(self):
        with tempfile.TemporaryDirectory() as sd:
            proje = os.path.join(sd, "proje")
            os.makedirs(proje)
            with mock.patch.object(ozet, "olustur", return_value={"a": 1}), \
                    mock.patch("os.replace", side_effect=PermissionError("kilitli")), \
                    mock.patch("time.sleep"):
                self.assertIsNone(ozet.yaz(sd, proje))
                self.assertIsNone(ozet.yaz(sd, proje))   # ikinci PermissionError de istisna fırlatmaz
            self.assertTrue(os.path.exists(os.path.join(sd, "ozet.json.bekliyor")))
            self.assertFalse(os.path.exists(os.path.join(sd, "ozet_hata.txt")))
            self.assertFalse(os.path.exists(os.path.join(sd, "ozet.json")))
            with mock.patch.object(ozet, "olustur", return_value={"a": 1}):
                self.assertEqual(ozet.yaz(sd, proje), {"a": 1})
            self.assertTrue(os.path.exists(os.path.join(sd, "ozet.json")))
            self.assertFalse(os.path.exists(os.path.join(sd, "ozet.json.bekliyor")))


class KabukKos(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "creationflags yalnız Windows")
    def test_creationflags_penceresiz(self):
        gercek = subprocess.Popen
        gorulen = {}

        def sahte(*a, **k):
            gorulen.update(k)
            return gercek(*a, **k)
        with mock.patch("subprocess.Popen", side_effect=sahte):
            kod, metin, _ = L.kabuk_kos("echo merhaba", os.getcwd(), 30)
        self.assertEqual(kod, 0)
        self.assertEqual(gorulen["creationflags"], subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW)

    def test_zaman_asimi_korunur(self):
        komut = f'"{sys.executable}" -c "import time; time.sleep(30)"'
        kod, metin, sure = L.kabuk_kos(komut, os.getcwd(), 1)
        self.assertEqual(kod, -1)
        self.assertIn("zaman aşımı", metin)
        self.assertLess(sure, 20)


if __name__ == "__main__":
    unittest.main()
