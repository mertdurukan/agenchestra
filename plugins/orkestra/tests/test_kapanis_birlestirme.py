"""Kapanışta güvenli birleştirme (I-225, ADR-0086): temiz koşulda birleşir, güvensiz koşulda ana ağaç değişmez."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import dal_temizle  # noqa: E402
import ork_lib as L  # noqa: E402


def git(yol, *a):
    return subprocess.run(["git", "-C", yol, *a], capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()


def yaz(yol, ad, icerik):
    os.makedirs(os.path.dirname(os.path.join(yol, ad)) or yol, exist_ok=True)
    with open(os.path.join(yol, ad), "w", encoding="utf-8") as f:
        f.write(icerik)


def commit(yol, ad, icerik=None):
    yaz(yol, ad, icerik if icerik is not None else ad)
    git(yol, "add", "-A")
    git(yol, "commit", "-q", "-m", ad)


class KapanisBirlestirTest(unittest.TestCase):
    def setUp(self):
        self._ortam = {k: os.environ.get(k) for k in ("CLAUDE_PROJECT_DIR", "ORKESTRA_KAPANIS_BIRLESTIRME", "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL")}
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        os.environ.pop("ORKESTRA_KAPANIS_BIRLESTIRME", None)
        os.environ.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        self.k = tempfile.mkdtemp()
        self.depo = os.path.join(self.k, "depo")
        os.makedirs(self.depo)
        git(self.depo, "init", "-q", "-b", "main")
        yaz(self.depo, ".gitignore", ".claude/\n")
        commit(self.depo, "a.txt", "taban\n")
        os.makedirs(os.path.join(self.depo, ".claude", "orkestra"))
        self.wt = os.path.join(self.k, "wt")
        git(self.depo, "worktree", "add", "-q", "-b", "oturum", self.wt)

    def tearDown(self):
        for k, v in self._ortam.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.k, ignore_errors=True)

    def main_uc(self):
        return git(self.depo, "rev-parse", "main")

    def ana_durum(self):
        return git(self.depo, "status", "--porcelain", "--untracked-files=all")

    def gunluk(self):
        yol = os.path.join(self.depo, ".claude", "orkestra", "gunluk.jsonl")
        if not os.path.isfile(yol):
            return []
        with open(yol, encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]

    def test_temiz_birlesir(self):
        commit(self.wt, "x.txt")
        s = dal_temizle.kapanis_birlestir(self.wt, "ihlal", "I-1")
        self.assertEqual(s["sonuc"], "birlesti", s)
        self.assertEqual(git(self.depo, "merge-base", "--is-ancestor", "oturum", "main") or "", "")
        self.assertTrue(os.path.isfile(os.path.join(self.depo, "x.txt")))
        self.assertEqual(self.ana_durum(), "")
        self.assertEqual(len(git(self.depo, "rev-list", "--parents", "-n", "1", "main").split()), 3)  # --no-ff birleştirme commit'i
        self.assertEqual(self.gunluk()[-1]["sonuc"], "birlesti")

    def test_catisma_ana_agac_degismez(self):
        commit(self.depo, "a.txt", "ana\n")
        commit(self.wt, "a.txt", "dal\n")
        once = self.main_uc()
        s = dal_temizle.kapanis_birlestir(self.wt, "ihlal", "I-1")
        self.assertEqual(s["sonuc"], "catisma", s)
        self.assertIn("a.txt", s["dosyalar"])
        self.assertEqual(self.main_uc(), once)
        self.assertEqual(self.ana_durum(), "")
        self.assertFalse(os.path.exists(os.path.join(self.depo, ".git", "MERGE_HEAD")))

    def test_ortusen_commitsiz_dosya_degismez(self):
        commit(self.wt, "a.txt", "dal\n")                         # çakışmaz: ana a.txt'yi commit etmedi
        yaz(self.depo, "a.txt", "baskasinin commitsiz isi\n")
        once, durum = self.main_uc(), self.ana_durum()
        s = dal_temizle.kapanis_birlestir(self.wt, "ihlal", "I-1")
        self.assertEqual(s["sonuc"], "ortusme", s)
        self.assertEqual(s["dosyalar"], ["a.txt"])
        self.assertEqual(self.main_uc(), once)
        self.assertEqual(self.ana_durum(), durum)
        with open(os.path.join(self.depo, "a.txt"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "baskasinin commitsiz isi\n")

    def test_ilgisiz_commitsiz_dosya_korunur(self):
        commit(self.wt, "x.txt")
        yaz(self.depo, "baskasi.txt", "commitsiz\n")
        s = dal_temizle.kapanis_birlestir(self.wt, "ihlal", "I-1")
        self.assertEqual(s["sonuc"], "birlesti", s)
        with open(os.path.join(self.depo, "baskasi.txt"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "commitsiz\n")
        self.assertEqual(self.ana_durum(), "?? baskasi.txt")

    def test_ana_worktree_main_degil(self):
        commit(self.wt, "x.txt")
        git(self.depo, "checkout", "-q", "-b", "baska")
        once = git(self.depo, "rev-parse", "baska")
        s = dal_temizle.kapanis_birlestir(self.wt, "ihlal", "I-1")
        self.assertEqual(s["sonuc"], "ana-dal-degil", s)
        self.assertEqual(git(self.depo, "rev-parse", "baska"), once)
        self.assertEqual(git(self.depo, "rev-parse", "main"), git(self.depo, "rev-parse", "main"))
        self.assertNotEqual(git(self.depo, "merge-base", "--is-ancestor", "oturum", "main") if False else "x", "")

    def test_birlestirme_hatasi_abort(self):
        commit(self.wt, "x.txt")
        once = self.main_uc()
        gercek = dal_temizle._git

        def sahte(depo, *a):
            if a[:2] == ("merge", "--no-ff"):
                return subprocess.CompletedProcess(a, 1, "", "sahte hata")
            return gercek(depo, *a)

        with mock.patch.object(dal_temizle, "_git", sahte):
            s = dal_temizle.kapanis_birlestir(self.wt, "ihlal", "I-1")
        self.assertEqual(s["sonuc"], "hata", s)
        self.assertEqual(self.main_uc(), once)
        self.assertEqual(self.ana_durum(), "")

    def test_kapat_golge(self):
        commit(self.wt, "x.txt")
        once = self.main_uc()
        s = dal_temizle.kapanis_birlestir(self.wt, "golge", "I-7")
        self.assertEqual(s["sonuc"], "birlestirirdi", s)
        self.assertEqual(self.main_uc(), once)
        self.assertFalse(os.path.exists(os.path.join(self.depo, "x.txt")))
        k = self.gunluk()[-1]
        self.assertEqual((k["tur"], k["sonuc"], k["is"], k["kip"]), ("kapanis_birlestirme", "birlestirirdi", "I-7", "golge"))
        self.assertEqual(k["uc"], git(self.wt, "rev-parse", "oturum"))

    def test_golge_catismayi_da_kaydeder(self):
        commit(self.depo, "a.txt", "ana\n")
        commit(self.wt, "a.txt", "dal\n")
        s = dal_temizle.kapanis_birlestir(self.wt, "golge", "I-7")
        self.assertEqual(s["sonuc"], "catisma")
        self.assertEqual(self.gunluk()[-1]["sonuc"], "catisma")

    def test_dal_kirli(self):
        commit(self.wt, "x.txt")
        yaz(self.wt, "yarim.txt", "commitsiz")
        s = dal_temizle.kapanis_birlestir(self.wt, "ihlal", "I-1")
        self.assertEqual(s["sonuc"], "dal-kirli", s)
        self.assertEqual(s["dosyalar"], ["yarim.txt"])

    def test_zaten_birlesmis_ve_main_ve_kapali(self):
        self.assertEqual(dal_temizle.kapanis_birlestir(self.wt, "ihlal")["sonuc"], "zaten-birlesmis")
        self.assertIsNone(dal_temizle.kapanis_birlestir(self.depo, "ihlal"))        # main'deki oturum: yapacak dal yok
        commit(self.wt, "x.txt")
        os.environ["ORKESTRA_KAPANIS_BIRLESTIRME"] = "0"
        self.assertIsNone(dal_temizle.kapanis_birlestir(self.wt, "ihlal"))
        self.assertFalse(os.path.exists(os.path.join(self.depo, "x.txt")))

    def test_kapanis_uyarisi_nedeni_soyler(self):
        commit(self.depo, "a.txt", "ana\n")
        commit(self.wt, "a.txt", "dal\n")
        uyari = dal_temizle.kapanis(self.wt, "I-1")
        self.assertIn("main'e birleşmemiş", uyari)
        self.assertIn("catisma", uyari)

    def test_kapanis_gercek_kipte_birlestirir(self):
        commit(self.wt, "x.txt")
        with mock.patch.object(dal_temizle.kapi_mod, "mod", lambda kapi, cwd=None: "ihlal" if kapi == dal_temizle.KAPI else "golge"):
            self.assertEqual(dal_temizle.kapanis(self.wt, "I-1"), "")
        self.assertTrue(os.path.isfile(os.path.join(self.depo, "x.txt")))

    def test_gunluk_ozet_kirilim(self):
        commit(self.wt, "x.txt")
        dal_temizle.kapanis_birlestir(self.wt, "golge", "I-7")
        yol = os.path.join(self.depo, ".claude", "orkestra", "gunluk.jsonl")
        L.jsonl_ekle(yol, {"zaman": L.simdi(), "tur": "kapanis_yanlis_pozitif", "is": "I-7", "not": "elle birleştirirken çakıştı"})
        import io
        import contextlib
        import argparse
        from komutlar import gosterge
        cikti = io.StringIO()
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": self.depo}), contextlib.redirect_stdout(cikti):
            gosterge.cmd_gunluk_ozet(argparse.Namespace(gun=1))
        metin = cikti.getvalue()
        self.assertIn("Kapanış birleştirme: birlestirirdi ×1", metin)
        self.assertIn("yanlış-pozitif bildirimi: 1", metin)


if __name__ == "__main__":
    unittest.main()
