"""scripts/oto_commit.py: ORKESTRA_OTO_COMMIT ile açılır; yalnız düzenlenen dosyayı commit eder, .gitignore'u atlar."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BETIK = os.path.join(KOK, "scripts", "oto_commit.py")
HOOKS = os.path.join(KOK, "hooks", "hooks.json")


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, encoding="utf-8")


class OtoCommit(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp(prefix="ork_otocommit_")
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "test@example.com")
        git(self.repo, "config", "user.name", "test")
        git(self.repo, "config", "commit.gpgsign", "false")
        self.yaz(".gitignore", "gizli.txt\n")
        git(self.repo, "add", ".gitignore")
        git(self.repo, "commit", "-q", "-m", "ilk")

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def yaz(self, ad, metin):
        yol = os.path.join(self.repo, ad)
        with open(yol, "w", encoding="utf-8") as f:
            f.write(metin)
        return yol

    def kos(self, yol, acik="1", atif=None):
        env = dict(os.environ, PYTHONUTF8="1")
        env.pop("ORKESTRA_OTO_COMMIT_ATIF", None)
        if acik is None:
            env.pop("ORKESTRA_OTO_COMMIT", None)
        else:
            env["ORKESTRA_OTO_COMMIT"] = acik
        if atif:
            env["ORKESTRA_OTO_COMMIT_ATIF"] = atif
        girdi = {"tool_name": "Write", "tool_input": {"file_path": yol}}
        r = subprocess.run([sys.executable, BETIK], input=json.dumps(girdi), capture_output=True, text=True,
                           encoding="utf-8", env=env)
        self.assertEqual(r.returncode, 0, r.stderr)

    def commit_sayisi(self):
        return int(git(self.repo, "rev-list", "--count", "HEAD").stdout.strip())

    def test_kapaliyken_commit_yok(self):
        for deger in (None, "0", ""):
            self.kos(self.yaz("a.txt", "x"), acik=deger)
        self.assertEqual(self.commit_sayisi(), 1)

    def test_acikken_yalniz_o_dosya_commit_edilir(self):
        self.yaz("baska.txt", "dokunma")
        git(self.repo, "add", "baska.txt")  # başka oturumun sahnelediği dosya commit'e girmemeli
        self.kos(self.yaz("alt_a.txt", "x"), atif="Co-Authored-By: Deneme <x@example.com>")
        self.assertEqual(self.commit_sayisi(), 2)
        son = git(self.repo, "show", "--name-only", "--format=%B", "HEAD").stdout
        self.assertIn("Otomatik commit: alt_a.txt", son)
        self.assertIn("Co-Authored-By: Deneme", son)
        self.assertNotIn("baska.txt", son)
        self.assertIn("A  baska.txt", git(self.repo, "status", "--porcelain").stdout)

    def test_izlenen_dosya_degisince_commit(self):
        yol = self.yaz("b.txt", "1")
        self.kos(yol)
        self.yaz("b.txt", "2")
        self.kos(yol)
        self.assertEqual(self.commit_sayisi(), 3)
        self.assertIn("Co-Authored-By: Claude <noreply@anthropic.com>", git(self.repo, "log", "-1", "--format=%B").stdout)

    def test_gitignore_ve_degismeyen_dosya_atlanir(self):
        self.kos(self.yaz("gizli.txt", "sır yok"))
        yol = self.yaz("c.txt", "1")
        self.kos(yol)
        self.kos(yol)  # değişiklik yok
        self.assertEqual(self.commit_sayisi(), 2)

    def test_hooks_json_girdisi(self):
        with open(HOOKS, encoding="utf-8") as f:
            post = json.load(f)["hooks"]["PostToolUse"]
        girdi = [g for g in post if "oto_commit.py" in g["hooks"][0]["command"]]
        self.assertEqual(len(girdi), 1)
        self.assertEqual(girdi[0]["matcher"], "Edit|Write|MultiEdit|NotebookEdit")
        h = girdi[0]["hooks"][0]
        betik = '"${CLAUDE_PLUGIN_ROOT}/scripts/oto_commit.py"'
        self.assertEqual(h["command"], ('case "${ORKESTRA_OTO_COMMIT:-0}" in 0|"") exit 0;; esac; '
                                        f'if command -v python >/dev/null 2>&1; then exec python {betik}; '
                                        f'elif command -v py >/dev/null 2>&1; then exec py -3 {betik}; '
                                        f'else exec python3 {betik}; fi'))
        self.assertNotIn("args", h)
        self.assertNotIn("hook_python", h["command"])


if __name__ == "__main__":
    unittest.main()
