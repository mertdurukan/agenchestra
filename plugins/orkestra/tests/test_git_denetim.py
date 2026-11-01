"""Git denetimi (I-325): dal sınıflaması, stash/commitsiz sayımı ve kapanış uyarısı (pozitif ve negatif)."""
import os
import subprocess
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import dal_temizle  # noqa: E402
import git_denetim  # noqa: E402


def git(yol, *a):
    return subprocess.run(["git", "-C", yol, "-c", "user.name=t", "-c", "user.email=t@t", *a],
                          capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()


def commit(yol, ad):
    with open(os.path.join(yol, ad), "w", encoding="utf-8") as f:
        f.write(ad)
    git(yol, "add", ".")
    git(yol, "commit", "-q", "-m", ad)


class GitDenetim(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()
        self.uzak = os.path.join(self.t, "uzak.git")
        self.depo = os.path.join(self.t, "depo")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", self.uzak], check=True)
        subprocess.run(["git", "clone", "-q", self.uzak, self.depo], check=True, capture_output=True)
        git(self.depo, "checkout", "-q", "-B", "main")
        commit(self.depo, "a")
        git(self.depo, "push", "-q", "origin", "main")

    def test_temiz_depoda_uyari_yok(self):
        self.assertEqual(git_denetim.uyari(self.depo), "")
        self.assertEqual(dal_temizle.kapanis(self.depo), "")

    def test_yedeksiz_dal_ve_uyari(self):
        git(self.depo, "checkout", "-q", "-b", "kuyruk")
        commit(self.depo, "b")
        commit(self.depo, "c")
        git(self.depo, "checkout", "-q", "main")
        d = {x["ad"]: x for x in git_denetim.tara(self.depo)["yerel"]}
        self.assertEqual((d["kuyruk"]["durum"], d["kuyruk"]["adet"]), ("yedeksiz", 2))
        self.assertEqual(d["main"]["durum"], "uzakta")
        self.assertIn("kuyruk (2 commit, uzakta kopyası yok)", git_denetim.uyari(self.depo))
        self.assertIn("kuyruk", dal_temizle.kapanis(self.depo))

    def test_gonderilmemis_dal_ayrilir(self):
        git(self.depo, "checkout", "-q", "-b", "ozellik")
        commit(self.depo, "b")
        git(self.depo, "push", "-q", "origin", "ozellik")
        commit(self.depo, "c")
        d = {x["ad"]: x for x in git_denetim.tara(self.depo)["yerel"]}
        self.assertEqual((d["ozellik"]["durum"], d["ozellik"]["adet"]), ("gonderilmemis", 1))

    def test_uzak_birlesmis_ve_benzersiz(self):
        git(self.depo, "checkout", "-q", "-b", "eski")
        git(self.depo, "push", "-q", "origin", "eski")
        git(self.depo, "checkout", "-q", "-b", "yeni")
        commit(self.depo, "b")
        git(self.depo, "push", "-q", "origin", "yeni")
        git(self.depo, "checkout", "-q", "main")
        u = {x["ad"]: x for x in git_denetim.tara(self.depo)["uzak"]}
        self.assertEqual(u["origin/eski"]["durum"], "birlesmis")
        self.assertEqual((u["origin/yeni"]["durum"], u["origin/yeni"]["adet"]), ("benzersiz", 1))
        self.assertNotIn("origin/main", u)

    def test_stash_ve_commitsiz_sayilir(self):
        with open(os.path.join(self.depo, "a"), "w", encoding="utf-8") as f:
            f.write("degisti")
        git(self.depo, "stash", "push", "-q", "-m", "x")
        with open(os.path.join(self.depo, "yeni"), "w", encoding="utf-8") as f:
            f.write("y")
        t = git_denetim.tara(self.depo)
        self.assertEqual((t["stash"], t["commitsiz"]), (1, 1))
        self.assertIn("stash: 1", git_denetim.rapor(self.depo))

    def test_uzaksiz_depoda_uyari_yok(self):
        yerel = os.path.join(self.t, "yerel")
        subprocess.run(["git", "init", "-q", "-b", "main", yerel], check=True)
        commit(yerel, "a")
        git(yerel, "checkout", "-q", "-b", "dal")
        commit(yerel, "b")
        self.assertEqual(git_denetim.uyari(yerel), "")

    def test_depo_olmayan_yer_istisna_atmaz(self):
        self.assertEqual(git_denetim.uyari(self.t), "")
        self.assertEqual(git_denetim.tara(self.t)["yerel"], [])


if __name__ == "__main__":
    unittest.main()
