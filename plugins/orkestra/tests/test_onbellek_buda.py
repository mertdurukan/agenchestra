"""I-271 P8: `orkestra guncelle` sonrası eklenti önbelleği budaması ve `orkestra bakim` worktree geride uyarısı.

Tüm testler geçici dizin kullanır; gerçek ~/.claude önbelleğine dokunulmaz (ev parametresi tmp).
"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import guncelle as G  # noqa: E402
import test_cekirdek as TC  # noqa: E402
from komutlar import bakim as B  # noqa: E402

ANA = {"ajan_id": "ana", "ajan_tipi": "ana"}


def yaz(yol, metin="x"):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8") as f:
        f.write(metin)


class OnbellekBuda(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ev = os.path.join(self.tmp.name, "ev")
        self.kok = G.onbellek_koku(self.ev)
        self.eklenti = os.path.join(self.kok, "orkestra")
        self.cikti = []

    def surum(self, ad, yas_saat, eklenti="orkestra"):
        y = os.path.join(self.kok, eklenti, ad)
        yaz(os.path.join(y, "scripts", "a.py"), "print(1)\n")
        t = time.time() - yas_saat * 3600
        os.utime(y, (t, t))
        return y

    def kurulu(self, yol, ad="orkestra@claude-orchestration"):
        yaz(os.path.join(self.ev, ".claude", "plugins", "installed_plugins.json"),
            json.dumps({"version": 2, "plugins": {ad: [{"scope": "user", "version": "x", "installPath": yol}]}}))

    def buda(self, **k):
        return G.onbellek_buda(self.ev, ortam={}, yaz=self.cikti.append, **k)

    def kalan(self, eklenti="orkestra"):
        return sorted(os.listdir(os.path.join(self.kok, eklenti)))

    def test_k1_etkin_ve_en_yeni_3_kalir_digerleri_silinir(self):
        for i in range(7):  # s0 en yeni ... s6 en eski
            self.surum(f"s{i}", yas_saat=i + 1)
        self.kurulu(os.path.join(self.eklenti, "s0"))
        r = self.buda(tut=3)
        self.assertEqual(self.kalan(), ["s0", "s1", "s2", "s3"])
        self.assertEqual(sorted(a["ad"] for a in r["silinen"]), ["s4", "s5", "s6"])
        self.assertEqual(r["hata"], [])

    def test_k1_esik_ayardan_okunur(self):
        ayar = os.path.join(self.tmp.name, "onbellek_buda.json")
        yaz(ayar, json.dumps({"tutulacak_son_surum": 1}))
        self.assertEqual(G.buda_esigi(ayar), 1)
        self.assertEqual(G.buda_esigi(os.path.join(self.tmp.name, "yok.json")), 3)
        with open(G.BUDA_AYAR, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["tutulacak_son_surum"], 3)

    def test_k2_etkin_surum_esik_disinda_olsa_da_silinmez(self):
        for i in range(6):
            self.surum(f"s{i}", yas_saat=i + 1)
        self.kurulu(os.path.join(self.eklenti, "s5"))  # en eski sürüm etkin
        self.buda(tut=3)
        self.assertEqual(self.kalan(), ["s0", "s1", "s2", "s5"])

    def test_k2_kullanimdaki_ve_calisan_kopya_silinmez(self):
        for i in range(6):
            self.surum(f"s{i}", yas_saat=i + 1)
        self.kurulu(os.path.join(self.eklenti, "s0"))
        yaz(os.path.join(self.eklenti, "s4", ".in_use", "1234"), "")
        G.onbellek_buda(self.ev, ortam={"CLAUDE_PLUGIN_ROOT": os.path.join(self.eklenti, "s5")}, tut=1, yaz=self.cikti.append)
        self.assertEqual(self.kalan(), ["s0", "s1", "s4", "s5"])

    def test_k2_her_eklenti_ayri_budanir_ve_kuru_kosu_silmez(self):
        for i in range(5):
            self.surum(f"s{i}", yas_saat=i + 1)
            self.surum(f"u{i}", yas_saat=i + 1, eklenti="orkestra-ui")
        self.kurulu(os.path.join(self.eklenti, "s0"))
        r = self.buda(tut=1, kuru=True)
        self.assertEqual(len(r["aday"]), 7)  # orkestra: s2-s4 (3), orkestra-ui: etkin yok, u1-u4 (4)
        self.assertEqual(r["silinen"], [])
        self.assertIsNone(r["manifest"])
        self.assertEqual(len(self.kalan()), 5)

    def test_k3_onbellek_koku_disi_yol_reddedilir(self):
        disari = os.path.join(self.tmp.name, "baska", "klasor")
        os.makedirs(disari)
        os.makedirs(self.eklenti)
        for yol in (disari, self.kok, os.path.join(self.kok, "..", "..", "baska"), self.eklenti):
            with self.assertRaises(ValueError):
                G.onbellek_klasoru_sil(self.kok, yol)
        self.assertTrue(os.path.isdir(disari))
        self.assertTrue(os.path.isdir(self.eklenti))
        s = self.surum("s9", 1)
        G.onbellek_klasoru_sil(self.kok, s)
        self.assertFalse(os.path.exists(s))

    def test_k4_manifest_silmeden_once_yazilir(self):
        for i in range(5):
            self.surum(f"s{i}", yas_saat=i + 1)
        self.kurulu(os.path.join(self.eklenti, "s0"))
        r = self.buda(tut=3)
        mf = os.path.join(self.ev, ".claude", "orkestra-makine", G.BUDA_MANIFEST)
        self.assertEqual(r["manifest"], mf)
        with open(mf, encoding="utf-8") as f:
            kayit = json.loads(f.read().splitlines()[-1])
        self.assertEqual([k["ad"] for k in kayit["klasorler"]], ["s4"])
        k = kayit["klasorler"][0]
        self.assertEqual(set(k), {"eklenti", "ad", "boyut", "tarih"})
        self.assertGreater(k["boyut"], 0)
        self.assertIn("yeniden indir", kayit["geri_alma"])

    def test_k4_manifest_yazilamazsa_hicbir_sey_silinmez(self):
        for i in range(5):
            self.surum(f"s{i}", yas_saat=i + 1)
        engel = os.path.join(self.tmp.name, "dosya")
        yaz(engel)  # manifest dizini yerine dosya: makedirs başarısız
        with self.assertRaises(OSError):
            self.buda(tut=1, manifest_dizini=engel)
        self.assertEqual(len(self.kalan()), 5)

    def test_onbellek_yoksa_sessiz(self):
        self.assertEqual(self.buda(tut=3)["silinen"], [])
        self.assertEqual(self.cikti, [])


import test_guncelle as TG  # noqa: E402


class GuncelleBudar(TG.Ortam):
    def test_guncelle_sonrasi_onbellek_budanir(self):
        kok = os.path.join(G.onbellek_koku(self.ev), "orkestra")
        for i in range(6):
            y = os.path.join(kok, f"s{i}")
            yaz(os.path.join(y, "a.txt"))
            t = time.time() - (i + 1) * 3600
            os.utime(y, (t, t))
        kod, cikti = self.kos()
        self.assertEqual(kod, 0, cikti)
        self.assertEqual(sorted(os.listdir(kok)), ["s0", "s1", "s2"])  # installPath yok: en yeni 3 kalır
        self.assertIn("Önbellek budama: 3 eski sürüm", cikti)


class WorktreeGeride(unittest.TestCase):
    """K5: bakim, worktree durum kopyası ana kopyadan geride ise tek satır uyarı yazar."""
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown
    cli = TC.Cekirdek.cli

    def agac_kur(self, ana_gunluk, wt_gunluk, ana_maliyet=0, wt_maliyet=0):
        self.ana = tempfile.mkdtemp(prefix="ork_ana_")
        self.addCleanup(shutil.rmtree, self.ana, True)
        os.makedirs(os.path.join(self.ana, ".git", "worktrees", "wt"))
        ana_sd = os.path.join(self.ana, ".claude", "orkestra")
        yaz(os.path.join(ana_sd, "gunluk.jsonl"), "{}\n" * ana_gunluk)
        yaz(os.path.join(ana_sd, "maliyet.jsonl"), "{}\n" * ana_maliyet)
        yaz(os.path.join(self.proje, ".git"), "gitdir: " + os.path.join(self.ana, ".git", "worktrees", "wt") + "\n")
        yaz(os.path.join(self.sd, "gunluk.jsonl"), "{}\n" * wt_gunluk)
        yaz(os.path.join(self.sd, "maliyet.jsonl"), "{}\n" * wt_maliyet)

    def bakim_cikti(self):
        r = self.cli("bakim", **ANA)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def test_k5_farkta_uyari_yazar(self):
        self.agac_kur(ana_gunluk=5, wt_gunluk=2, ana_maliyet=4, wt_maliyet=1)
        self.assertEqual(B.worktree_geride_uyari(self.proje), "worktree geride: gunluk 3, maliyet 3 satır")
        self.assertIn("worktree geride: gunluk 3, maliyet 3 satır", self.bakim_cikti())

    def test_k5_farksizda_yazmaz(self):
        self.agac_kur(ana_gunluk=2, wt_gunluk=2, ana_maliyet=1, wt_maliyet=1)
        self.assertEqual(B.worktree_geride_uyari(self.proje), "")
        self.assertNotIn("worktree geride", self.bakim_cikti())

    def test_k5_worktree_degilse_sessiz(self):
        self.assertEqual(B.worktree_geride_uyari(self.proje), "")
        self.assertNotIn("worktree geride", self.bakim_cikti())


if __name__ == "__main__":
    unittest.main()
