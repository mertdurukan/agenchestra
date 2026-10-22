"""Oturum worktree'sinde orkestra durumu tek kaynaktan çözülür (ADR-0032, I-156 P1).

Claude'un oturum başına açtığı worktree'de git dışı `.claude/orkestra` kopyalanır; hook ana klasöre, CLI kopyaya yazıyordu.
Her test tempfile altında kendi git deposunu kurar; gerçek depoya dokunmaz.
`py -3.13 -m pytest plugins/orkestra/tests/test_oturum_agaci_durum.py`
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
sys.path.insert(0, os.path.join(KOK, "scripts"))
import ork_lib as L  # noqa: E402


def git(cwd, *args):
    r = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)}: {r.stderr or r.stdout}")
    return r.stdout


def n(yol):
    return os.path.normcase(os.path.realpath(yol)).replace("\\", "/").rstrip("/")


class OturumAgaciDurum(unittest.TestCase):
    def setUp(self):
        self.taban = os.path.realpath(tempfile.mkdtemp(prefix="ork_oad_"))
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
        # oturum worktree'si: depo içi gizli klasör; durum kopyası uygulama tarafından kopyalanmış gibi
        self.wt = os.path.join(self.ana, ".claude", "worktrees", "oturum-ab12cd")
        git(self.ana, "worktree", "add", "-q", "-b", "claude/oturum-ab12cd", self.wt)
        shutil.copytree(os.path.join(self.ana, ".claude", "orkestra"), os.path.join(self.wt, ".claude", "orkestra"))
        for k in ("CLAUDE_PROJECT_DIR", L.DURUM_YEREL_ORTAM):
            os.environ.pop(k, None)

    def tearDown(self):
        os.environ.pop(L.DURUM_YEREL_ORTAM, None)
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        subprocess.run(["git", "-C", self.ana, "worktree", "remove", "--force", self.wt], capture_output=True)
        shutil.rmtree(self.taban, ignore_errors=True)

    def kos(self, args, cwd, env_ek=None):
        env = dict(os.environ, CLAUDE_CODE_SESSION_ID="oad-oturum", PYTHONUTF8="1")
        env.pop("CLAUDE_PROJECT_DIR", None)
        env.pop(L.DURUM_YEREL_ORTAM, None)
        env.update(env_ek or {})
        return subprocess.run([sys.executable, CLI] + args, cwd=cwd, env=env, capture_output=True, text=True,
                              encoding="utf-8")

    # ------------------------------------------------------------------ kütüphane
    def test_ana_agac_koku_worktree_ve_ana_agac(self):
        self.assertEqual(n(L.ana_agac_koku(self.wt)), n(self.ana))
        self.assertIsNone(L.ana_agac_koku(self.ana))  # ana ağaçta .git klasördür
        self.assertIsNone(L.ana_agac_koku(self.taban))  # git dışı

    def test_worktree_cwd_ana_agaca_cozulur(self):  # kriter: 4 senaryodan 1
        self.assertEqual(n(L.proje_dizini(self.wt)), n(self.ana))
        self.assertEqual(n(L.durum_dizini(self.wt)), n(os.path.join(self.ana, ".claude", "orkestra")))

    def test_alt_klasorden_de_ana_agaca_cozulur(self):
        alt = os.path.join(self.wt, "derin", "klasor")
        os.makedirs(alt)
        self.assertEqual(n(L.proje_dizini(alt)), n(self.ana))

    def test_proje_dizini_env_worktree_ise_ana_agaca_cozulur(self):  # 4 senaryodan 2
        os.environ["CLAUDE_PROJECT_DIR"] = self.wt
        self.assertEqual(n(L.proje_dizini(self.wt)), n(self.ana))

    def test_yerel_ortam_kopyayi_secer(self):  # 4 senaryodan 3
        os.environ[L.DURUM_YEREL_ORTAM] = "1"
        self.assertEqual(n(L.proje_dizini(self.wt)), n(self.wt))

    def test_ana_agac_degismez(self):  # 4 senaryodan 4
        self.assertEqual(n(L.proje_dizini(self.ana)), n(self.ana))

    def test_ana_agacta_durum_yoksa_worktree_kopyasi_kalir(self):
        shutil.rmtree(os.path.join(self.ana, ".claude", "orkestra"))
        self.assertEqual(n(L.proje_dizini(self.wt)), n(self.wt))

    def test_kart_agaci_kopyasiz_ana_agaca_cozulur(self):
        kart = os.path.join(self.ana, ".claude", "worktrees", "kart-G-001")
        git(self.ana, "worktree", "add", "-q", "-b", "kart/G-001", kart)
        try:
            self.assertEqual(n(L.proje_dizini(kart)), n(self.ana))
        finally:
            subprocess.run(["git", "-C", self.ana, "worktree", "remove", "--force", kart], capture_output=True)

    # ------------------------------------------------------------------ P2: ağaçlar arası numara tekilliği
    def _ikinci_agac(self):
        wt2 = os.path.join(self.ana, ".claude", "worktrees", "oturum-ef34gh")
        git(self.ana, "worktree", "add", "-q", "-b", "claude/oturum-ef34gh", wt2)
        self.addCleanup(lambda: subprocess.run(["git", "-C", self.ana, "worktree", "remove", "--force", wt2],
                                               capture_output=True))
        return wt2

    def test_sonraki_klasor_adi_kardes_agactaki_numarayi_atlar(self):
        import is_kaydi as K
        wt2 = self._ikinci_agac()
        os.makedirs(os.path.join(self.wt, "Is", "001-ilk-agac"))
        os.makedirs(os.path.join(self.ana, "Is", "002-ana-agac"))
        ad = K.sonraki_klasor_adi(os.path.join(wt2, "Is"), "Ikinci", "20261022")
        self.assertEqual(ad, "003-20261022-ikinci")

    def test_sonraki_klasor_adi_tek_agacta_degismez(self):
        import is_kaydi as K
        os.makedirs(os.path.join(self.wt, "Is", "004-x"))
        self.assertEqual(K.sonraki_klasor_adi(os.path.join(self.wt, "Is"), "Y", "20261022"), "005-20261022-y")

    def test_klasor_ayir_tercih_kardes_agactaki_numarayla_cakisirsa_siradakini_alir(self):
        import is_kaydi as K
        wt2 = self._ikinci_agac()
        os.makedirs(os.path.join(self.wt, "Is", "001-ilk-agac"))
        sd = os.path.join(self.ana, ".claude", "orkestra")
        ad = K.klasor_ayir(sd, os.path.join(wt2, "Is"), "Ikinci", "20261022", olustur=False, tercih="001-baska-ad")
        self.assertEqual(ad, "002-20261022-ikinci")

    def test_klasor_ayir_ayni_ad_kardes_agacta_varsa_cakisma_sayilmaz(self):
        import is_kaydi as K
        wt2 = self._ikinci_agac()
        os.makedirs(os.path.join(self.wt, "Is", "001-ayni-is"))
        sd = os.path.join(self.ana, ".claude", "orkestra")
        ad = K.klasor_ayir(sd, os.path.join(wt2, "Is"), "Ayni", "20261022", olustur=False, tercih="001-ayni-is")
        self.assertEqual(ad, "001-ayni-is")

    def test_git_disi_klasorde_kardes_listesi_bos(self):
        import is_kaydi as K
        d = os.path.join(self.taban, "gitsiz")
        os.makedirs(d)
        self.assertEqual(K.kardes_agac_klasorleri(d), [])

    # ------------------------------------------------------------------ P4: oturum ağaçları temizlikte tanınır
    def test_agac_temizle_oturum_agacini_oturum_sinifina_alir(self):
        s = L.agac_temizle_siniflandir(self.ana, [])
        self.assertEqual([n(w["yol"]) for w in s["oturum"]], [n(self.wt)])
        self.assertEqual(s["kalip_disi"], [])
        self.assertEqual(s["aday"], [])
        self.assertEqual(s["oturum"][0]["devralinmamis"], 0)

    def test_agac_temizle_devralinmamis_kopyayi_sayar(self):
        with open(os.path.join(self.wt, ".claude", "orkestra", "gunluk.jsonl"), "w", encoding="utf-8", newline="\n") as f:
            f.write('{"a":1}\n{"a":2}\n')
        s = L.agac_temizle_siniflandir(self.ana, [])
        self.assertEqual(s["oturum"][0]["devralinmamis"], 2)

    def test_agac_temizle_kart_agaci_oturum_sayilmaz(self):
        kart = os.path.join(self.ana, ".claude", "worktrees", "kart-G-009")
        git(self.ana, "worktree", "add", "-q", "-b", "kart/G-009", kart)
        try:
            s = L.agac_temizle_siniflandir(self.ana, [])
            self.assertEqual([n(w["yol"]) for w in s["oturum"]], [n(self.wt)])
            self.assertEqual([n(w["yol"]) for w in s["aday"]], [n(kart)])  # kartı yok → aday
        finally:
            subprocess.run(["git", "-C", self.ana, "worktree", "remove", "--force", kart], capture_output=True)

    def test_cli_agac_temizle_oturum_agacina_dokunmaz_ve_uyarir(self):
        with open(os.path.join(self.wt, ".claude", "orkestra", "gunluk.jsonl"), "w", encoding="utf-8", newline="\n") as f:
            f.write('{"a":1}\n')
        r = self.kos(["kart", "agac-temizle", "--uygula", "--ajan-id", "ana", "--ajan-tipi", "ana"], self.wt)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("oturum ağacı", r.stdout)
        self.assertIn("orkestra durum devral", r.stdout)
        self.assertTrue(os.path.isdir(self.wt))

    # ------------------------------------------------------------------ CLI uçtan uca
    def test_cli_worktree_cwd_isi_ana_isler_json_a_yazar(self):
        klasor = os.path.join(self.wt, "Is", "001-deneme")
        r = self.kos(["is", "ac", "Worktree deneme işi", "--klasor", klasor], self.wt)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.ana, ".claude", "orkestra", "isler.json"), encoding="utf-8") as f:
            ana = f.read()
        self.assertIn("Worktree deneme", ana)
        yerel = os.path.join(self.wt, ".claude", "orkestra", "isler.json")
        self.assertFalse(os.path.exists(yerel) and "Worktree deneme" in open(yerel, encoding="utf-8").read())

    def test_cli_yerel_ortamla_kopyaya_yazar(self):
        klasor = os.path.join(self.wt, "Is", "001-yerel")
        r = self.kos(["is", "ac", "Yerel deneme işi", "--klasor", klasor], self.wt, {L.DURUM_YEREL_ORTAM: "1"})
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.wt, ".claude", "orkestra", "isler.json"), encoding="utf-8") as f:
            self.assertIn("Yerel deneme", f.read())
        ana = os.path.join(self.ana, ".claude", "orkestra", "isler.json")
        self.assertFalse(os.path.exists(ana) and "Yerel deneme" in open(ana, encoding="utf-8").read())


if __name__ == "__main__":
    unittest.main()
