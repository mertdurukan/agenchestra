"""Artık dal temizliği (I-201): birleşmiş dal adaydır, birleşmemiş ve worktree'de açık dal korunur, ihlal kipi yedekleyip siler."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import dal_temizle  # noqa: E402


def git(yol, *a):
    return subprocess.run(["git", "-C", yol, "-c", "user.name=t", "-c", "user.email=t@t", *a],
                          capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()


def commit(yol, ad):
    with open(os.path.join(yol, ad), "w", encoding="utf-8") as f:
        f.write(ad)
    git(yol, "add", ".")
    git(yol, "commit", "-q", "-m", ad)


class DalTemizleTest(unittest.TestCase):
    def setUp(self):
        self.k = tempfile.mkdtemp()
        self.depo = os.path.join(self.k, "depo")
        os.makedirs(self.depo)
        git(self.depo, "init", "-q", "-b", "main")
        commit(self.depo, "a")
        git(self.depo, "branch", "birlesmis")                    # main ile aynı uç: birleşmiş
        git(self.depo, "checkout", "-q", "-b", "yeni")
        commit(self.depo, "b")                                   # main'de olmayan commit
        git(self.depo, "checkout", "-q", "main")
        git(self.depo, "branch", "oturum")                       # çağıran oturumun dalı
        wt = os.path.join(self.k, "wt")
        git(self.depo, "worktree", "add", "-q", "-b", "acik", wt)  # worktree'de açık, birleşmiş
        self.wt = wt

    def tearDown(self):
        shutil.rmtree(self.k, ignore_errors=True)

    def test_adaylar(self):
        a = dal_temizle.adaylar(self.depo, "oturum")
        self.assertEqual(a["aday"], ["birlesmis"])
        self.assertEqual(a["birlesmemis"], ["yeni"])

    def test_golge_silmez(self):
        s = dal_temizle.temizle(self.depo, "oturum", "golge")
        self.assertEqual(s["aday"], ["birlesmis"])
        self.assertEqual(s["silinen"], [])
        self.assertIn("birlesmis", git(self.depo, "branch", "--list", "birlesmis"))

    def test_ihlal_yedekler_ve_siler(self):
        s = dal_temizle.temizle(self.depo, "oturum", "ihlal")
        self.assertEqual(s["silinen"], ["birlesmis"])
        self.assertTrue(os.path.isfile(s["bundle"]))
        self.assertEqual(git(self.depo, "branch", "--list", "birlesmis"), "")
        self.assertNotEqual(git(self.depo, "branch", "--list", "yeni"), "")      # birleşmemiş durur
        self.assertNotEqual(git(self.depo, "branch", "--list", "oturum"), "")    # oturum dalı durur
        self.assertNotEqual(git(self.depo, "branch", "--list", "acik"), "")      # worktree'de açık durur
        self.assertIn("birlesmis", git(self.depo, "bundle", "list-heads", s["bundle"]))

    def test_hata_istisna_firlatmaz(self):
        s = dal_temizle.temizle(os.path.join(self.k, "yok"), "", "ihlal")
        self.assertEqual(s["silinen"], [])

    def test_kapanis_birlesmemis_dal_uyarir(self):
        git(self.depo, "checkout", "-q", "yeni")                 # HEAD main'e birleşmemiş
        self.assertIn("main'e birleşmemiş", dal_temizle.kapanis(self.depo))
        git(self.depo, "checkout", "-q", "-b", "yeni2", "main")  # HEAD birleşmiş: uyarı yok (kip ihlal olsa da çağıranın dalı silinmez)
        self.assertEqual(dal_temizle.kapanis(self.depo), "")

    def test_session_start_cagrisi_hata_vermez(self):
        s = dal_temizle.calistir(os.path.join(self.k, "yok"))      # git deposu değil: istisna yok, silme yok
        self.assertEqual((s or {}).get("silinen", []), [])

    def test_kapali(self):
        os.environ["ORKESTRA_DAL_TEMIZLE"] = "0"
        try:
            self.assertIsNone(dal_temizle.calistir(self.depo))
        finally:
            del os.environ["ORKESTRA_DAL_TEMIZLE"]


class AgacTemizleTest(unittest.TestCase):
    """I-225 (ADR-0086): birleşmiş, temiz, kilitsiz, açık işi olmayan, atıl worktree yedekten sonra kalkar."""

    def setUp(self):
        self._ortam = os.environ.pop("CLAUDE_PROJECT_DIR", None)
        os.environ.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        # realpath: Windows runner'da TMP 8.3 kısa ad (RUNNER~1) verir; kod git'in uzun yolunu döndürür (I-450)
        self.k = os.path.realpath(tempfile.mkdtemp())
        self.depo = os.path.join(self.k, "depo")
        os.makedirs(self.depo)
        git(self.depo, "init", "-q", "-b", "main")
        commit(self.depo, "a")
        self.oturum = os.path.join(self.k, "oturum")                       # çağıran oturumun worktree'si
        git(self.depo, "worktree", "add", "-q", "-b", "oturum", self.oturum)
        self.bitmis = os.path.join(self.k, "bitmis")                       # main'e birleşmiş eski worktree
        git(self.depo, "worktree", "add", "-q", "-b", "bitmis", self.bitmis)
        self.gelecek = __import__("time").time() + 48 * 3600               # "48 saat sonra": atıl eşiğini aşar

    def tearDown(self):
        if self._ortam is not None:
            os.environ["CLAUDE_PROJECT_DIR"] = self._ortam
        shutil.rmtree(self.k, ignore_errors=True)

    def temizle(self, kip="ihlal", simdi=None):
        return dal_temizle.agaclar_temizle(self.oturum, "oturum", kip, self.gelecek if simdi is None else simdi)

    def neden(self, s, yol):
        return [x["neden"] for x in s["atlanan"] if os.path.normcase(x["yol"]) == os.path.normcase(yol.replace("\\", "/"))]

    def test_kalkar_ve_yedeklenir(self):
        s = self.temizle()
        self.assertEqual(len(s["kaldirilan"]), 1, s)
        self.assertFalse(os.path.isdir(self.bitmis))
        self.assertEqual(git(self.depo, "branch", "--list", "bitmis"), "")
        self.assertTrue(os.path.isfile(s["bundle"]))
        self.assertIn("bitmis", git(self.depo, "bundle", "list-heads", s["bundle"]))
        self.assertTrue(os.path.isdir(self.oturum))                         # çağıran oturumun klasörü durur

    def test_golge_kaldirmaz(self):
        s = self.temizle("golge")
        self.assertEqual(len(s["aday"]), 1)
        self.assertEqual(s["kaldirilan"], [])
        self.assertTrue(os.path.isdir(self.bitmis))

    def test_kirli_kalkmaz(self):
        with open(os.path.join(self.bitmis, "yarim.txt"), "w", encoding="utf-8") as f:
            f.write("commitsiz")
        s = self.temizle()
        self.assertEqual(s["kaldirilan"], [])
        self.assertEqual([x["neden"] for x in s["atlanan"]], ["kirli"])
        self.assertTrue(os.path.isdir(self.bitmis))

    def test_kilitli_kalkmaz(self):
        git(self.depo, "worktree", "lock", self.bitmis)
        s = self.temizle()
        self.assertEqual([x["neden"] for x in s["atlanan"]], ["kilitli"])
        self.assertTrue(os.path.isdir(self.bitmis))

    def test_guncel_kalkmaz(self):
        s = self.temizle(simdi=__import__("time").time())
        self.assertEqual([x["neden"] for x in s["atlanan"]], ["guncel"])
        self.assertTrue(os.path.isdir(self.bitmis))

    def test_birlesmemis_kalkmaz(self):
        commit(self.bitmis, "yeni")
        s = self.temizle()
        self.assertEqual([x["neden"] for x in s["atlanan"]], ["birlesmemis"])
        self.assertTrue(os.path.isdir(self.bitmis))

    def test_acik_is_kaydi_olan_kalkmaz(self):
        sd = os.path.join(self.depo, ".claude", "orkestra")
        os.makedirs(sd)
        with open(os.path.join(sd, "isler.json"), "w", encoding="utf-8") as f:
            f.write('{"isler": {"I-9": {"durum": "acik", "klasor": %s}}}' % __import__("json").dumps(os.path.join(self.bitmis, "09-is")))
        s = self.temizle()
        self.assertEqual([x["neden"] for x in s["atlanan"]], ["acik-is"])
        self.assertTrue(os.path.isdir(self.bitmis))

    def test_devralinmamis_durum_kopyasi_olan_kalkmaz(self):
        kopya = os.path.join(self.bitmis, ".claude", "orkestra")
        os.makedirs(kopya)
        os.makedirs(os.path.join(self.depo, ".claude", "orkestra"))
        with unittest.mock.patch.object(dal_temizle.L, "oturum_devralinmamis", lambda depo, agac: 3):
            s = self.temizle()
        self.assertEqual([x["neden"] for x in s["atlanan"]], ["devralinmamis"])
        self.assertTrue(os.path.isdir(self.bitmis))

    def test_yedek_yoksa_kalkmaz(self):
        with unittest.mock.patch.object(dal_temizle, "_yedekle", lambda *a: ""):
            s = self.temizle()
        self.assertEqual(s["kaldirilan"], [])
        self.assertIn("bundle", s["hata"])
        self.assertTrue(os.path.isdir(self.bitmis))
        self.assertNotEqual(git(self.depo, "branch", "--list", "bitmis"), "")

    # ---- I-433: iş belgesi koruması
    def belge(self, *parca, icerik="x"):
        yol = os.path.join(self.bitmis, *parca)
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with open(yol, "w", encoding="utf-8") as f:
            f.write(icerik)
        return yol

    def belgeler(self, s):
        return sorted(os.path.normcase(os.path.normpath(b)) for x in s["atlanan"] for b in x.get("belgeler", []))

    def norm(self, *yollar):
        return sorted(os.path.normcase(os.path.normpath(y)) for y in yollar)

    def test_kayitli_is_klasorunde_commitsiz_belge_kalkmaz(self):
        sd = os.path.join(self.depo, ".claude", "orkestra")
        os.makedirs(sd)
        klasor = os.path.join(self.bitmis, "Is", "101-is")
        with open(os.path.join(sd, "isler.json"), "w", encoding="utf-8") as f:   # kapanmış iş: acik-is koruması devreye girmez
            f.write('{"isler": {"I-1": {"durum": "kapandi", "klasor": %s}}}' % __import__("json").dumps(klasor))
        plan = self.belge("Is", "101-is", "plan.md")
        mevcut = self.belge("Is", "101-is", "mevcut_durum_20261109.md")
        self.belge("Is", "101-is", "notlar.txt")                               # belge değil: listede yok
        s = self.temizle()
        self.assertEqual(self.neden(s, self.bitmis), ["is-belgesi"])
        self.assertEqual(self.belgeler(s), self.norm(mevcut, plan))
        self.assertEqual(s["kaldirilan"], [])
        self.assertTrue(os.path.isfile(plan))

    def test_birlesmemis_dalda_commitli_belge_kalkmaz_ve_listelenir(self):
        isj = self.belge("Is", "102-is", "is.json", icerik="{}")
        todo = self.belge("Is", "102-is", "todo.md")
        git(self.bitmis, "add", ".")
        git(self.bitmis, "commit", "-q", "-m", "belgeler")                    # isler.json kaydı yok; is.json ile bulunur
        s = self.temizle()
        self.assertEqual(self.neden(s, self.bitmis), ["is-belgesi"])
        self.assertEqual(self.belgeler(s), self.norm(isj, todo))
        self.assertTrue(os.path.isdir(self.bitmis))

    def test_ignore_edilmis_belge_kalkmaz(self):
        self.belge(".gitignore", icerik="gizli/\n")
        git(self.bitmis, "add", ".")
        git(self.bitmis, "commit", "-q", "-m", "ignore")
        git(self.depo, "merge", "-q", "bitmis")                               # dal birleşmiş, worktree git'e göre temiz
        sozlesme = self.belge("gizli", "103-is", "sozlesme_v1.md")
        self.belge("gizli", "103-is", "is.json", icerik="{}")
        s = self.temizle()
        self.assertEqual(self.neden(s, self.bitmis), ["is-belgesi"])
        self.assertIn(os.path.normcase(os.path.normpath(sozlesme)), self.belgeler(s))
        self.assertTrue(os.path.isdir(self.bitmis))

    def test_belgeleri_mainde_olan_kalkar(self):
        self.belge("Is", "104-is", "is.json", icerik="{}")
        self.belge("Is", "104-is", "plan.md")
        git(self.bitmis, "add", ".")
        git(self.bitmis, "commit", "-q", "-m", "belgeler")
        git(self.depo, "merge", "-q", "bitmis")
        s = self.temizle()
        self.assertEqual(s["atlanan"], [])
        self.assertEqual(len(s["kaldirilan"]), 1, s)
        self.assertFalse(os.path.isdir(self.bitmis))
        self.assertTrue(os.path.isfile(os.path.join(self.depo, "Is", "104-is", "plan.md")))

    def test_belge_atlamasi_gunluge_yazilir(self):
        sd = os.path.join(self.k, "durum")
        os.makedirs(sd)
        plan = self.belge("Is", "105-is", "plan.md")
        self.belge("Is", "105-is", "is.json", icerik="{}")
        with unittest.mock.patch.object(dal_temizle.L, "durum_dizini", lambda *a: sd), \
                unittest.mock.patch.object(dal_temizle.kapi_mod, "mod", lambda *a: "ihlal"), \
                unittest.mock.patch.object(dal_temizle.time, "time", lambda: self.gelecek):
            dal_temizle._agaclari_calistir(self.oturum, "oturum", "test")
        with open(os.path.join(sd, "gunluk.jsonl"), encoding="utf-8") as f:
            kayit = __import__("json").loads(f.read().strip().splitlines()[-1])
        self.assertEqual(kayit["tur"], "worktree_temizle")
        self.assertEqual(kayit["atlanan"][0]["neden"], "is-belgesi")
        self.assertIn(os.path.normcase(os.path.normpath(plan)), [os.path.normcase(os.path.normpath(b)) for b in kayit["atlanan"][0]["belgeler"]])
        self.assertTrue(os.path.isdir(self.bitmis))

    def test_calistir_guncel_worktree_dokunmaz(self):
        sd = os.path.join(self.depo, ".claude", "orkestra")
        os.makedirs(sd)
        # worktree'nin commit ve dosya zamanları yeni: atıl değil, hiçbir kipte kalkmaz
        dal_temizle.calistir(self.depo, "main", "test")
        self.assertTrue(os.path.isdir(self.bitmis))


if __name__ == "__main__":
    unittest.main()
