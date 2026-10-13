"""Kart çalışma ağacı + test kapısı: kilitli test, test_alani ve test-kos ağaçtaki karşılığa göre işler.

Her test geçici bir git deposu açar (tempfile); gerçek depoya dokunmaz.
`python -m unittest discover -s plugins/orkestra/tests -v`
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(KOK, "scripts", "orkestra.py")
HOOK = os.path.join(KOK, "scripts", "hook.py")
OTURUM = "agac-test-oturum"

KIRMIZI_TEST = ("import os, sys, unittest\n"
                "sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))\n"
                "import x\n"
                "class T(unittest.TestCase):\n"
                "    def test_f(self):\n"
                "        self.assertEqual(x.f(), 2)\n")


def kos(args, cwd, stdin=None):
    env = dict(os.environ, CLAUDE_CODE_SESSION_ID=OTURUM, PYTHONUTF8="1")
    env.pop("CLAUDE_PROJECT_DIR", None)
    return subprocess.run([sys.executable] + args, cwd=cwd, env=env, input=stdin, capture_output=True, text=True,
                          encoding="utf-8")


def git(cwd, *args):
    r = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)}: {r.stderr or r.stdout}")
    return r.stdout


def yaz(yol, metin):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8", newline="\n") as f:
        f.write(metin)


class AgacTestKapisi(unittest.TestCase):
    def setUp(self):
        self.taban = os.path.realpath(tempfile.mkdtemp(prefix="ork_agt_"))
        self.proje = os.path.join(self.taban, "depo")
        os.makedirs(self.proje)
        git(self.proje, "init", "-q", "-b", "main")
        git(self.proje, "config", "user.name", "Test")
        git(self.proje, "config", "user.email", "test@example.invalid")
        git(self.proje, "config", "core.autocrlf", "false")
        yaz(os.path.join(self.proje, ".gitignore"), ".claude/\n__pycache__/\n")
        yaz(os.path.join(self.proje, "src", "x.py"), "def f():\n    return 1\n")
        yaz(os.path.join(self.proje, "tests", "test_x.py"), KIRMIZI_TEST)
        yaz(os.path.join(self.proje, "docs", "d.md"), "# d\n")
        git(self.proje, "add", ".")
        git(self.proje, "commit", "-q", "-m", "ilk")
        r = kos([CLI, "baslat"], self.proje)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.cli("kart", "yeni", "--baslik", "kod", "--basamak", "T2", "--kabul", "ok", "--sinif", "kod",
                     "--test-komutu", f'"{sys.executable}" -m unittest discover -s tests', "--test-alani", "tests/**",
                     "--yazma", "src/**", "--yazma", "tests/**")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.g = r.stdout.strip()

    def tearDown(self):
        for satir in git(self.proje, "worktree", "list", "--porcelain").splitlines():
            if satir.startswith("worktree ") and os.path.realpath(satir[9:]) != self.proje:
                subprocess.run(["git", "-C", self.proje, "worktree", "remove", "--force", satir[9:]], capture_output=True)
        shutil.rmtree(self.taban, ignore_errors=True)

    # ---------------------------------------------------------- yardımcılar
    def cli(self, *args, ajan_id="ana", ajan_tipi="ana"):
        return kos([CLI] + list(args) + ["--ajan-id", ajan_id, "--ajan-tipi", ajan_tipi], self.proje)

    def kirmizi(self):
        r = self.cli("kart", "test-kos", self.g, "--asama", "kirmizi", ajan_id="tw", ajan_tipi="orkestra:isci-t2")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def agac(self):
        r = self.cli("kart", "agac", self.g)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def karar(self, dosya, surec="is", ana=False):
        """(karar, neden) — karar None ise hook geçti."""
        girdi = {"session_id": OTURUM, "cwd": self.proje, "hook_event_name": "PreToolUse", "tool_name": "Write",
                 "tool_input": {"file_path": dosya, "content": "x"}}
        if not ana:
            # Etiket önbelleği (test_test_kilidi_hook.py ile aynı yol): hook #GOREV/#SUREC'i buradan okur.
            aid = "w-" + surec
            yaz(os.path.join(self.proje, ".claude", "orkestra", "oturumlar", f"ajan_{aid}.json"),
                json.dumps({"gorev": self.g, "surec": surec, "ajan": "orkestra:isci-t2"}))
            girdi.update(agent_id=aid, agent_type="orkestra:isci-t2")
        r = kos([HOOK, "PreToolUse"], self.proje, stdin=json.dumps(girdi))
        self.assertEqual(r.returncode, 0, r.stderr)
        h = (json.loads(r.stdout) if r.stdout.strip() else {}).get("hookSpecificOutput") or {}
        return h.get("permissionDecision"), h.get("permissionDecisionReason") or ""

    # ---------------------------------------------------------- (a) ağaçtaki kilitli test
    def test_a_agactaki_kilitli_teste_test_yaz_ve_ana_ajan_yazamaz(self):
        self.kirmizi()
        yol = self.agac()
        hedef = os.path.join(yol, "tests", "test_x.py")
        for surec, ana in (("test-yaz", False), ("is", False), ("is", True)):
            k, neden = self.karar(hedef, surec, ana=ana)
            self.assertEqual(k, "deny", f"{surec} ana={ana}")
            self.assertIn("kilitli test", neden)
        # paylaşılan ağaçtaki karşılığı da kilitli kalır
        self.assertEqual(self.karar(os.path.join(self.proje, "tests", "test_x.py"), ana=True)[0], "deny")
        # kilitli olmayan ağaç dosyası ana ajana kilit gerekçesiyle kapanmaz
        k, neden = self.karar(os.path.join(yol, "src", "x.py"), ana=True)
        self.assertNotIn("kilitli test", neden)

    # ---------------------------------------------------------- (b) ağaçta test alanı / src
    def test_b_agacta_kod_iscisi_test_alanina_yazamaz_srcye_yazar(self):
        yol = self.agac()
        k, neden = self.karar(os.path.join(yol, "tests", "test_y.py"), "is")
        self.assertEqual(k, "deny")
        self.assertIn("test_alani", neden)
        self.assertIsNone(self.karar(os.path.join(yol, "src", "y.py"), "is")[0])
        self.assertIsNone(self.karar(os.path.join(yol, "tests", "test_y.py"), "test-yaz")[0])
        k, neden = self.karar(os.path.join(yol, "src", "y.py"), "test-yaz")
        self.assertEqual(k, "deny")
        self.assertIn("test-yaz yalnız test_alani", neden)

    # ---------------------------------------------------------- (c) sıra
    def test_c_sira_paylasilan_depo_test_alani_agac_yazma_alani(self):
        yol = self.agac()
        # 1) paylaşılan depo reddi test-yaz'ın test_alani geçişinden önce gelir
        for surec in ("test-yaz", "is"):
            k, neden = self.karar(os.path.join(self.proje, "tests", "test_y.py"), surec)
            self.assertEqual(k, "deny", surec)
            self.assertIn("çalışma ağacı var", neden, surec)
        # 2) ağaçta test alanı denetimi, ağaç yazma alanı denetiminden önce
        k, neden = self.karar(os.path.join(yol, "tests", "test_y.py"), "is")
        self.assertIn("test_alani", neden)
        # 3) test alanı dışı, yazma alanı dışı → ağaç yazma alanı reddi
        k, neden = self.karar(os.path.join(yol, "docs", "z.md"), "is")
        self.assertEqual(k, "deny")
        self.assertIn("yazma alanı dışında", neden)
        self.assertIn("çalışma ağacı:", neden)

    # ---------------------------------------------------------- (d) test-kos ağaçta
    def test_d_yesil_agactaki_kodla_gecer_bozuk_kilitli_test_gecmez(self):
        self.kirmizi()
        yol = self.agac()
        yaz(os.path.join(yol, "src", "x.py"), "def f():\n    return 2\n")  # düzeltme yalnız ağaçta
        r = self.cli("kart", "test-kos", self.g, "--asama", "yesil", ajan_id="tw", ajan_tipi="orkestra:isci-t2")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("GEÇTİ", r.stdout)
        # ağaçtaki kilitli test boşaltılır; paylaşılan ağaçta kod da düzeltilse yeşil geçmez
        yaz(os.path.join(yol, "tests", "test_x.py"),
            "import unittest\nclass T(unittest.TestCase):\n    def test_f(self):\n        pass\n")
        yaz(os.path.join(self.proje, "src", "x.py"), "def f():\n    return 2\n")
        r = self.cli("kart", "test-kos", self.g, "--asama", "yesil", ajan_id="tw", ajan_tipi="orkestra:isci-t2")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertIn("kilitten saptı", r.stdout)


if __name__ == "__main__":
    unittest.main()
