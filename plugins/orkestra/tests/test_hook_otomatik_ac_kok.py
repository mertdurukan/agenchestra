"""I-151 G9: hook._otomatik_ac durum klasörünü L.durum_dizini ile aynı kökte kurar (CLAUDE_PROJECT_DIR > cwd).
`py -3.13 -m pytest plugins/orkestra/tests/test_hook_otomatik_ac_kok.py`
"""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import hook  # noqa: E402
import ork_lib as L  # noqa: E402


class OtomatikAcKok(unittest.TestCase):
    def setUp(self):
        self.kok = tempfile.mkdtemp(prefix="ork_oa_")
        self.proje = os.path.join(self.kok, "proje")
        self.baska = os.path.join(self.kok, "baska")
        os.makedirs(self.proje)
        os.makedirs(self.baska)

    def tearDown(self):
        shutil.rmtree(self.kok, ignore_errors=True)

    def test_ortam_projesi_cwd_den_once_gelir(self):
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": self.proje, "ORKESTRA_OTOMATIK_ACIL": "1"}):
            sd = hook._otomatik_ac({"cwd": self.baska})
        self.assertEqual(os.path.normcase(sd), os.path.normcase(os.path.join(self.proje, ".claude", "orkestra")))
        self.assertFalse(os.path.exists(os.path.join(self.baska, ".claude")))

    def test_kurulan_klasor_durum_dizini_ile_ayni(self):
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": self.proje, "ORKESTRA_OTOMATIK_ACIL": "1"}):
            sd = hook._otomatik_ac({"cwd": self.baska})
            self.assertEqual(os.path.normcase(L.durum_dizini(self.baska)), os.path.normcase(sd))

    def test_ortam_yoksa_cwd_kullanilir(self):
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        env["ORKESTRA_OTOMATIK_ACIL"] = "1"
        with mock.patch.dict(os.environ, env, clear=True):
            sd = hook._otomatik_ac({"cwd": self.baska})
        self.assertEqual(os.path.normcase(sd), os.path.normcase(os.path.join(self.baska, ".claude", "orkestra")))


if __name__ == "__main__":
    unittest.main()
