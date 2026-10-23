"""I-059 P5: os.replace geçici PermissionError yeniden deneme + hook_cikti bozuk stdout."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import ork_lib as L  # noqa: E402


class ReplaceDene(unittest.TestCase):
    def test_gecici_izin_hatasindan_sonra_basarir(self):
        cagri = []

        def sahte(a, b):
            cagri.append(1)
            if len(cagri) < 3:
                raise PermissionError("kullanımda")

        with mock.patch.object(L.os, "replace", sahte), mock.patch.object(L.time, "sleep") as uyku:
            L.replace_dene("a", "b")
        self.assertEqual(len(cagri), 3)
        self.assertEqual(uyku.call_count, 2)

    def test_surekli_hata_5_denemeden_sonra_yukselir(self):
        with mock.patch.object(L.os, "replace", side_effect=PermissionError("x")) as r, mock.patch.object(L.time, "sleep"):
            with self.assertRaises(PermissionError):
                L.replace_dene("a", "b")
        self.assertEqual(r.call_count, 5)

    def test_baska_hata_yeniden_denenmez(self):
        with mock.patch.object(L.os, "replace", side_effect=FileNotFoundError("x")) as r:
            with self.assertRaises(FileNotFoundError):
                L.replace_dene("a", "b")
        self.assertEqual(r.call_count, 1)


if __name__ == "__main__":
    unittest.main()


class HookCiktiBozukStdout(unittest.TestCase):
    """041 P5: stdout.flush OSError(22) verirse hook_cikti çıkış kodunu korur, istisna sızdırmaz."""

    class Bozuk:
        def write(self, _):
            pass

        def flush(self):
            raise OSError(22, "Invalid argument")

    def test_flush_hatasi_cikis_kodunu_korur(self):
        for kod in (0, 2):
            with mock.patch.object(L.sys, "stdout", self.Bozuk()), mock.patch.object(L.sys, "stderr", mock.Mock()):
                with self.assertRaises(SystemExit) as c:
                    L.hook_cikti({"a": 1}, kod)
            self.assertEqual(c.exception.code, kod)
