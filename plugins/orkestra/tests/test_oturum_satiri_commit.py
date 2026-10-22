"""Oturum satırı yalnız bağlı (linked) worktree'de commit'lenir (ana ağaçta commit atılmaz); bağlı worktree'de SessionEnd
yazmaz, satırlar Stop'ta yazılıp commit'lenir (ADR-0038).
`py -3.13 -m pytest plugins/orkestra/tests/test_oturum_satiri_commit.py`
"""
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import hook  # noqa: E402
import oto_commit  # noqa: E402


def git(cwd, *args):
    r = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)}: {r.stderr or r.stdout}")
    return r.stdout


class OturumSatiriCommit(unittest.TestCase):
    def setUp(self):
        self.taban = os.path.realpath(tempfile.mkdtemp(prefix="ork_osc_"))
        self.ana = os.path.join(self.taban, "depo")
        os.makedirs(self.ana)
        git(self.ana, "init", "-q", "-b", "main")
        git(self.ana, "config", "user.name", "Test")
        git(self.ana, "config", "user.email", "test@example.invalid")
        self.rel = os.path.join("is", "oturumlar.md")
        os.makedirs(os.path.join(self.ana, "is"))
        self.yaz(self.ana, "# Oturumlar\n")
        git(self.ana, "add", "-A")
        git(self.ana, "commit", "-q", "-m", "ilk")
        self.agac = os.path.join(self.taban, "agac")
        git(self.ana, "worktree", "add", "-q", "-b", "claude/x", self.agac)
        git(self.agac, "config", "user.name", "Test")
        git(self.agac, "config", "user.email", "test@example.invalid")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.taban, ignore_errors=True)

    def yaz(self, kok, satir):
        with open(os.path.join(kok, self.rel), "a", encoding="utf-8", newline="\n") as f:
            f.write(satir)

    def durum(self, kok):
        return git(kok, "status", "--porcelain", "--", self.rel).strip()

    def test_bagli_worktree_te_commitlenir(self):
        self.yaz(self.agac, "- satir\n")
        self.assertTrue(self.durum(self.agac))
        hook._oturum_agacinda_commitle(os.path.join(self.agac, self.rel))
        self.assertEqual(self.durum(self.agac), "")
        self.assertIn("oturum satırı", git(self.agac, "log", "-1", "--format=%s"))

    def test_ana_agacta_commitlenmez(self):
        self.yaz(self.ana, "- satir\n")
        hook._oturum_agacinda_commitle(os.path.join(self.ana, self.rel))
        self.assertTrue(self.durum(self.ana))

    def test_baska_dosyaya_dokunmaz(self):
        self.yaz(self.agac, "- satir\n")
        with open(os.path.join(self.agac, "baska.txt"), "w", encoding="utf-8") as f:
            f.write("x")
        git(self.agac, "add", "baska.txt")
        hook._oturum_agacinda_commitle(os.path.join(self.agac, self.rel))
        self.assertIn("A  baska.txt", git(self.agac, "status", "--porcelain"))

    def _ozet(self, oid="abcd1234", sayi="1"):
        return f"- 2026-10-22 20:00 · oturum {oid} · Claude süresi {sayi} · alt ajan süresi - · 1 token · $0.00 · ne: x · sonuç/nerede kalındı: y\n"

    def _sessionend(self, kok, ozet):
        yol = os.path.join(kok, self.rel)
        with mock.patch.object(hook, "_oturum_ozet_yolu", return_value=yol), \
                mock.patch.object(hook, "_oturum_ozet_satiri", return_value=ozet):
            hook._oturum_satiri_yaz("sd", "abcd1234-oturum")

    def test_sessionend_bagli_worktree_te_yazmaz(self):
        onceki = open(os.path.join(self.agac, self.rel), encoding="utf-8").read()
        self._sessionend(self.agac, self._ozet())
        self.assertEqual(open(os.path.join(self.agac, self.rel), encoding="utf-8").read(), onceki)
        self.assertEqual(self.durum(self.agac), "")

    def test_sessionend_kapaliysa_eski_davranis(self):
        with mock.patch.dict(os.environ, {"ORKESTRA_OTURUM_SATIRI_STOPTA": "0"}):
            self._sessionend(self.agac, self._ozet())
        self.assertIn("Claude süresi", open(os.path.join(self.agac, self.rel), encoding="utf-8").read())
        self.assertEqual(self.durum(self.agac), "")

    def test_sessionend_ana_agacta_ekler_commitlemez(self):
        self._sessionend(self.ana, self._ozet())
        self.assertIn("Claude süresi", open(os.path.join(self.ana, self.rel), encoding="utf-8").read())
        self.assertTrue(self.durum(self.ana))

    def test_stop_ozeti_tek_satir_yeniler_ve_commitler(self):
        yol = os.path.join(self.agac, self.rel)
        self.yaz(self.agac, "- tur satiri\n")
        with mock.patch.object(hook, "_oturum_ozet_satiri", return_value=self._ozet(sayi="1")):
            hook._bagli_agacta_satirlari_kaydet("sd", "abcd1234-oturum", yol)
        self.assertEqual(self.durum(self.agac), "")
        self.yaz(self.agac, "- tur satiri 2\n")
        with mock.patch.object(hook, "_oturum_ozet_satiri", return_value=self._ozet(sayi="2")):
            hook._bagli_agacta_satirlari_kaydet("sd", "abcd1234-oturum", yol)
        govde = open(yol, encoding="utf-8").read()
        self.assertEqual(govde.count("oturum abcd1234 · Claude süresi"), 1)
        self.assertIn("Claude süresi 2", govde)
        self.assertIn("- tur satiri\n", govde)
        self.assertIn("- tur satiri 2\n", govde)
        self.assertEqual(self.durum(self.agac), "")

    def test_stop_ana_agacta_dokunmaz(self):
        yol = os.path.join(self.ana, self.rel)
        onceki = open(yol, encoding="utf-8").read()
        with mock.patch.object(hook, "_oturum_ozet_satiri", return_value=self._ozet()):
            hook._bagli_agacta_satirlari_kaydet("sd", "abcd1234-oturum", yol)
        self.assertEqual(open(yol, encoding="utf-8").read(), onceki)

    def test_index_lock_cakismasinda_yeniden_dener(self):
        self.yaz(self.agac, "- satir\n")
        gitdir = git(self.agac, "rev-parse", "--path-format=absolute", "--git-dir").strip()
        kilit = os.path.join(gitdir, "index.lock")
        with open(kilit, "w"):
            pass
        threading.Timer(1.5, lambda: os.remove(kilit)).start()
        hook._oturum_agacinda_commitle(os.path.join(self.agac, self.rel))
        self.assertEqual(self.durum(self.agac), "")

    def test_yedek_dosyasi_cli_sonrasi_commitlenir(self):
        klasor = os.path.join(self.agac, "is")
        with open(os.path.join(klasor, "is.json.eski-20261022184814"), "w", encoding="utf-8") as f:
            f.write("{}")
        yollar = oto_commit.klasorleri_commit(self.agac, ["is"], None, etiket="orkestra")
        self.assertEqual(yollar, ["is/is.json.eski-20261022184814"])
        self.assertEqual(git(self.agac, "status", "--porcelain").strip(), "")


if __name__ == "__main__":
    unittest.main()
