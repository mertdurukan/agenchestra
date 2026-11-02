"""Yol bazlı gönderim kapısı (ADR-0012): yasak yola dokunan commit engellenir, öncekiler zincirlenir."""
import os
import subprocess
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import push_kapisi as P  # noqa: E402

CLI = os.path.join(KOK, "scripts", "orkestra.py")


def git(d, *a):
    return subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgsign=false", "-C", d, *a],
                          capture_output=True, text=True, encoding="utf-8")


def dosya(d, ad, metin="x"):
    p = os.path.join(d, ad)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(metin)


class Kapi(unittest.TestCase):
    def setUp(self):
        t = tempfile.mkdtemp()
        self.uzak = os.path.join(t, "uzak.git")
        self.d = os.path.join(t, "proje")
        subprocess.run(["git", "init", "-q", "--bare", self.uzak], check=True)
        subprocess.run(["git", "init", "-q", "-b", "main", self.d], check=True)
        git(self.d, "remote", "add", "origin", self.uzak)
        dosya(self.d, "a.txt")
        git(self.d, "add", "-A")
        git(self.d, "commit", "-qm", "ilk")
        git(self.d, "push", "-q", "origin", "main")
        P.yol_ekle(self.d, "gizli")

    def cli(self, *a):
        return subprocess.run([sys.executable, "-X", "utf8", CLI, *a], cwd=self.d, capture_output=True, text=True, encoding="utf-8")

    def gonder(self):
        return git(self.d, "push", "origin", "main")

    def test_kur_yasak_yol_engellenir_temiz_gecer(self):
        r = self.cli("push-kapisi", "kur")
        self.assertEqual(r.returncode, 0, r.stderr)
        dosya(self.d, "temiz.txt")
        git(self.d, "add", "-A"); git(self.d, "commit", "-qm", "temiz")
        self.assertEqual(self.gonder().returncode, 0)
        dosya(self.d, "gizli/x.md")
        git(self.d, "add", "-A"); git(self.d, "commit", "-qm", "gizli")
        r = self.gonder()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("GONDERIM ENGELLENDI", r.stderr)

    def test_onceki_hook_zincirlenir_ve_kaldirinca_geri_gelir(self):
        k = os.path.join(self.d, ".git", "hooks", "pre-push")
        with open(k, "w", encoding="utf-8", newline="\n") as f:
            f.write("#!/bin/sh\necho ONCEKI-CALISTI >&2\nexit 0\n")
        os.chmod(k, 0o755)
        self.cli("push-kapisi", "kur")
        self.assertTrue(os.path.exists(k + ".onceki"))
        dosya(self.d, "b.txt"); git(self.d, "add", "-A"); git(self.d, "commit", "-qm", "b")
        self.assertIn("ONCEKI-CALISTI", self.gonder().stderr)
        self.cli("push-kapisi", "kaldir")
        with open(k, encoding="utf-8") as f:
            self.assertIn("ONCEKI-CALISTI", f.read())
        self.assertFalse(os.path.exists(k + ".onceki"))

    def test_durum_ve_yasak_yol_yoksa_gecer(self):
        self.assertIn("kurulu değil", self.cli("push-kapisi", "durum").stdout)
        self.assertEqual(P.ihlaller(self.d, "origin", "", []), [])
        os.remove(P.ayar_yolu(self.d))
        self.assertEqual(P.yollar(self.d), [])


if __name__ == "__main__":
    unittest.main()
