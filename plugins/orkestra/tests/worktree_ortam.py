"""Worktree oturumu testleri için ortak ortam (I-220): gerçek kombinasyonu kurar.

Uygulama hook sürecine `CLAUDE_PROJECT_DIR`'i ana ağaç olarak verebilir, hook girdisindeki `cwd` ise oturum worktree'sidir.
Önceki testler ortamı worktree'ye ayarlayıp bu kombinasyonu hiç sınamıyordu; yeni worktree testleri ortamı buradan alır.
Her test tempfile altında kendi git deposunu kurar; gerçek depoya dokunmaz.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import ork_lib as L  # noqa: E402

ORTAM_ANAHTARLARI = ("CLAUDE_PROJECT_DIR", L.DURUM_YEREL_ORTAM)


def git(cwd, *args):
    r = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)}: {r.stderr or r.stdout}")
    return r.stdout


def n(yol):
    return os.path.normcase(os.path.realpath(yol)).replace("\\", "/").rstrip("/")


class WorktreeOrtamMixin:
    """`kur_worktree_ortami()` setUp'tan çağrılır: self.ana, self.wt, self.sd; ortam ana ağaçtır (gerçek kombinasyon)."""

    PROJE_ADI = "Is"

    def kur_worktree_ortami(self, ortam="ana"):
        self.taban = os.path.realpath(tempfile.mkdtemp(prefix="ork_wto_"))
        self.ana = os.path.join(self.taban, "depo")
        self.sd = os.path.join(self.ana, ".claude", "orkestra")
        for alt in ("oturumlar", "gorevler"):
            os.makedirs(os.path.join(self.sd, alt))
        with open(os.path.join(self.sd, "baglam.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump({"surum": 1, "projeler": [self.PROJE_ADI]}, f)
        git(self.ana, "init", "-q", "-b", "main")
        git(self.ana, "config", "user.name", "Test")
        git(self.ana, "config", "user.email", "test@example.invalid")
        with open(os.path.join(self.ana, ".gitignore"), "w", encoding="utf-8", newline="\n") as f:
            f.write(".claude/orkestra/\n.claude/worktrees/\n")
        git(self.ana, "add", ".")
        git(self.ana, "commit", "-q", "-m", "ilk")
        self.wt = os.path.join(self.ana, ".claude", "worktrees", "oturum-ab12cd")
        git(self.ana, "worktree", "add", "-q", "-b", "claude/oturum-ab12cd", self.wt)
        self._eski_ortam = {k: os.environ.pop(k, None) for k in ORTAM_ANAHTARLARI}
        if ortam == "ana":
            os.environ["CLAUDE_PROJECT_DIR"] = self.ana
        elif ortam == "worktree":
            os.environ["CLAUDE_PROJECT_DIR"] = self.wt

    def temizle_worktree_ortami(self):
        for k, v in self._eski_ortam.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v
        subprocess.run(["git", "-C", self.ana, "worktree", "remove", "--force", self.wt], capture_output=True)
        shutil.rmtree(self.taban, ignore_errors=True)
