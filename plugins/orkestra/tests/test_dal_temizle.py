"""Artık dal temizliği (I-201): birleşmiş dal adaydır, birleşmemiş ve worktree'de açık dal korunur, ihlal kipi yedekleyip siler."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import dal_temizle  # noqa: E402


def git(yol, *a):
    return subprocess.run(["git", "-C", yol, "-c", "user.name=t", "-c", "user.email=t@t", *a],
                          capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()


def commit(yol, ad):
    with open(os.path.join(yol, ad), "w", encoding="utf-8") as f:
        f.write(ad)
    git(yol, "add", ".")
    git(yol, "commit", "-q", "-m", ad)


class DalTemizleTest(unittest.TestCase):
    def setUp(self):
        self.k = tempfile.mkdtemp()
        self.depo = os.path.join(self.k, "depo")
        os.makedirs(self.depo)
        git(self.depo, "init", "-q", "-b", "main")
        commit(self.depo, "a")
        git(self.depo, "branch", "birlesmis")                    # main ile aynı uç: birleşmiş
        git(self.depo, "checkout", "-q", "-b", "yeni")
        commit(self.depo, "b")                                   # main'de olmayan commit
        git(self.depo, "checkout", "-q", "main")
        git(self.depo, "branch", "oturum")                       # çağıran oturumun dalı
        wt = os.path.join(self.k, "wt")
        git(self.depo, "worktree", "add", "-q", "-b", "acik", wt)  # worktree'de açık, birleşmiş
        self.wt = wt

    def tearDown(self):
        shutil.rmtree(self.k, ignore_errors=True)

    def test_adaylar(self):
        a = dal_temizle.adaylar(self.depo, "oturum")
        self.assertEqual(a["aday"], ["birlesmis"])
        self.assertEqual(a["birlesmemis"], ["yeni"])

    def test_golge_silmez(self):
        s = dal_temizle.temizle(self.depo, "oturum", "golge")
        self.assertEqual(s["aday"], ["birlesmis"])
        self.assertEqual(s["silinen"], [])
        self.assertIn("birlesmis", git(self.depo, "branch", "--list", "birlesmis"))

    def test_ihlal_yedekler_ve_siler(self):
        s = dal_temizle.temizle(self.depo, "oturum", "ihlal")
        self.assertEqual(s["silinen"], ["birlesmis"])
        self.assertTrue(os.path.isfile(s["bundle"]))
        self.assertEqual(git(self.depo, "branch", "--list", "birlesmis"), "")
        self.assertNotEqual(git(self.depo, "branch", "--list", "yeni"), "")      # birleşmemiş durur
        self.assertNotEqual(git(self.depo, "branch", "--list", "oturum"), "")    # oturum dalı durur
        self.assertNotEqual(git(self.depo, "branch", "--list", "acik"), "")      # worktree'de açık durur
        self.assertIn("birlesmis", git(self.depo, "bundle", "list-heads", s["bundle"]))

    def test_hata_istisna_firlatmaz(self):
        s = dal_temizle.temizle(os.path.join(self.k, "yok"), "", "ihlal")
        self.assertEqual(s["silinen"], [])

    def test_kapali(self):
        os.environ["ORKESTRA_DAL_TEMIZLE"] = "0"
        try:
            self.assertIsNone(dal_temizle.calistir(self.depo))
        finally:
            del os.environ["ORKESTRA_DAL_TEMIZLE"]


if __name__ == "__main__":
    unittest.main()
