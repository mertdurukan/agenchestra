"""araclar/temiz_gecmis.py: çok commit'li depodan tek commit'lik temiz kopya; yasak desen varsa çıkış 1."""
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest

ARAC = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "araclar", "temiz_gecmis.py")
spec = importlib.util.spec_from_file_location("temiz_gecmis", ARAC)
TG = importlib.util.module_from_spec(spec)
spec.loader.exec_module(TG)


def git(kok, *a):
    return subprocess.run(["git", "-c", "safe.directory=*", "-C", kok, *a], capture_output=True, text=True, encoding="utf-8").stdout.strip()


class TemizGecmis(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp(prefix="ork_tg_")
        self.kaynak = os.path.join(self.t, "k")
        os.makedirs(self.kaynak)
        git(self.kaynak, "init", "-q", "-b", "main")
        git(self.kaynak, "config", "user.email", "t@example.com")
        git(self.kaynak, "config", "user.name", "t")
        for i, metin in enumerate(["bir\n", "iki zzmusteri\n", "uc\n"]):
            with open(os.path.join(self.kaynak, "a.txt"), "w", encoding="utf-8", newline="") as f:
                f.write(metin)
            git(self.kaynak, "add", "a.txt")
            git(self.kaynak, "commit", "-q", "-m", "c%d" % i)

    def tearDown(self):
        shutil.rmtree(self.t, ignore_errors=True)

    def test_tek_commit_ve_temiz(self):
        cikti = os.path.join(self.t, "c")
        self.assertEqual(TG.main(["--kaynak", self.kaynak, "--cikti", cikti, "--desen", "zzmusteri"]), 0)
        self.assertEqual(git(cikti, "rev-list", "--count", "HEAD"), "1")

    def test_yasak_desen_cikis_1(self):
        with open(os.path.join(self.kaynak, "a.txt"), "w", encoding="utf-8", newline="") as f:
            f.write("zzmusteri\n")
        git(self.kaynak, "commit", "-qam", "d")
        self.assertEqual(TG.main(["--kaynak", self.kaynak, "--cikti", os.path.join(self.t, "c"), "--desen", "zzmusteri"]), 1)

    def test_dolu_cikti_dizini_reddedilir(self):
        self.assertEqual(TG.main(["--kaynak", self.kaynak, "--cikti", self.kaynak]), 2)


if __name__ == "__main__":
    unittest.main()
