"""G-085: taşınabilir kurulum — sabit yol yok, GitHub kaynağı."""
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

DEPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ARACLAR = os.path.join(DEPO, "araclar")
YASAK = ("C:/Mert", "C:\\Users\\PC", "C:\\\\Users\\\\PC", "McD")


def yukle(ad):
    spec = importlib.util.spec_from_file_location("g085_" + ad, os.path.join(ARACLAR, ad + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def norm(p):
    return os.path.normpath(p).replace("\\", "/").rstrip("/").lower()


def git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, encoding="utf-8")


def bos_depo(kok, origin=None):
    d = os.path.join(kok, "sahte-depo")
    os.makedirs(d)
    git(d, "init", "-q")
    if origin:
        git(d, "remote", "add", "origin", origin)
    return d


class SabitYolYok(unittest.TestCase):
    def test_araclar_altinda_yasak_dizge_yok(self):
        bulunan = []
        for kok, dizinler, dosyalar in os.walk(ARACLAR):
            dizinler[:] = [d for d in dizinler if d != "__pycache__"]
            for ad in dosyalar:
                if ad.endswith((".pyc", ".pyo")):
                    continue
                with open(os.path.join(kok, ad), encoding="utf-8", errors="replace") as f:
                    metin = f.read()
                for y in YASAK:
                    if y in metin:
                        bulunan.append((os.path.join(kok, ad), y))
        self.assertEqual(bulunan, [])

    def test_kok_settings_yasak_dizge_yok(self):
        with open(os.path.join(DEPO, ".claude", "settings.json"), encoding="utf-8") as f:
            metin = f.read()
        for y in YASAK:
            self.assertNotIn(y, metin)


class YayinYolu(unittest.TestCase):
    def setUp(self):
        self.m = yukle("yayin_kur")
        self.env = {k: v for k, v in os.environ.items() if k != "ORKESTRA_YAYIN"}

    def test_arguman_env_ustunde(self):
        with mock.patch.dict(os.environ, {**self.env, "ORKESTRA_YAYIN": "/env/yolu"}, clear=True):
            self.assertEqual(self.m.yayin_yolu("/arg/yolu"), "/arg/yolu")

    def test_arguman_ters_egik_cizgi_normallesir(self):
        with mock.patch.dict(os.environ, self.env, clear=True):
            self.assertEqual(self.m.yayin_yolu("D:\\a\\b"), "D:/a/b")

    def test_env_varsayilandan_once(self):
        with mock.patch.dict(os.environ, {**self.env, "ORKESTRA_YAYIN": "/env/yolu"}, clear=True):
            self.assertEqual(self.m.yayin_yolu(), "/env/yolu")
            self.assertEqual(self.m.yayin_yolu(None), "/env/yolu")

    def test_bos_env_varsayilana_duser(self):
        with mock.patch.dict(os.environ, {**self.env, "ORKESTRA_YAYIN": ""}, clear=True):
            self.assertNotEqual(self.m.yayin_yolu(), "")

    def test_varsayilan_depoya_gore_turetilir(self):
        with tempfile.TemporaryDirectory() as t:
            sahte = os.path.join(t, "bir", "depom")
            os.makedirs(sahte)
            with mock.patch.dict(os.environ, self.env, clear=True), mock.patch.object(self.m, "DEPO", sahte):
                y = norm(self.m.yayin_yolu())
            izinli = {norm(sahte), norm(os.path.join(os.path.dirname(sahte), "Claude_Orkestrasyon", "plugin_yayin"))}
            self.assertIn(y, izinli)
            self.assertTrue(y.startswith(norm(t)))

    def test_varsayilan_gercek_depoda_sabit_yol_degil(self):
        with mock.patch.dict(os.environ, self.env, clear=True):
            y = norm(self.m.yayin_yolu())
        # Depo gerçekte hangi klasörde olursa olsun yol ondan türer; kaynakta sabit kullanıcı yolu yok.
        self.assertTrue(y.startswith(norm(os.path.dirname(DEPO))))
        with open(self.m.__file__, encoding="utf-8") as f:
            self.assertNotRegex(f.read(), r"(?i)[a-z]:[\/]+mert")

    def test_modulde_VARSAYILAN_YAYIN_sabiti_yok(self):
        self.assertFalse(hasattr(self.m, "VARSAYILAN_YAYIN") and "Mert" in str(self.m.VARSAYILAN_YAYIN))


class ProjeyeKur(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.proje = os.path.join(self.tmp.name, "proje")
        os.makedirs(self.proje)
        self.m = yukle("projeye_kur")
        self.ayar_yolu = os.path.join(self.proje, ".claude", "settings.json")

    def calistir(self, *arg, depo=None):
        argv = ["projeye_kur.py", self.proje, *arg]
        cikti = io.StringIO()
        kod = 0
        env = {k: v for k, v in os.environ.items() if k != "ORKESTRA_YAYIN"}
        yamalar = [
            mock.patch.object(sys, "argv", argv),
            mock.patch.object(self.m, "claude_exe", lambda: "claude"),
            mock.patch.object(self.m, "kos", lambda a, c, k: (0, "claude-orchestration")),
            mock.patch.dict(os.environ, env, clear=True),
        ]
        if depo:
            yamalar.append(mock.patch.object(self.m, "DEPO", depo))
        with contextlib.ExitStack() as st:
            for y in yamalar:
                st.enter_context(y)
            with contextlib.redirect_stdout(cikti), contextlib.redirect_stderr(cikti):
                try:
                    self.m.main()
                except SystemExit as e:
                    kod = e.code if isinstance(e.code, int) else (1 if e.code else 0)
                    if isinstance(e.code, str):
                        cikti.write(e.code)
        return kod, cikti.getvalue()

    def ayar(self):
        with open(self.ayar_yolu, encoding="utf-8") as f:
            return json.load(f)

    def test_github_kaynagi_repo_argumanindan(self):
        kod, _ = self.calistir("--kaynak", "github", "--repo", "a/b")
        self.assertEqual(kod, 0)
        girdi = self.ayar()["extraKnownMarketplaces"]["claude-orchestration"]
        self.assertEqual(girdi["source"], {"source": "github", "repo": "a/b"})
        self.assertTrue(self.ayar()["enabledPlugins"]["orkestra@claude-orchestration"])

    def test_github_repo_origin_urlinden_turetilir(self):
        for url, beklenen in (("https://github.com/sahip/depo.git", "sahip/depo"),
                              ("git@github.com:sahip2/depo2.git", "sahip2/depo2")):
            with self.subTest(url=url):
                with tempfile.TemporaryDirectory() as t:
                    d = bos_depo(t, url)
                    if os.path.exists(self.ayar_yolu):
                        os.remove(self.ayar_yolu)
                    kod, _ = self.calistir("--kaynak", "github", depo=d)
                    self.assertEqual(kod, 0)
                    self.assertEqual(self.ayar()["extraKnownMarketplaces"]["claude-orchestration"]["source"],
                                     {"source": "github", "repo": beklenen})

    def test_repo_argumani_origin_ustunde(self):
        with tempfile.TemporaryDirectory() as t:
            d = bos_depo(t, "https://github.com/baska/yer.git")
            kod, _ = self.calistir("--kaynak", "github", "--repo", "a/b", depo=d)
            self.assertEqual(kod, 0)
            self.assertEqual(self.ayar()["extraKnownMarketplaces"]["claude-orchestration"]["source"]["repo"], "a/b")

    def test_github_repo_yok_origin_yok_hata_ayar_yazilmaz(self):
        with tempfile.TemporaryDirectory() as t:
            d = bos_depo(t)
            kod, cikti = self.calistir("--kaynak", "github", depo=d)
        self.assertNotEqual(kod, 0)
        self.assertIn("repo", cikti.lower())
        self.assertFalse(os.path.exists(self.ayar_yolu))

    def test_gecersiz_kaynak_reddedilir(self):
        kod, _ = self.calistir("--kaynak", "ftp")
        self.assertNotEqual(kod, 0)
        self.assertFalse(os.path.exists(self.ayar_yolu))

    def test_yerel_varsayilan_directory_ve_mutlak_yol(self):
        kod, _ = self.calistir("--yayin", "D:\\klon\\yayin")
        self.assertEqual(kod, 0)
        self.assertEqual(self.ayar()["extraKnownMarketplaces"]["claude-orchestration"]["source"],
                         {"source": "directory", "path": "D:/klon/yayin"})

    def test_yerel_acik_kaynak_ayni_sonuc(self):
        kod, _ = self.calistir("--kaynak", "yerel", "--yayin", "D:/klon/yayin")
        self.assertEqual(kod, 0)
        self.assertEqual(self.ayar()["extraKnownMarketplaces"]["claude-orchestration"]["source"],
                         {"source": "directory", "path": "D:/klon/yayin"})

    def test_yerel_varsayilan_yol_sabit_degil(self):
        kod, _ = self.calistir()
        self.assertEqual(kod, 0)
        p = self.ayar()["extraKnownMarketplaces"]["claude-orchestration"]["source"]["path"]
        self.assertTrue(os.path.isabs(p))
        with open(os.path.join(ARACLAR, "projeye_kur.py"), encoding="utf-8") as f:
            self.assertNotRegex(f.read(), r"(?i)[a-z]:[\/]+mert")   # sabit yol kaynakta yok

    def test_var_olan_kaynak_ve_ayar_ustune_yazilmaz(self):
        os.makedirs(os.path.dirname(self.ayar_yolu))
        onceki = {"model": "ozel-model",
                  "extraKnownMarketplaces": {"claude-orchestration": {"source": {"source": "directory", "path": "X:/benim"}}}}
        with open(self.ayar_yolu, "w", encoding="utf-8") as f:
            json.dump(onceki, f)
        kod, _ = self.calistir("--kaynak", "github", "--repo", "a/b")
        self.assertEqual(kod, 0)
        s = self.ayar()
        self.assertEqual(s["model"], "ozel-model")
        self.assertEqual(s["extraKnownMarketplaces"]["claude-orchestration"]["source"],
                         {"source": "directory", "path": "X:/benim"})

    def test_kuru_calisma_ayar_yazmaz(self):
        kod, _ = self.calistir("--kaynak", "github", "--repo", "a/b", "--kuru")
        self.assertEqual(kod, 0)
        self.assertFalse(os.path.exists(self.ayar_yolu))


class KokYapilandirma(unittest.TestCase):
    def test_kok_settings_gecerli_ve_eklentiler(self):
        with open(os.path.join(DEPO, ".claude", "settings.json"), encoding="utf-8") as f:
            s = json.load(f)
        ep = s["enabledPlugins"]
        self.assertIs(ep.get("orkestra@claude-orchestration"), True)
        self.assertIs(ep.get("orkestra-ui@claude-orchestration"), True)
        self.assertEqual(s["extraKnownMarketplaces"]["claude-orchestration"]["source"]["source"], "github")
        self.assertIn("repo", s["extraKnownMarketplaces"]["claude-orchestration"]["source"])
        self.assertEqual(str(s["env"]["PYTHONUTF8"]), "1")

    def test_gitignore_calisma_verisini_dislar_ve_settings_izlenir(self):
        with open(os.path.join(DEPO, ".gitignore"), encoding="utf-8") as f:
            satirlar = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        self.assertTrue(any(l.rstrip("/*") in (".claude/orkestra", "/.claude/orkestra") for l in satirlar), satirlar)
        for gerekli in ("*.lock", "__pycache__", ".pytest_cache"):
            self.assertTrue(any(l.strip("/") in (gerekli, gerekli + "/") for l in satirlar), gerekli)
        r = git(DEPO, "check-ignore", "-q", ".claude/orkestra/ortak_defter.md")
        self.assertEqual(r.returncode, 0)
        r = git(DEPO, "check-ignore", "-q", ".claude/settings.json")
        self.assertEqual(r.returncode, 1)


if __name__ == "__main__":
    unittest.main()
