"""Yayın klonu: projeye_kur kaynağı, orkestra guncelle klon denetimi, git hook (python -m unittest)."""
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


def _sh_yolu():
    """sh yolu: PATH'te yoksa Git kurulumundaki sh.exe (bin/ ya da usr/bin/); yoksa None."""
    yol = shutil.which("sh")
    if yol:
        return yol
    try:
        ep = subprocess.run(["git", "--exec-path"], capture_output=True, text=True,
                            encoding="utf-8", check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    d = os.path.abspath(ep)
    while True:
        for aday in (os.path.join(d, "bin", "sh.exe"), os.path.join(d, "usr", "bin", "sh.exe")):
            if os.path.isfile(aday):
                return aday
        ust = os.path.dirname(d)
        if ust == d:
            return None
        d = ust


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

    def test_guncelle_kirli_yayin_klonunu_reddeder(self):
        import orkestra as O
        klon = os.path.join(self.t, "klon")
        os.makedirs(klon)
        git(klon, "init", "-q")
        yaz(os.path.join(klon, "a.txt"), "1")
        git(klon, "add", ".")
        git(klon, "commit", "-q", "-m", "x")
        yaz(os.path.join(klon, "a.txt"), "2")
        a = type("A", (), {"kuru": False})()
        with mock.patch.object(O.L, "pazar_kaynagi", return_value=klon), \
                mock.patch.object(O.L, "claude_exe", return_value="claude-yok"), \
                mock.patch.object(O.L, "proje_dizini", return_value=self.t), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as err:
            with self.assertRaises(SystemExit):
                O.cmd_guncelle(a)
        self.assertIn("commitlenmemiş", err.getvalue())

    def test_hook_yalniz_klonun_dalinda_esitler_ve_hep_0_cikar(self):
        sh = _sh_yolu()
        if sh is None:
            self.skipTest("sh bulunamadı (Git Bash yok)")
        sablon = os.path.join(DEPO, "araclar", "git_hooklar", "yayin-esitle.sh")
        dev, klon = os.path.join(self.t, "dev"), os.path.join(self.t, "klon")
        os.makedirs(dev)
        git(dev, "init", "-q", "-b", "main")
        yaz(os.path.join(dev, "a.txt"), "1")
        git(dev, "add", ".")
        git(dev, "commit", "-q", "-m", "ilk")
        subprocess.run(["git", "clone", "-q", dev, klon], check=True, capture_output=True)
        with open(sablon, encoding="utf-8", newline="") as f:
            betik = os.path.join(self.t, "he.sh")
            with open(betik, "w", encoding="utf-8", newline="\n") as g:
                g.write(f.read().replace("@YAYIN@", klon.replace("\\", "/")))
        kos = lambda: subprocess.run([sh, betik], cwd=dev, capture_output=True, text=True, encoding="utf-8")
        # main'de commit: klon ilerler
        yaz(os.path.join(dev, "a.txt"), "2")
        git(dev, "commit", "-q", "-am", "iki")
        self.assertEqual(kos().returncode, 0)
        self.assertEqual(git(klon, "rev-parse", "HEAD"), git(dev, "rev-parse", "HEAD"))
        # başka dalda commit: klon dalı ve HEAD'i değişmez, sessiz 0
        onceki = git(klon, "rev-parse", "HEAD")
        git(dev, "checkout", "-q", "-b", "deneme")
        yaz(os.path.join(dev, "a.txt"), "3")
        git(dev, "commit", "-q", "-am", "uc")
        r = kos()
        self.assertEqual(r.returncode, 0)
        self.assertEqual(git(klon, "symbolic-ref", "--short", "HEAD"), "main")
        self.assertEqual(git(klon, "rev-parse", "HEAD"), onceki)
        # klon yoksa yine 0, mesaj stderr'de
        shutil.rmtree(klon, ignore_errors=True)
        r = kos()
        self.assertEqual(r.returncode, 0)
        self.assertIn("orkestra-yayin", r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
