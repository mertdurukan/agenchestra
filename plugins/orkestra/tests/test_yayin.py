"""Yayın klonu: projeye_kur kaynağı ve yayin_kur (GitHub'dan klon, hook yok); klon denetimi test_guncelle.py'de (python -m unittest)."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPO = os.path.dirname(os.path.dirname(KOK))
sys.path.insert(0, os.path.join(KOK, "scripts"))
sys.path.insert(0, os.path.join(DEPO, "araclar"))


def git(yol, *a):
    return subprocess.run(["git", "-C", yol, "-c", "user.name=t", "-c", "user.email=t@t", *a],
                          capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()


def yaz(yol, metin):
    with open(yol, "w", encoding="utf-8") as f:
        f.write(metin)


class Yayin(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp(prefix="ork_yayin_")

    def tearDown(self):
        shutil.rmtree(self.t, ignore_errors=True)

    def test_projeye_kur_kaynak_yayin_klonundan(self):
        import projeye_kur as P
        self.assertNotEqual(P.YAYIN, P.DEPO.replace("\\", "/"))
        self.assertTrue(P.VARSAYILAN_YAYIN.endswith("Claude_Orkestrasyon/plugin_yayin"))
        proje = os.path.join(self.t, "proje")
        os.makedirs(proje)
        eski = P.YAYIN
        P.YAYIN = "Z:/yayin"
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                P.ayar_birlestir(proje, True, False)
        finally:
            P.YAYIN = eski
        with open(os.path.join(proje, ".claude", "settings.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["extraKnownMarketplaces"][P.MARKET]["source"]["path"], "Z:/yayin")

    def test_yayin_kur_hook_yazmaz_ve_klonu_githubdan_kurar(self):
        import yayin_kur as Y
        self.assertFalse(os.path.exists(os.path.join(DEPO, "araclar", "git_hooklar")))
        self.assertFalse(hasattr(Y, "hook_yaz"))
        self.assertEqual(Y.varsayilan_yayin(), __import__("projeye_kur").VARSAYILAN_YAYIN)
        # GitHub'ı temsil eden uzak depo (github_adresi taklit edilir; gerçek ağ kullanılmaz)
        dev = os.path.join(self.t, "dev")
        os.makedirs(dev)
        git(dev, "init", "-q", "-b", "main")
        yaz(os.path.join(dev, "a.txt"), "1")
        git(dev, "add", ".")
        git(dev, "commit", "-q", "-m", "ilk")
        uzak = os.path.join(self.t, "uzak.git").replace("\\", "/")
        subprocess.run(["git", "clone", "-q", "--bare", dev, uzak], check=True, capture_output=True)
        klon = os.path.join(self.t, "yayin")
        with mock.patch.object(Y, "github_adresi", return_value=uzak):
            with contextlib.redirect_stdout(io.StringIO()):
                Y.klon_kur(klon, False)
                self.assertEqual(git(klon, "rev-parse", "HEAD"), git(dev, "rev-parse", "HEAD"))
                hooklar = [h for h in os.listdir(os.path.join(klon, ".git", "hooks")) if not h.endswith(".sample")]
                self.assertEqual(hooklar, [])
                # origin yerel yola çevrilmişse GitHub adresine döndürülür
                git(klon, "remote", "set-url", "origin", dev)
                Y.klon_kur(klon, False)
            self.assertEqual(git(klon, "remote", "get-url", "origin"), uzak)

    def test_yayin_kur_yerel_origini_reddeder(self):
        import yayin_kur as Y
        with mock.patch.object(Y, "git", return_value=mock.Mock(returncode=0, stdout=self.t + "\n")):
            with self.assertRaises(SystemExit) as c:
                Y.github_adresi()
        self.assertIn("yerel", str(c.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
