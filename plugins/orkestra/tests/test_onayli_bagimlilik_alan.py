"""Onaylı (teslim edilmemiş) bağımlılığın yazma alanı, bağımlı kartın isleniyor geçişini engellemez.

Bağımlı OLMAYAN onaylı kartın alanı eskisi gibi çıkış 5 verir. Geçici git deposu kullanır.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(KOK, "scripts", "orkestra.py")
OTURUM = "onayli-bag-oturum"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ic_kos  # noqa: E402


def git(cwd, *args):
    r = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)}: {r.stderr or r.stdout}")


def yaz(yol, metin):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8", newline="\n") as f:
        f.write(metin)


class OnayliBagimlilikAlani(unittest.TestCase):
    def setUp(self):
        self.taban = os.path.realpath(tempfile.mkdtemp(prefix="ork_obag_"))
        self.proje = os.path.join(self.taban, "depo")
        os.makedirs(self.proje)
        git(self.proje, "init", "-q", "-b", "main")
        git(self.proje, "config", "user.name", "Test")
        git(self.proje, "config", "user.email", "test@example.invalid")
        git(self.proje, "config", "core.autocrlf", "false")
        yaz(os.path.join(self.proje, ".gitignore"), ".claude/\n")
        yaz(os.path.join(self.proje, "src", "x.py"), "x = 1\n")
        git(self.proje, "add", ".")
        git(self.proje, "commit", "-q", "-m", "ilk")
        r = self.kos([CLI, "baslat"])
        self.assertEqual(r.returncode, 0, r.stderr)

    def tearDown(self):
        shutil.rmtree(self.taban, ignore_errors=True)

    def kos(self, args):
        env = dict(os.environ, CLAUDE_CODE_SESSION_ID=OTURUM, PYTHONUTF8="1")
        env.pop("CLAUDE_PROJECT_DIR", None)
        env.pop("ORKESTRA_AGAC_KOKU", None)
        return ic_kos.kos(args, cwd=self.proje, env=env, input=None)

    def cli(self, *args, ajan_id="ana", ajan_tipi="ana"):
        return self.kos([CLI] + list(args) + ["--ajan-id", ajan_id, "--ajan-tipi", ajan_tipi])

    def kart(self, yazma, bagimli=()):
        a = ["kart", "yeni", "--soru", "Kısa test sorusu?", "--baslik", "iş", "--basamak", "T2", "--kabul", "yapıldı", "--sinif", "belge",
             "--yazma", yazma]
        for b in bagimli:
            a += ["--bagimli", b]
        r = self.cli(*a)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def isleniyor(self, gid):
        return self.cli("kart", "durum", gid, "isleniyor", ajan_id="w-" + gid, ajan_tipi="orkestra:isci-t2")

    def onayla(self, gid):
        self.assertEqual(self.isleniyor(gid).returncode, 0)
        self.assertEqual(self.cli("kart", "durum", gid, "is-bitti", "--ozet", "tamam", ajan_id="w-" + gid,
                                  ajan_tipi="orkestra:isci-t2").returncode, 0)
        r = self.cli("kart", "denetim", gid, "--karar", "onay", "--gerekce", "ok", ajan_id="d1", ajan_tipi="orkestra:denetci")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_onayli_bagimlilik_alani_engel_degil(self):
        a = self.kart("src/**")
        b = self.kart("src/x.py", bagimli=[a])
        self.onayla(a)  # A onaylandi, teslim edilmedi
        r = self.isleniyor(b)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_bagimli_olmayan_onayli_kart_hala_engel(self):
        a = self.kart("src/**")
        b = self.kart("src/x.py")  # A'ya bağımlı değil
        self.onayla(a)
        r = self.isleniyor(b)
        self.assertEqual(r.returncode, 5, r.stdout + r.stderr)
        self.assertIn(f"çakışma: {a}", r.stderr)

    def test_bagimlilik_acik_islenen_kart_hala_engel(self):
        # Bağımlılık henüz onaylanmamış (isleniyor) ise alanı tutulu kalır.
        a = self.kart("src/**")
        b = self.kart("src/x.py", bagimli=[a])
        self.assertEqual(self.isleniyor(a).returncode, 0)
        self.assertEqual(self.isleniyor(b).returncode, 5)


if __name__ == "__main__":
    unittest.main()
