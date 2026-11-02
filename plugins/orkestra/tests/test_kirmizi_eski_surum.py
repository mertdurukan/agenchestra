"""005 kırmızı kapı: kod önceden yazılmışsa `kart test-kos --asama kirmizi --eski-surumde [--surum-ref REF]` testi eski sürümde
(geçici git worktree) koşturur; çalışma ağacı hiçbir durumda değişmez."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ic_kos  # noqa: E402

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(KOK, "scripts", "orkestra.py")
OTURUM = "test-oturum-es"
ANA = dict(ajan_id="ana", ajan_tipi="ana")

ESKI_KOD = "def deger():\n    return 1\n"
YENI_KOD = "def deger():\n    return 2\n"
TEST = ("import unittest\n"
        "import uygulama\n\n\n"
        "class T(unittest.TestCase):\n"
        "    def test_deger(self):\n"
        "        self.assertEqual(uygulama.deger(), 2)\n")


def kos(args, cwd):
    env = dict(os.environ, CLAUDE_CODE_SESSION_ID=OTURUM, PYTHONUTF8="1")
    env.pop("CLAUDE_PROJECT_DIR", None)
    return ic_kos.kos(args, cwd=cwd, env=env)


class EskiSurumdeKirmizi(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_es_")
        self.addCleanup(shutil.rmtree, self.proje, ignore_errors=True)
        self.git("init", "-q")
        self.yaz("uygulama.py", ESKI_KOD)
        self.git("add", "uygulama.py")
        self.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "eski")
        self.eski_sha = self.git("rev-parse", "HEAD").stdout.strip()
        self.assertEqual(kos([CLI, "baslat"], self.proje).returncode, 0)
        self.yaz("testler/test_u.py", TEST)  # test yeni, izlenmiyor
        self.yaz("uygulama.py", YENI_KOD)  # kod testten önce yazılmış (çalışma ağacında)
        self.komut = f'"{sys.executable}" -m pytest testler/test_u.py -q'

    def git(self, *a):
        return subprocess.run(["git", *a], cwd=self.proje, capture_output=True, text=True, encoding="utf-8")

    def yaz(self, goreli, icerik):
        yol = os.path.join(self.proje, *goreli.split("/"))
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with open(yol, "w", encoding="utf-8", newline="\n") as f:
            f.write(icerik)

    def oku(self, goreli):
        with open(os.path.join(self.proje, *goreli.split("/")), encoding="utf-8", newline="") as f:
            return f.read()

    def cli(self, *args, **kim):
        a = [CLI, *args]
        if kim:
            a += ["--ajan-id", kim["ajan_id"], "--ajan-tipi", kim["ajan_tipi"]]
        return kos(a, self.proje)

    def kart(self, tdd=True):
        r = self.cli("kart", "yeni", "--soru", "Kısa test sorusu?", "--baslik", "kod işi", "--basamak", "T2", "--sinif", "kod",
                     *(["--tdd"] if tdd else []), "--kabul", "çalışır", "--yazma", "src/**",
                     "--test-komutu", self.komut, "--test-alani", "testler/*.py")
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def kart_json(self, g):
        import json
        return json.loads(self.cli("kart", "goster", g).stdout)

    def durum(self):
        return self.git("status", "--porcelain").stdout

    @unittest.skipIf(os.environ.get("GITHUB_ACTIONS") == "true" and sys.platform == "win32",
                "I-304: Windows 8.3 kısa yol, ürün kodunda realpath gerekir (kart.py:1139, teknik.py:201, ork_lib.py:1148)")
    def test_kod_yazilmisken_duz_kirmizi_gecmez_eski_surumde_kirmizi_kilitler(self):
        g = self.kart()
        r = self.cli("kart", "test-kos", g, "--asama", "kirmizi")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)  # kod yazılı: test yeşil, kırmızı olamaz
        self.assertFalse(self.kart_json(g).get("test_kilidi"))
        once = self.durum()
        r = self.cli("kart", "test-kos", g, "--asama", "kirmizi", "--eski-surumde")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("test kirmizi: GEÇTİ", r.stdout)
        k = self.kart_json(g)
        self.assertTrue(k["test_kilidi"])
        self.assertEqual(k["test_kosulari"][-1]["eski_surum"], self.eski_sha)
        self.assertEqual(self.oku("uygulama.py"), YENI_KOD)  # çalışma ağacı değişmedi
        self.assertEqual(self.durum(), once)
        self.assertEqual(len([x for x in self.git("worktree", "list").stdout.splitlines() if x.strip()]), 1)  # geçici worktree silindi

    @unittest.skipIf(os.environ.get("GITHUB_ACTIONS") == "true" and sys.platform == "win32",
                "I-304: Windows 8.3 kısa yol, ürün kodunda realpath gerekir (kart.py:1139, teknik.py:201, ork_lib.py:1148)")
    def test_surum_ref_verilen_sürümde_kosar_eski_sha(self):
        g = self.kart()
        r = self.cli("kart", "test-kos", g, "--asama", "kirmizi", "--eski-surumde", "--surum-ref", self.eski_sha)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.kart_json(g)["test_kosulari"][-1]["eski_surum"], self.eski_sha)

    def test_test_eski_surumde_de_yesilse_kirmizi_gecmez_kilit_yazilmaz(self):
        self.yaz("uygulama.py", YENI_KOD)
        self.git("add", "uygulama.py")
        self.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "kod yeni")
        g = self.kart()
        r = self.cli("kart", "test-kos", g, "--asama", "kirmizi", "--eski-surumde")  # HEAD artık yeni kod: test yeşil
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertFalse(self.kart_json(g).get("test_kilidi"))

    def test_hatali_kullanim_ve_gecersiz_ref(self):
        g = self.kart()
        self.assertNotEqual(self.cli("kart", "test-kos", g, "--asama", "yesil", "--eski-surumde").returncode, 0)
        self.assertNotEqual(self.cli("kart", "test-kos", g, "--asama", "kirmizi", "--surum-ref", "HEAD").returncode, 0)
        r = self.cli("kart", "test-kos", g, "--asama", "kirmizi", "--eski-surumde", "--surum-ref", "yok-boyle-ref")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("bulunamadı", r.stderr)
        self.assertEqual(self.oku("uygulama.py"), YENI_KOD)
        self.assertEqual(len([x for x in self.git("worktree", "list").stdout.splitlines() if x.strip()]), 1)

    def test_git_deposu_degilse_acik_hata(self):
        shutil.rmtree(os.path.join(self.proje, ".git"), ignore_errors=True)
        g = self.kart()
        r = self.cli("kart", "test-kos", g, "--asama", "kirmizi", "--eski-surumde")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("git deposunda", r.stderr)


if __name__ == "__main__":
    unittest.main()
