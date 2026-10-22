"""SessionEnd'de yazılan oturum satırı yalnız bağlı (linked) worktree'de commit'lenir (ana ağaçta commit atılmaz).
`py -3.13 -m pytest plugins/orkestra/tests/test_oturum_satiri_commit.py`
"""
import os
import subprocess
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import hook  # noqa: E402


def git(cwd, *args):
    r = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)}: {r.stderr or r.stdout}")
    return r.stdout


class OturumSatiriCommit(unittest.TestCase):
    def setUp(self):
        self.taban = os.path.realpath(tempfile.mkdtemp(prefix="ork_osc_"))
        self.ana = os.path.join(self.taban, "depo")
        os.makedirs(self.ana)
        git(self.ana, "init", "-q", "-b", "main")
        git(self.ana, "config", "user.name", "Test")
        git(self.ana, "config", "user.email", "test@example.invalid")
        self.rel = os.path.join("is", "oturumlar.md")
        os.makedirs(os.path.join(self.ana, "is"))
        self.yaz(self.ana, "# Oturumlar\n")
        git(self.ana, "add", "-A")
        git(self.ana, "commit", "-q", "-m", "ilk")
        self.agac = os.path.join(self.taban, "agac")
        git(self.ana, "worktree", "add", "-q", "-b", "claude/x", self.agac)
        git(self.agac, "config", "user.name", "Test")
        git(self.agac, "config", "user.email", "test@example.invalid")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.taban, ignore_errors=True)

    def yaz(self, kok, satir):
        with open(os.path.join(kok, self.rel), "a", encoding="utf-8", newline="\n") as f:
            f.write(satir)

    def durum(self, kok):
        return git(kok, "status", "--porcelain", "--", self.rel).strip()

    def test_bagli_worktree_te_commitlenir(self):
        self.yaz(self.agac, "- satir\n")
        self.assertTrue(self.durum(self.agac))
        hook._oturum_agacinda_commitle(os.path.join(self.agac, self.rel))
        self.assertEqual(self.durum(self.agac), "")
        self.assertIn("oturum satırı", git(self.agac, "log", "-1", "--format=%s"))

    def test_ana_agacta_commitlenmez(self):
        self.yaz(self.ana, "- satir\n")
        hook._oturum_agacinda_commitle(os.path.join(self.ana, self.rel))
        self.assertTrue(self.durum(self.ana))

    def test_baska_dosyaya_dokunmaz(self):
        self.yaz(self.agac, "- satir\n")
        with open(os.path.join(self.agac, "baska.txt"), "w", encoding="utf-8") as f:
            f.write("x")
        git(self.agac, "add", "baska.txt")
        hook._oturum_agacinda_commitle(os.path.join(self.agac, self.rel))
        self.assertIn("A  baska.txt", git(self.agac, "status", "--porcelain"))


if __name__ == "__main__":
    unittest.main()
