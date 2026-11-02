"""I-343: doktor git denetimi bozuk core.fsmonitor değerini yakalar ve geri alınabilir biçimde onarır."""
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import doktor  # noqa: E402
from doktor import Baglam  # noqa: E402


def git(cwd, *a):
    return subprocess.run(["git", "-C", cwd, *a], capture_output=True, text=True, encoding="utf-8")


class FsmonitorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.depo = os.path.join(self.tmp.name, "depo")
        os.mkdir(self.depo)
        git(self.depo, "init", "-q")
        git(self.depo, "config", "user.email", "t@t")
        git(self.depo, "config", "user.name", "t")
        git(self.depo, "commit", "-q", "--allow-empty", "-m", "ilk")

    def k(self, proje=None):
        return doktor.k_git(Baglam(proje=proje or self.depo))

    def test_gecersiz_deger_hata(self):
        git(self.depo, "config", "core.fsmonitor", "core.untrackedcache")
        s = self.k()
        self.assertEqual(s.durum, "hata")
        self.assertIn("core.fsmonitor", s.mesaj)

    def test_boolean_deger_gecerli(self):
        git(self.depo, "config", "core.fsmonitor", "false")
        self.assertEqual(self.k().durum, "gecti")

    def test_calisan_program_degeri_gecerli(self):
        betik = os.path.join(self.tmp.name, "hook.sh")
        with open(betik, "w", newline="\n") as f:
            f.write("#!/bin/sh\nexit 0\n")
        os.chmod(betik, 0o755)
        git(self.depo, "config", "core.fsmonitor", betik.replace("\\", "/"))
        self.assertNotEqual(self.k().durum, "hata")

    def test_worktree_git_dosyasi(self):
        wt = os.path.join(self.tmp.name, "wt")
        git(self.depo, "worktree", "add", "-q", "-b", "yan", wt)
        self.assertTrue(os.path.isfile(os.path.join(wt, ".git")))
        git(self.depo, "config", "core.fsmonitor", "core.untrackedcache")
        self.assertEqual(self.k(wt).durum, "hata")

    def test_onarim_geri_alinir(self):
        git(self.depo, "config", "core.fsmonitor", "core.untrackedcache")
        s = self.k()
        o = doktor.o_git(Baglam(proje=self.depo), s)
        self.assertEqual(o.sinif, "B")
        o.uygula()
        self.assertEqual(git(self.depo, "config", "--get", "core.fsmonitor").returncode, 1)
        self.assertNotIn("cannot spawn", git(self.depo, "status", "--porcelain").stderr)
        self.assertEqual(self.k().durum, "gecti")
        subprocess.run(o.geri_al["argv"], capture_output=True)
        self.assertEqual(git(self.depo, "config", "--get", "core.fsmonitor").stdout.strip(), "core.untrackedcache")


if __name__ == "__main__":
    unittest.main()
