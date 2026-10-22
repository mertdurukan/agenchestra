"""Teslim kapısı (ADR-0035, P3): kod değişikliği taşıyan işin kapanışında PR, CI ve inceleme kaydı.
Geçici git deposunda koşar; `gh` çağrısı taklit edilir (ağ yok)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import kapi_mod as KM  # noqa: E402
import teslim as T  # noqa: E402

ESKI = "2000-01-01T00:00:00+00:00"


def git(kok, *args):
    subprocess.run(["git", "-C", kok, *args], check=True, capture_output=True, text=True)


def pr(ci="SUCCESS", karar="", url="https://github.com/x/y/pull/1"):
    return {"statusCheckRollup": [{"conclusion": ci, "status": "COMPLETED"}] if ci else [], "reviewDecision": karar,
            "state": "OPEN", "url": url}


class Teslim(unittest.TestCase):
    def setUp(self):
        self.kok = tempfile.mkdtemp(prefix="ork_teslim_")
        self.addCleanup(shutil.rmtree, self.kok, True)
        git(self.kok, "init", "-q")
        git(self.kok, "config", "user.email", "t@t")
        git(self.kok, "config", "user.name", "t")
        self.klasor = os.path.join(self.kok, "is1")
        os.makedirs(self.klasor)
        with open(os.path.join(self.klasor, "todo.md"), "w", encoding="utf-8") as f:
            f.write("x")
        git(self.kok, "add", "-A")
        git(self.kok, "commit", "-qm", "ilk")
        self.kayit = {"id": "I-1", "klasor": self.klasor, "olusturma": ESKI}
        env = mock.patch.dict(os.environ, {"ORKESTRA_TESLIM_KAPISI": "1"})
        env.start()
        self.addCleanup(env.stop)

    def uzak_ekle(self):
        git(self.kok, "remote", "add", "origin", "https://example.invalid/x/y.git")

    def kod_yaz(self, ad="modul/a.py"):
        yol = os.path.join(self.kok, ad)
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with open(yol, "w", encoding="utf-8") as f:
            f.write("x = 1\n")

    def eksik(self, mod="ihlal", pr_degeri=None):
        with mock.patch.object(KM, "mod", return_value=mod), mock.patch.object(KM, "kaydet") as kayit, \
                mock.patch.object(T, "pr_oku", return_value=pr_degeri):
            sonuc = T.teslim_eksigi(self.kok, self.kayit)
        return sonuc, kayit

    def test_uzak_deposuz_proje_muaf(self):
        self.kod_yaz()
        self.assertEqual(self.eksik()[0], [])

    def test_kod_degismediyse_muaf(self):
        self.uzak_ekle()
        self.assertEqual(self.eksik()[0], [])

    def test_kapi_kapaliysa_muaf(self):
        self.uzak_ekle()
        self.kod_yaz()
        with mock.patch.dict(os.environ, {"ORKESTRA_TESLIM_KAPISI": "0"}):
            self.assertEqual(self.eksik()[0], [])

    def test_yeni_klasordeki_kod_sayilir_belge_ve_adr_sayilmaz(self):
        self.kod_yaz("yeni_klasor/b.py")
        self.kod_yaz("is1/arac.py")
        self.kod_yaz("adr/ornek.py")
        self.assertEqual(T.kod_dosyalari(self.kok, self.klasor, ESKI), ["yeni_klasor/b.py"])

    def test_pr_yoksa_ihlal_modunda_eksik(self):
        self.uzak_ekle()
        self.kod_yaz()
        sonuc, _ = self.eksik("ihlal", None)
        self.assertEqual(len(sonuc), 1)
        self.assertIn("PR bulunamadı", sonuc[0])

    def test_pr_yoksa_golge_modunda_uyarir_engellemez(self):
        self.uzak_ekle()
        self.kod_yaz()
        sonuc, _ = self.eksik("golge", None)
        self.assertEqual(sonuc, [])

    def test_ci_kirmizi_reddedilir(self):
        self.uzak_ekle()
        self.kod_yaz()
        self.kayit["teslim"] = {"inceleme": "denetçi"}
        sonuc, _ = self.eksik("ihlal", pr("FAILURE"))
        self.assertEqual(len(sonuc), 1)
        self.assertIn("CI sonucu başarısız", sonuc[0])

    def test_inceleme_yoksa_reddedilir_github_onayi_yeter(self):
        self.uzak_ekle()
        self.kod_yaz()
        sonuc, _ = self.eksik("ihlal", pr("SUCCESS"))
        self.assertTrue(any("inceleme" in e for e in sonuc), sonuc)
        self.assertEqual(self.eksik("ihlal", pr("SUCCESS", "APPROVED"))[0], [])

    def test_inceleme_kaydi_yeter(self):
        self.uzak_ekle()
        self.kod_yaz()
        self.kayit["teslim"] = {"inceleme": "orkestra:denetci onayladı"}
        self.assertEqual(self.eksik("ihlal", pr("SUCCESS"))[0], [])

    def test_ascii_disi_dosya_adi_kod_sayilir(self):
        self.kod_yaz("modul/çö.py")
        git(self.kok, "add", "-A")
        git(self.kok, "commit", "-qm", "kod")
        self.assertEqual(T.kod_dosyalari(self.kok, self.klasor, ESKI), ["modul/çö.py"])

    def test_alt_projedeki_claude_klasoru_sayilmaz(self):
        self.kod_yaz("alt/.claude/hook.py")
        self.assertEqual(T.kod_dosyalari(self.kok, self.klasor, ESKI), [])

    def test_kapatilmis_pr_reddedilir(self):
        self.uzak_ekle()
        self.kod_yaz()
        self.kayit["teslim"] = {"inceleme": "x"}
        degerler = dict(pr("SUCCESS"), state="CLOSED")
        self.assertTrue(any("kapatılmış" in e for e in self.eksik("ihlal", degerler)[0]))

    def test_bilinmeyen_ci_sonucu_yesil_sayilmaz(self):
        self.assertEqual(T.ci_durumu([{"conclusion": "STALE", "status": "COMPLETED"}]), "bekliyor")

    def test_gh_yoksa_dogrulanamadi_denir(self):
        self.uzak_ekle()
        self.kod_yaz()
        with mock.patch.object(T.shutil, "which", return_value=None):
            sonuc, _ = self.eksik("ihlal", None)
        self.assertIn("doğrulanamadı", sonuc[0])

    def test_ayni_golge_kaydi_tekrarlanmaz(self):
        sd = os.path.join(self.kok, ".claude", "orkestra")
        os.makedirs(sd)
        with mock.patch.object(KM.L, "durum_dizini", return_value=sd):
            self.assertTrue(KM.kaydet(self.klasor, "teslim", "eksik a"))
            self.assertFalse(KM.kaydet(self.klasor, "teslim", "eksik a"))
            self.assertTrue(KM.kaydet(self.klasor, "teslim", "eksik b"))
        with open(os.path.join(sd, "gunluk.jsonl"), encoding="utf-8") as f:
            self.assertEqual(len(f.readlines()), 2)

    def test_ci_durumu_bicimleri(self):
        self.assertEqual(T.ci_durumu(None), "yok")
        self.assertEqual(T.ci_durumu([]), "yok")
        self.assertEqual(T.ci_durumu([{"conclusion": "SUCCESS", "status": "COMPLETED"}, {"state": "SUCCESS"}]), "yesil")
        self.assertEqual(T.ci_durumu([{"conclusion": "", "status": "IN_PROGRESS"}]), "bekliyor")
        self.assertEqual(T.ci_durumu([{"conclusion": "SUCCESS"}, {"state": "FAILURE"}]), "kirmizi")

    def test_pr_oku_gh_ciktisini_ayristirir(self):
        yanit = subprocess.CompletedProcess([], 0, json.dumps(pr()), "")
        with mock.patch.object(T, "_gh", return_value=yanit) as gh:
            self.assertEqual(T.pr_oku("5", self.kok)["state"], "OPEN")
            self.assertEqual(gh.call_args.args[0][:3], ["pr", "view", "5"])
        with mock.patch.object(T, "_gh", return_value=subprocess.CompletedProcess([], 1, "", "yok")):
            self.assertIsNone(T.pr_oku("", self.kok))


if __name__ == "__main__":
    unittest.main()
