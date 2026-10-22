"""İzole ortam uyarısı (ADR-0035, P4): kod kartı ana çalışma ağacındaysa uyarı ve gölge kaydı; hiçbir koşulda reddetmez."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import on_kontrol as OK  # noqa: E402


class IzoleOrtam(unittest.TestCase):
    def setUp(self):
        self.kok = tempfile.mkdtemp(prefix="ork_izole_")
        self.addCleanup(shutil.rmtree, self.kok, True)
        subprocess.run(["git", "-C", self.kok, "init", "-q"], check=True, capture_output=True)

    def test_ana_calisma_agacinda_kod_karti_uyarir(self):
        self.assertTrue(OK.izole_degil(self.kok, {"sinif": "kod"}))

    def test_kod_olmayan_kart_uyarmaz(self):
        self.assertFalse(OK.izole_degil(self.kok, {"sinif": "belge"}))

    def test_worktree_uyarmaz(self):
        # worktree'de .git bir DOSYADIR
        os.rmdir(os.path.join(self.kok, ".git")) if not os.listdir(os.path.join(self.kok, ".git")) else shutil.rmtree(os.path.join(self.kok, ".git"))
        with open(os.path.join(self.kok, ".git"), "w", encoding="utf-8") as f:
            f.write("gitdir: /baska/yer\n")
        with mock.patch.object(OK.L, "git_koku", return_value=self.kok):
            self.assertFalse(OK.izole_degil(self.kok, {"sinif": "kod"}))

    def test_git_deposu_degilse_uyarmaz(self):
        with mock.patch.object(OK.L, "git_koku", return_value=None):
            self.assertFalse(OK.izole_degil(self.kok, {"sinif": "kod"}))


if __name__ == "__main__":
    unittest.main()
