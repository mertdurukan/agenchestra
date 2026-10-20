"""orkestra update / guncelle: LLM'siz güncelleme (yayın klonu + kurulu plugin'ler, user/project kapsamı, çıkış kodu).

Git gerçek (tempfile altında origin + klon); claude.exe sahte: `guncelle.kos` yalnız claude komutlarını yakalar.
`py -3.13 -m pytest plugins/orkestra/tests/test_guncelle.py`
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import guncelle as G  # noqa: E402

GERCEK_KOS = G.kos
SAHTE_CLAUDE = "C:/sahte/claude.exe"


def git(yol, *a):
    return subprocess.run(["git", "-C", yol, "-c", "user.name=t", "-c", "user.email=t@t", *a],
                          capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()


def yaz(yol, metin):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8") as f:
        f.write(metin)


class Ortam(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.t = self.tmp.name
        self.addCleanup(self.tmp.cleanup)
        self.origin = os.path.join(self.t, "origin")
        os.makedirs(self.origin)
        git(self.origin, "init", "-q", "-b", "main")
        yaz(os.path.join(self.origin, "a.txt"), "1")
        git(self.origin, "add", ".")
        git(self.origin, "commit", "-q", "-m", "ilk")
        self.ev = os.path.join(self.t, "ev")
        self.klon = os.path.join(self.t, "plugin_yayin")
        subprocess.run(["git", "clone", "-q", self.origin, self.klon], check=True, capture_output=True)
        self.surum = "aaaa"
        self.claude_cagrilari = []
        self.claude_hatasi = {}  # komut parçası -> çıkış kodu
        self.pazar_yaz()
        self.kurulu_yaz([("orkestra@claude-orchestration", "user", None), ("orkestra-ui@claude-orchestration", "user", None)])
        self.cikti = []
        for p in (mock.patch.object(G, "kos", self.sahte_kos), mock.patch.object(G, "claude_bul", return_value=SAHTE_CLAUDE)):
            p.start()
            self.addCleanup(p.stop)

    def pazar_yaz(self):
        yaz(os.path.join(self.ev, ".claude", "plugins", "known_marketplaces.json"),
            json.dumps({G.PAZAR: {"installLocation": self.klon}}))

    def kurulu_yaz(self, girdiler):
        veri = {}
        for ad, kapsam, proje in girdiler:
            g = {"scope": kapsam, "version": self.surum}
            if proje:
                g["projectPath"] = proje
            veri.setdefault(ad, []).append(g)
        yaz(os.path.join(self.ev, ".claude", "plugins", "installed_plugins.json"), json.dumps({"version": 2, "plugins": veri}))

    def sahte_kos(self, argv, cwd=None):
        if argv[0] != SAHTE_CLAUDE:
            return GERCEK_KOS(argv, cwd)
        self.claude_cagrilari.append((argv[1:], cwd))
        for parca, kod in self.claude_hatasi.items():
            if parca in " ".join(argv):
                return kod, "sahte hata"
        return 0, "ok"

    def kos(self, kuru=False):
        kod = G.calistir(kuru=kuru, yaz=self.cikti.append, ev=self.ev, ortam={})
        return kod, "\n".join(self.cikti)

    def origine_commit(self):
        yaz(os.path.join(self.origin, "a.txt"), "2")
        git(self.origin, "commit", "-q", "-am", "yeni")


class ClaudeBulTest(unittest.TestCase):
    def test_env_yolu_oncelikli(self):
        with tempfile.TemporaryDirectory() as t:
            exe = os.path.join(t, "claude.exe")
            yaz(exe, "x")
            self.assertEqual(G.claude_bul({"CLAUDE_CODE_EXECPATH": exe}, which=lambda _: "path"), exe)

    def test_msix_paketi_en_yeni_surum(self):
        with tempfile.TemporaryDirectory() as t:
            taban = os.path.join(t, "Packages", "Claude_abc", "LocalCache", "Roaming", "Claude", "claude-code")
            for s in ("2.1.9", "2.1.10", "2.0.99"):
                yaz(os.path.join(taban, s, "win-x64", "claude.exe"), "x")
            bulunan = G.claude_bul({"LOCALAPPDATA": t, "APPDATA": os.path.join(t, "yok")}, which=lambda _: None)
            self.assertIn(os.path.join("2.1.10", "win-x64"), bulunan)

    def test_claude_data_koku(self):
        with tempfile.TemporaryDirectory() as t:
            yaz(os.path.join(t, "Claude-Data", "claude_abc", "claude-code", "2.1.304", "aed6", "claude.exe"), "x")
            bulunan = G.claude_bul({"LOCALAPPDATA": t, "APPDATA": os.path.join(t, "yok")}, which=lambda _: None)
            self.assertIn(os.path.join("2.1.304", "aed6"), bulunan)

    def test_appdata_ve_path_yedegi(self):
        with tempfile.TemporaryDirectory() as t:
            yaz(os.path.join(t, "Claude", "claude-code", "1.0.0", "win", "claude.exe"), "x")
            self.assertIn("1.0.0", G.claude_bul({"APPDATA": t}, which=lambda _: None))
        self.assertEqual(G.claude_bul({}, which=lambda _: "C:/bin/claude"), "C:/bin/claude")
        self.assertIsNone(G.claude_bul({}, which=lambda _: None))


class GuncelleTest(Ortam):
    def test_user_kapsamli_pluginler_bulunur_ve_zaten_guncel(self):
        kod, cikti = self.kos()
        self.assertEqual(kod, 0, cikti)
        self.assertIn("ZATEN GÜNCEL", cikti)
        komutlar = [" ".join(c[0]) for c in self.claude_cagrilari]
        self.assertEqual(komutlar, ["plugin marketplace update claude-orchestration",
                                    "plugin update orkestra@claude-orchestration --scope user",
                                    "plugin update orkestra-ui@claude-orchestration --scope user"])

    def test_project_kapsami_proje_klasorunde_calisir(self):
        proje = os.path.join(self.t, "proje")
        os.makedirs(proje)
        self.kurulu_yaz([("orkestra@claude-orchestration", "project", proje)])
        kod, _ = self.kos()
        self.assertEqual(kod, 0)
        self.assertEqual(self.claude_cagrilari[1][1], proje)
        self.assertIn("--scope project", " ".join(self.claude_cagrilari[1][0]))

    def test_guncellendi_klon_ve_plugin_surumu(self):
        self.origine_commit()
        eski = git(self.klon, "rev-parse", "--short", "HEAD")
        orijinal = self.sahte_kos

        def surum_degistir(argv, cwd=None):
            r = orijinal(argv, cwd)
            if argv[1:3] == ["plugin", "update"]:
                self.surum = "bbbb"
                self.kurulu_yaz([("orkestra@claude-orchestration", "user", None), ("orkestra-ui@claude-orchestration", "user", None)])
            return r
        with mock.patch.object(G, "kos", surum_degistir):
            kod, cikti = self.kos()
        yeni = git(self.klon, "rev-parse", "--short", "HEAD")
        self.assertNotEqual(eski, yeni)
        self.assertEqual(kod, 0, cikti)
        self.assertIn(f"GÜNCELLENDİ (klon {eski} → {yeni})", cikti)
        self.assertIn("orkestra@claude-orchestration (user): aaaa → bbbb", cikti)
        self.assertIn("/reload-plugins", cikti)

    def test_kirli_klon_reddedilir_claude_cagrilmaz(self):
        yaz(os.path.join(self.klon, "a.txt"), "elle")
        kod, cikti = self.kos()
        self.assertEqual(kod, 1)
        self.assertIn("HATA: yayın klonunda commitlenmemiş değişiklik", cikti)
        self.assertEqual(self.claude_cagrilari, [])

    def test_ag_hatasi_fetch(self):
        git(self.klon, "remote", "set-url", "origin", os.path.join(self.t, "yok"))
        kod, cikti = self.kos()
        self.assertEqual(kod, 1)
        self.assertIn("HATA: GitHub'dan çekilemedi", cikti)
        self.assertEqual(self.claude_cagrilari, [])

    def test_ayrismis_dal_ff_only_reddeder(self):
        self.origine_commit()
        yaz(os.path.join(self.klon, "b.txt"), "yerel")
        git(self.klon, "add", ".")
        git(self.klon, "commit", "-q", "-m", "yerel")
        kod, cikti = self.kos()
        self.assertEqual(kod, 1)
        self.assertIn("ileri sarılamadı", cikti)

    def test_claude_yok(self):
        with mock.patch.object(G, "claude_bul", return_value=None):
            kod, cikti = self.kos()
        self.assertEqual(kod, 1)
        self.assertIn("HATA: claude.exe bulunamadı", cikti)

    def test_kurulu_plugin_yok(self):
        os.remove(os.path.join(self.ev, ".claude", "plugins", "installed_plugins.json"))
        kod, cikti = self.kos()
        self.assertEqual(kod, 1)
        self.assertIn("HATA: kurulu claude-orchestration plugin'i bulunamadı", cikti)

    def test_pazar_guncelleme_hatasi_durdurur(self):
        self.claude_hatasi = {"marketplace update": 3}
        kod, cikti = self.kos()
        self.assertEqual(kod, 1)
        self.assertIn("HATA: pazar yeri güncellenemedi (çıkış 3)", cikti)
        self.assertEqual(len(self.claude_cagrilari), 1)

    def test_plugin_hatasi_digerlerini_dener_ve_hata_doner(self):
        self.claude_hatasi = {"update orkestra@": 5}
        kod, cikti = self.kos()
        self.assertEqual(kod, 1)
        self.assertIn("HATA: plugin güncellenemedi: orkestra@claude-orchestration --scope user (çıkış 5)", cikti)
        self.assertEqual(len(self.claude_cagrilari), 3)

    def test_kuru_komut_calistirmaz_klonu_ilerletmez(self):
        self.origine_commit()
        once = git(self.klon, "rev-parse", "HEAD")
        kod, cikti = self.kos(kuru=True)
        self.assertEqual(kod, 0)
        self.assertEqual(self.claude_cagrilari, [])
        self.assertEqual(git(self.klon, "rev-parse", "HEAD"), once)
        self.assertIn("Kuru koşu", cikti)


class CliTest(unittest.TestCase):
    def kos(self, *args, env_ek=None):
        env = dict(os.environ, PYTHONUTF8="1")
        env.update(env_ek or {})
        return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", env=env)

    def hata_env(self, tmp):
        # Kurulum dosyaları yok: git ve claude bulunur, yayın klonu bulunamaz -> HATA.
        return {"USERPROFILE": tmp, "HOME": tmp, "CLAUDE_CODE_EXECPATH": sys.executable}

    def test_help_update_ve_guncelle_ayni(self):
        for ad in ("update", "guncelle"):
            r = self.kos(sys.executable, os.path.join(KOK, "scripts", "orkestra.py"), ad, "--help")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("--kuru", r.stdout)

    def test_hata_sifirdan_farkli_cikis_kodu_python(self):
        with tempfile.TemporaryDirectory() as t:
            r = self.kos(sys.executable, os.path.join(KOK, "scripts", "orkestra.py"), "update", env_ek=self.hata_env(t))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("HATA:", r.stdout)

    @unittest.skipUnless(os.name == "nt", "orkestra.cmd yalnız Windows")
    def test_cmd_sarmalayici_cikis_kodunu_yutmaz(self):
        cmd = os.path.join(KOK, "bin", "orkestra.cmd")
        with tempfile.TemporaryDirectory() as t:
            r = self.kos(cmd, "update", env_ek=dict(self.hata_env(t), ORKESTRA_PYTHON=sys.executable))
            r2 = self.kos(cmd, "update", env_ek=self.hata_env(t))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(r2.returncode, 1, r2.stdout + r2.stderr)


if __name__ == "__main__":
    unittest.main()
