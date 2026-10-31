"""Korunan deponun birincil main kopyasına yazma kapısı (I-302, ADR-0122): gerçek git depoları ve çalışma ağaçlarıyla."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import hook  # noqa: E402
import main_kopya_kapisi as mk  # noqa: E402


def git(yol, *a):
    return subprocess.run(["git", "-C", yol, "-c", "user.name=t", "-c", "user.email=t@t", *a],
                          capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()


class Reddedildi(Exception):
    pass


class MainKopyaKapisi(unittest.TestCase):
    def setUp(self):
        self.k = tempfile.mkdtemp()
        self.depo = os.path.join(self.k, "depo")
        os.makedirs(self.depo)
        git(self.depo, "init", "-q", "-b", "main")
        with open(os.path.join(self.depo, "a.txt"), "w", encoding="utf-8") as f:
            f.write("a")
        git(self.depo, "add", ".")
        git(self.depo, "commit", "-q", "-m", "a")
        self.wt = os.path.join(self.k, "wt")
        git(self.depo, "worktree", "add", "-q", "-b", "is", self.wt)
        self.baska = os.path.join(self.k, "baska")
        os.makedirs(self.baska)
        git(self.baska, "init", "-q", "-b", "main")
        self.korunan = [self.depo]

    def tearDown(self):
        shutil.rmtree(self.k, ignore_errors=True)

    def test_birincil_kopya_yakalanir_yeni_dosya_dahil(self):
        for ad in ("a.txt", os.path.join("alt", "yeni.py")):
            self.assertEqual(os.path.normcase(mk.birincil_kopya(os.path.join(self.depo, ad), self.korunan)),
                             os.path.normcase(self.depo))

    def test_eğik_cizgi_ve_buyuk_harf_farki_yakalanir(self):
        yol = os.path.join(self.depo, "a.txt").replace("\\", "/").upper() if os.name == "nt" else os.path.join(self.depo, "a.txt")
        self.assertIsNotNone(mk.birincil_kopya(yol, self.korunan))

    def test_ayri_calisma_agaci_gecer(self):
        self.assertTrue(os.path.isfile(os.path.join(self.wt, ".git")))
        self.assertIsNone(mk.birincil_kopya(os.path.join(self.wt, "a.txt"), [self.depo, self.wt]))

    def test_main_disi_dalda_birincil_kopya_gecer(self):
        git(self.depo, "checkout", "-q", "-b", "baska-dal")
        self.assertIsNone(mk.birincil_kopya(os.path.join(self.depo, "a.txt"), self.korunan))

    def test_korunmayan_depo_gecer(self):
        self.assertIsNone(mk.birincil_kopya(os.path.join(self.baska, "x.txt"), self.korunan))

    def test_bos_ayar_ve_git_disi_yol_gecer(self):
        self.assertIsNone(mk.birincil_kopya(os.path.join(self.depo, "a.txt"), []))
        self.assertIsNone(mk.birincil_kopya(os.path.join(tempfile.gettempdir(), "git-degil-xyz", "a.txt"), self.korunan))

    def test_env_kapatir(self):
        with unittest.mock.patch.object(mk, "_ayar_korunan", return_value=self.korunan), \
                unittest.mock.patch.dict(os.environ, {"ORKESTRA_MAIN_KOPYA_KAPISI": "0"}):
            self.assertIsNone(mk.karar(os.path.join(self.depo, "a.txt"), self.depo))

    def test_gomulu_varsayilan_golge_ayar_yoksa(self):
        import kapi_mod
        self.assertEqual(kapi_mod.mod("olmayan_kapi_xyz", self.depo), "golge")
        with open(os.path.join(KOK, "ayarlar", "main_kopya_kapisi.json"), encoding="utf-8") as f:
            self.assertIn('"mod": "golge"', f.read())

    def _hook(self, mod, yol, cwd=None):
        """_main_kopya_kapisi'ni sahte mod ve çıkış yakalayıcılarla koşar; (reddedilen, kaydedilen, uyarı)."""
        red, kayit = [], []

        def reddet(m):
            red.append(m)
            raise Reddedildi()

        hook._BEKLEYEN_UYARI = ""
        with unittest.mock.patch.object(mk, "_ayar_korunan", return_value=self.korunan), \
                unittest.mock.patch("kapi_mod.mod", return_value=mod), \
                unittest.mock.patch("kapi_mod.kaydet", side_effect=lambda *a: kayit.append(a) or True), \
                unittest.mock.patch.object(hook, "reddet", reddet):
            try:
                hook._main_kopya_kapisi({"cwd": cwd or self.depo, "session_id": "abcdef123456"}, {"file_path": yol}, "Edit")
            except Reddedildi:
                pass
        return red, kayit, hook._BEKLEYEN_UYARI

    def test_golgede_gecer_kaydeder_ve_uyarir(self):
        red, kayit, uyari = self._hook("golge", os.path.join(self.depo, "a.txt"))
        self.assertEqual(red, [])
        self.assertEqual(len(kayit), 1)
        self.assertEqual(kayit[0][1], "main_kopya_kapisi")
        self.assertIn("oturum=abcdef12", kayit[0][2])
        self.assertIn("worktree add", uyari)

    def test_ihlalde_reddeder_ve_worktree_yolunu_gosterir(self):
        red, kayit, _ = self._hook("ihlal", os.path.join(self.depo, "a.txt"))
        self.assertEqual(len(red), 1)
        self.assertIn("git -C", red[0])
        self.assertIn("worktree add", red[0])
        self.assertEqual(kayit, [])

    def test_ayri_agac_ve_korunmayan_depo_her_modda_gecer(self):
        for mod in ("golge", "ihlal"):
            for yol in (os.path.join(self.wt, "a.txt"), os.path.join(self.baska, "x.txt")):
                red, kayit, uyari = self._hook(mod, yol)
                self.assertEqual((red, kayit, uyari), ([], [], ""), (mod, yol))

    def test_multiedit_ve_yolsuz_cagri(self):
        hook._BEKLEYEN_UYARI = ""
        hook._main_kopya_kapisi({"cwd": self.depo}, {}, "MultiEdit")  # yol yok: sessizce geçer
        self.assertEqual(hook._BEKLEYEN_UYARI, "")
        self.assertIn("MultiEdit", hook.YAZAN_ARACLAR)


if __name__ == "__main__":
    unittest.main()
