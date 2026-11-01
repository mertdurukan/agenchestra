"""Worktree oturumunda iş belgeleri oturum klasöründe, bağlantı tabanı oturum köküdür (ADR-0035, I-161).

Uygulama göreli bağlantıyı oturum klasörüne (worktree) göre çözer; durum ana klasörde tek kaynak kalır.
Her test tempfile altında kendi git deposunu kurar; gerçek depoya dokunmaz.
`py -3.13 -m pytest plugins/orkestra/tests/test_belge_baglanti_worktree.py`
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(KOK, "scripts", "orkestra.py")
sys.path.insert(0, os.path.join(KOK, "scripts"))
import ork_lib as L  # noqa: E402
import is_onay as OY  # noqa: E402


def git(cwd, *args):
    r = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)}: {r.stderr or r.stdout}")
    return r.stdout


def n(yol):
    return os.path.normcase(os.path.realpath(yol)).replace("\\", "/").rstrip("/")


class BelgeBaglantiWorktree(unittest.TestCase):
    def setUp(self):
        self.taban = os.path.realpath(tempfile.mkdtemp(prefix="ork_bbw_"))
        self.ana = os.path.join(self.taban, "depo")
        os.makedirs(os.path.join(self.ana, ".claude", "orkestra"))
        git(self.ana, "init", "-q", "-b", "main")
        git(self.ana, "config", "user.name", "Test")
        git(self.ana, "config", "user.email", "test@example.invalid")
        with open(os.path.join(self.ana, ".gitignore"), "w", encoding="utf-8", newline="\n") as f:
            f.write(".claude/orkestra/\n.claude/worktrees/\n")
        with open(os.path.join(self.ana, "a.txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write("bir\n")
        git(self.ana, "add", ".")
        git(self.ana, "commit", "-q", "-m", "ilk")
        self.wt = os.path.join(self.ana, ".claude", "worktrees", "oturum-ab12cd")
        git(self.ana, "worktree", "add", "-q", "-b", "claude/oturum-ab12cd", self.wt)
        shutil.copytree(os.path.join(self.ana, ".claude", "orkestra"), os.path.join(self.wt, ".claude", "orkestra"))
        self._cwd = os.getcwd()
        for k in ("CLAUDE_PROJECT_DIR", L.DURUM_YEREL_ORTAM, "ORKESTRA_IS_KLASOR_KOK"):
            os.environ.pop(k, None)

    def tearDown(self):
        os.chdir(self._cwd)
        for k in ("CLAUDE_PROJECT_DIR", L.DURUM_YEREL_ORTAM, "ORKESTRA_IS_KLASOR_KOK"):
            os.environ.pop(k, None)
        subprocess.run(["git", "-C", self.ana, "worktree", "remove", "--force", self.wt], capture_output=True)
        shutil.rmtree(self.taban, ignore_errors=True)

    def kos(self, args, cwd, env_ek=None):
        env = dict(os.environ, CLAUDE_CODE_SESSION_ID="bbw-oturum", PYTHONUTF8="1")
        for k in ("CLAUDE_PROJECT_DIR", L.DURUM_YEREL_ORTAM, "ORKESTRA_IS_KLASOR_KOK"):
            env.pop(k, None)
        env.update(env_ek or {})
        return subprocess.run([sys.executable, CLI] + args, cwd=cwd, env=env, capture_output=True, text=True,
                              encoding="utf-8")

    # ------------------------------------------------------------------ P1 oturum kökü
    def test_oturum_koku_worktree_ve_ana_agac(self):
        self.assertEqual(n(L.oturum_koku(self.wt)), n(self.wt))
        self.assertEqual(n(L.oturum_koku(self.ana)), n(self.ana))

    def test_oturum_koku_alt_klasorden_worktree_kokudur(self):
        alt = os.path.join(self.wt, "derin", "klasor")
        os.makedirs(alt)
        self.assertEqual(n(L.oturum_koku(alt)), n(self.wt))

    def test_baglanti_koku_yalniz_ayni_deponun_worktreesinde_degisir(self):
        self.assertEqual(n(L.baglanti_koku(self.ana, self.wt)), n(self.wt))
        self.assertEqual(n(L.baglanti_koku(self.ana, self.ana)), n(self.ana))
        baska = os.path.join(self.taban, "baska")
        os.makedirs(baska)
        self.assertEqual(n(L.baglanti_koku(baska, self.wt)), n(baska))  # başka projenin kökü değişmez

    # ------------------------------------------------------------------ P2/P3 CLI
    def _is_ac(self, klasor, cwd, env_ek=None):
        return self.kos(["is", "ac", "Deneme işi", "--klasor", klasor], cwd, env_ek)

    def test_worktreedeki_is_baglantisi_oneksiz_ve_oturum_koklu(self):
        klasor = os.path.join(self.wt, "Claude_Orkestrasyon", "001-20261022-deneme")
        r = self._is_ac(klasor, self.wt)
        self.assertEqual(r.returncode, 0, r.stderr)
        is_id = r.stdout.strip().splitlines()[-1]
        b = self.kos(["is", "baglanti", is_id], self.wt)
        self.assertEqual(b.returncode, 0, b.stderr)
        self.assertIn("](Claude_Orkestrasyon/001-20261022-deneme/plan_gorunum.md)", b.stdout)  # ADR-0127
        self.assertNotIn(".claude/worktrees", b.stdout)

    def test_kok_disi_klasor_worktree_oturumunda_reddedilir(self):
        klasor = os.path.join(self.ana, "Claude_Orkestrasyon", "002-20261022-dis")
        r = self._is_ac(klasor, self.wt)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("oturum kökü dışında", r.stderr)
        self.assertIn(os.path.join(self.wt, "Claude_Orkestrasyon", "002-20261022-dis"), r.stderr)  # önerilen yol
        self.assertFalse(os.path.exists(klasor))

    def test_kok_disi_klasor_ortamla_kapatilabilir(self):
        klasor = os.path.join(self.ana, "Claude_Orkestrasyon", "003-20261022-dis")
        r = self._is_ac(klasor, self.wt, {"ORKESTRA_IS_KLASOR_KOK": "0"})
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_ana_agac_oturumunda_klasor_denetimi_yok(self):
        klasor = os.path.join(self.ana, "Claude_Orkestrasyon", "004-20261022-ana")
        r = self._is_ac(klasor, self.ana)
        self.assertEqual(r.returncode, 0, r.stderr)

    # ------------------------------------------------------------------ P4 onay kapısı
    def test_onay_beklerken_worktree_adr_klasorune_yazilabilir(self):
        os.chdir(self.wt)
        kayit = {"klasor": os.path.join(self.wt, "Claude_Orkestrasyon", "001-x")}
        self.assertEqual(OY.yazma_engeli(kayit, self.ana, os.path.join(self.wt, "adr", "ADR-0001-x.md")), "")
        self.assertEqual(OY.yazma_engeli(kayit, self.ana, os.path.join(self.ana, "adr", "ADR-0001-x.md")), "")
        self.assertNotEqual(OY.yazma_engeli(kayit, self.ana, os.path.join(self.wt, "src", "x.py")), "")


if __name__ == "__main__":
    unittest.main()
