"""Standartlar kaydı (ADR-0006): liste, proje önceliği, ekle, hata yolları."""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import standart as S  # noqa: E402

ZORUNLU = {"commit", "pr", "dal", "review", "jira_yorum"}


class StandartTemel(unittest.TestCase):
    def setUp(self):
        self.sd = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.sd, ignore_errors=True)

    def test_liste_eklenti_kalibi(self):
        adlar = {a for a, k, _ in S.liste(self.sd) if k == "eklenti"}
        self.assertTrue(ZORUNLU <= adlar)

    def test_commit_on_bir_turu_icerir(self):
        m = S.oku("commit", self.sd)
        for t in ("feat", "fix", "docs", "style", "refactor", "perf", "test", "build", "ci", "chore", "revert"):
            self.assertIn(f"`{t}`", m)

    def test_proje_onceligi(self):
        os.makedirs(os.path.join(self.sd, "standartlar"))
        with open(os.path.join(self.sd, "standartlar", "commit.md"), "w", encoding="utf-8") as f:
            f.write("proje commit")
        self.assertEqual(S.oku("commit", self.sd), "proje commit")
        self.assertIn(("commit", "proje"), [(a, k) for a, k, _ in S.liste(self.sd)])

    def test_ekle_ve_ezmez(self):
        y = S.ekle("sürüm_notu".replace("ü", "u"), self.sd)
        self.assertTrue(os.path.exists(y))
        with self.assertRaises(ValueError):
            S.ekle("surum_notu", self.sd)
        self.assertIn("surum_notu", {a for a, _, _ in S.liste(self.sd)})

    def test_gecersiz_ad(self):
        with self.assertRaises(ValueError):
            S.ekle("../kaçış", self.sd)
        self.assertIsNone(S.yol("../commit", self.sd))
        self.assertIsNone(S.oku("yok_boyle", self.sd))

    def test_sd_yokken_liste(self):
        self.assertTrue(ZORUNLU <= {a for a, _, _ in S.liste(None)})


if __name__ == "__main__":
    unittest.main()
