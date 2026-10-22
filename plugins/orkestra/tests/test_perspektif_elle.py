"""I-054: perspektif yalnız elle başlar; projeye_kur --kaldir user kurulumunda projede kapatır.
`py -3.13 -m pytest plugins/orkestra/tests/test_perspektif_elle.py`
Hepsi geçici projede koşar; gerçek ~/.claude ya da proje durum dizinine yazılmaz, claude komutu çağrılmaz.
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPO = os.path.dirname(os.path.dirname(KOK))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import hook  # noqa: E402
import niyet  # noqa: E402
import ork_lib as L  # noqa: E402
import panel  # noqa: E402
import perspektif  # noqa: E402

OTURUM = "perspelle-1234567890-oturum"
ZAMANI_GELDI = {"okunmamis_rapor": None, "zamani_geldi": True, "calisiyor": False}


def projeye_kur():
    spec = importlib.util.spec_from_file_location("i054_projeye_kur", os.path.join(DEPO, "araclar", "projeye_kur.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class HookOrtam(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_perspelle_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        self.genel = os.path.join(self.proje, "genel_panel")
        os.makedirs(self.genel)
        self.tr = os.path.join(self.proje, "tr.jsonl")
        open(self.tr, "w").close()
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for k in ("CLAUDE_PROJECT_DIR", "ORKESTRA_RUYA", "ORKESTRA_PERSPEKTIF", "ORKESTRA_PERSPEKTIF_OTO"):
            os.environ.pop(k, None)
        niyet_yolu = os.path.join(self.proje, "niyet", "niyet.jsonl")
        self._p = [mock.patch.object(niyet, "NIYET_YOLU", niyet_yolu),
                   mock.patch.object(niyet, "GENEL_DIZIN", os.path.dirname(niyet_yolu)),
                   mock.patch.object(niyet, "_gecici", return_value=False),
                   mock.patch.object(panel, "DURUM", os.path.join(self.genel, "panel.json")),
                   mock.patch.object(L, "GENEL_DIZIN", self.genel)]
        for p in self._p:
            p.start()
        self.g = {"session_id": OTURUM, "cwd": self.proje, "transcript_path": self.tr, "source": "startup"}

    def tearDown(self):
        for p in self._p:
            p.stop()
        self._env.stop()
        shutil.rmtree(self.proje, ignore_errors=True)

    def acilis(self) -> str:
        buf = io.StringIO()
        with mock.patch.object(L, "bayatlik", return_value=None), \
                mock.patch.object(perspektif, "durum", return_value=ZAMANI_GELDI), contextlib.redirect_stdout(buf):
            try:
                hook.session_start(self.g)
            except SystemExit:
                pass
        cikti = buf.getvalue().strip()
        return json.loads(cikti)["hookSpecificOutput"]["additionalContext"] if cikti else ""

    def kapanis(self) -> mock.MagicMock:
        with mock.patch.object(perspektif, "durum", return_value=ZAMANI_GELDI), \
                mock.patch.object(perspektif, "baslat") as baslat, contextlib.redirect_stdout(io.StringIO()):
            try:
                hook.session_end(self.g)
            except SystemExit:
                pass
        return baslat

    # P3 K1
    def test_acilista_perspektif_talimati_yok(self):
        self.assertNotIn("PERSPEKTİF ZAMANI", self.acilis())

    # P3 K2
    def test_kapanista_perspektif_baslamaz(self):
        self.kapanis().assert_not_called()

    # P3 K3
    def test_oto_degiskeniyle_ikisi_de_calisir(self):
        os.environ["ORKESTRA_PERSPEKTIF_OTO"] = "1"
        self.assertIn("PERSPEKTİF ZAMANI", self.acilis())
        self.kapanis().assert_called_once()


class KaldirTest(unittest.TestCase):
    def setUp(self):
        self.m = projeye_kur()
        self.m.KAYNAK = {"source": "directory", "path": "/yok"}
        self.proje = tempfile.mkdtemp(prefix="ork_kaldir_")
        self.komutlar = []
        self._p = [mock.patch.object(self.m, "claude_exe", return_value="claude"),
                   mock.patch.object(self.m, "kos", side_effect=lambda argv, cwd, kuru: self.komutlar.append(argv) or (0, ""))]
        for p in self._p:
            p.start()

    def tearDown(self):
        for p in self._p:
            p.stop()
        shutil.rmtree(self.proje, ignore_errors=True)

    def ayar(self):
        with open(os.path.join(self.proje, ".claude", "settings.json"), encoding="utf-8") as f:
            return json.load(f)

    # P2 K1
    def test_projeden_kaldir_false_yazar(self):
        os.makedirs(os.path.join(self.proje, ".claude"))
        with open(os.path.join(self.proje, ".claude", "settings.json"), "w", encoding="utf-8") as f:
            json.dump({"model": "x", "enabledPlugins": {"orkestra@claude-orchestration": True}}, f)
        with contextlib.redirect_stdout(io.StringIO()):
            self.m.kaldir(self.proje, False)
        s = self.ayar()
        self.assertEqual(s["model"], "x")
        self.assertIs(s["enabledPlugins"]["orkestra@claude-orchestration"], False)
        self.assertIs(s["enabledPlugins"]["orkestra-ui@claude-orchestration"], False)

    def test_ayar_dosyasi_yoksa_olusturur(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.m.kaldir(self.proje, False)
        self.assertIs(self.ayar()["enabledPlugins"]["orkestra@claude-orchestration"], False)

    def test_kuru_kosu_yazmaz(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.m.kaldir(self.proje, True)
        self.assertFalse(os.path.exists(os.path.join(self.proje, ".claude", "settings.json")))

    # P2 K2
    def test_kullanici_kaldir_user_kapsamindan_kaldirir(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.m.kaldir_kullanici(True)
        self.assertEqual(len(self.komutlar), 2)
        for argv in self.komutlar:
            self.assertIn("uninstall", argv)
            self.assertEqual(argv[argv.index("--scope") + 1], "user")

    # P1 K1
    def test_kullanici_kur_user_kapsaminda_kurar(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.m.kur_kullanici(True, True)
        kurulum = [a for a in self.komutlar if "install" in a]
        self.assertEqual(len(kurulum), 2)
        for argv in kurulum:
            self.assertEqual(argv[argv.index("--scope") + 1], "user")

    # I-057 P1 K1-K3
    def _ev(self):
        ev = tempfile.mkdtemp(prefix="ork_ev_")
        self.addCleanup(shutil.rmtree, ev, True)
        self._p.append(mock.patch.object(self.m, "kullanici_ayar_yolu", return_value=os.path.join(ev, ".claude", "settings.json")))
        self._p[-1].start()
        return os.path.join(ev, ".claude", "settings.json")

    def test_kullanici_kurulumu_uc_ayari_yazar_tekrarda_cogaltmaz(self):
        yol = self._ev()
        with contextlib.redirect_stdout(io.StringIO()):
            self.m.kullanici_ayar_yaz(False)
            self.m.kullanici_ayar_yaz(False)
        s = json.load(open(yol, encoding="utf-8"))
        self.assertEqual(s["env"]["PYTHONUTF8"], "1")
        self.assertEqual(s["permissions"]["allow"], ["Bash(orkestra *)"])
        self.assertEqual(s["statusLine"]["command"], self.m.KOTA_KOMUTU)

    def test_kullanicinin_durum_satiri_korunur_geri_alma_ona_dokunmaz(self):
        yol = self._ev()
        os.makedirs(os.path.dirname(yol))
        kendi = {"type": "command", "command": "benim"}
        json.dump({"statusLine": kendi, "theme": "x"}, open(yol, "w", encoding="utf-8"))
        with contextlib.redirect_stdout(io.StringIO()):
            self.m.kullanici_ayar_yaz(False)
            self.m.kullanici_ayar_geri(False)
        s = json.load(open(yol, encoding="utf-8"))
        self.assertEqual(s["statusLine"], kendi)
        self.assertEqual(s["theme"], "x")
        self.assertEqual(s["permissions"]["allow"], [])

    def test_geri_alma_kota_satirini_ve_izni_kaldirir(self):
        yol = self._ev()
        with contextlib.redirect_stdout(io.StringIO()):
            self.m.kullanici_ayar_yaz(False)
            self.m.kullanici_ayar_geri(False)
        s = json.load(open(yol, encoding="utf-8"))
        self.assertNotIn("statusLine", s)
        self.assertEqual(s["permissions"]["allow"], [])

    # I-057 P1 K4
    def test_proje_kurulumu_ayni_uc_ayari_yazar(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.m.ayar_birlestir(self.proje, False, False)
        s = self.ayar()
        self.assertEqual(s["env"]["PYTHONUTF8"], "1")
        self.assertIn("Bash(orkestra *)", s["permissions"]["allow"])
        self.assertEqual(s["statusLine"]["command"], self.m.KOTA_KOMUTU)


if __name__ == "__main__":
    unittest.main()


class PerspektifYoksay(unittest.TestCase):
    def test_yoksay_alarmi_sonraki_tetiklemeye_kadar_susturur(self):
        with tempfile.TemporaryDirectory() as sd:
            for _ in range(12):
                perspektif.oturum_say(sd, "startup")
            self.assertTrue(perspektif.durum(sd)["zamani_geldi"])
            perspektif.yoksay(sd)
            self.assertFalse(perspektif.durum(sd)["zamani_geldi"])
            for _ in range(perspektif.OTURUM_ESIGI):
                perspektif.oturum_say(sd, "startup")
            self.assertTrue(perspektif.durum(sd)["zamani_geldi"])
