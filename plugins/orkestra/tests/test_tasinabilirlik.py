"""P11 (I-026): taşınabilirlik — kodda literal makine yolu yok; temiz makinede (boş HOME, boş proje) ilk çalıştırma kendini kurar."""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(KOK, "scripts")
sys.path.insert(0, SCRIPTS)

# Sürücü harfli yol (C:\..., D:/...) ya da kullanıcı ev dizini yolu. URL'ler (http://) eşleşmez: harften önce harf yok.
SURUCU_YOLU = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]{1,2}[A-Za-z0-9_.]")
EV_YOLU = re.compile(r"(?:/Users/|/home/|\\Users\\)[A-Za-z0-9_.-]+", re.I)
# cfg.py makine keşfinin kendisi: örnek/şablon yol taşıyabilir. Başka dosyaya istisna eklenmez; yol cfg'den alınır.
ISTISNA = {"cfg.py"}


def kaynak_dosyalar():
    for kok, dizinler, dosyalar in os.walk(SCRIPTS):
        dizinler[:] = [d for d in dizinler if d != "__pycache__"]
        for ad in dosyalar:
            if ad.endswith(".py") and ad not in ISTISNA:
                yield os.path.join(kok, ad)


def ust_dizinde_orkestra_durumu_var():
    """Geçici dizinin üstünde `.claude/orkestra` varsa proje araması oraya bağlanır (ork_lib.proje_dizini); bu testler o ortamda anlamsızdır.
    `orkestra doktor` bunu `home_cakisma` kontrolüyle bildirir."""
    d = os.path.abspath(tempfile.gettempdir())
    while True:
        if os.path.isdir(os.path.join(d, ".claude", "orkestra")):
            return True
        ust = os.path.dirname(d)
        if ust == d:
            return False
        d = ust


ORTAM_KIRLI = "geçici dizinin üstünde .claude/orkestra var (orkestra doktor: home_cakisma); proje araması oraya bağlanır"


class StatikLintTest(unittest.TestCase):
    def test_cfg_disinda_literal_makine_yolu_yok(self):
        bulunan = []
        for yol in kaynak_dosyalar():
            with open(yol, encoding="utf-8") as f:
                for no, satir in enumerate(f, 1):
                    if SURUCU_YOLU.search(satir) or EV_YOLU.search(satir):
                        bulunan.append(f"{os.path.relpath(yol, KOK)}:{no}: {satir.strip()[:100]}")
        self.assertEqual(bulunan, [], "makineye özgü yol cfg.py'den alınmalı (ya da doktor onarsın)")

    def test_lint_kendi_deseni_calisir(self):
        for ornek in (r'x = "C:\Python315\python.exe"', 'y = "d:/tools/bash.exe"', 'z = "/Users/biri/bin"', r'w = "C:\\Users\\biri"'):
            self.assertTrue(SURUCU_YOLU.search(ornek) or EV_YOLU.search(ornek), ornek)
        for ornek in ('u = "https://example.com/a"', 'v = "ab:cd"', 'ok = r"[A-Za-z]:[\\/]"'):
            self.assertFalse(SURUCU_YOLU.search(ornek) or EV_YOLU.search(ornek), ornek)


class EvCakismaTest(unittest.TestCase):
    """P11 bulgusu: makine config'i `~/.claude/orkestra/` altına yazılınca home altındaki her proje orkestra'yı açık sanıyordu."""

    def test_varsayilan_ev_proje_durum_klasoru_adini_tasimaz(self):
        import cfg
        with mock.patch.dict(os.environ):
            os.environ.pop("ORKESTRA_HOME", None)
            self.assertNotEqual(os.path.basename(cfg.ev_dizini()), "orkestra")

    @unittest.skipIf(ust_dizinde_orkestra_durumu_var(), ORTAM_KIRLI)
    def test_home_altindaki_proje_makine_config_yuzunden_orkestrali_sayilmaz(self):
        import cfg
        import ork_lib as L
        with tempfile.TemporaryDirectory() as home:
            proje = os.path.join(home, "isler", "x")
            os.makedirs(proje)
            with mock.patch.dict(os.environ, {"HOME": home, "USERPROFILE": home}):
                os.environ.pop("ORKESTRA_HOME", None)
                os.environ.pop("CLAUDE_PROJECT_DIR", None)
                cfg.makine_yaz({"python": "p"})
                self.assertTrue(os.path.isfile(cfg.makine_dosyasi()))
                self.assertIsNone(L.durum_dizini(proje))


class TemizMakineTest(unittest.TestCase):
    """Boş HOME + boş proje + ORKESTRA_* yok. Gerçek alt süreç (uçtan uca; ic_kos kullanılmaz)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temizle)
        self.home = os.path.join(self.tmp.name, "home")
        self.proje = os.path.join(self.tmp.name, "proje")
        for d in (self.home, self.proje, os.path.join(self.home, "AppData", "Roaming"), os.path.join(self.home, "AppData", "Local")):
            os.makedirs(d)
        temel = ("PATH", "PATHEXT", "SYSTEMROOT", "SystemDrive", "COMSPEC", "TEMP", "TMP", "LANG", "WINDIR")
        self.env = {k: v for k, v in os.environ.items() if k in temel}
        self.env.update({"HOME": self.home, "USERPROFILE": self.home, "APPDATA": os.path.join(self.home, "AppData", "Roaming"),
                         "LOCALAPPDATA": os.path.join(self.home, "AppData", "Local"), "PYTHONUTF8": "1"})
        self.makine = os.path.join(self.home, ".claude", "orkestra-makine", "makine.json")

    def _temizle(self):
        for _ in range(20):  # arka plan doktor bitmeden klasör silinemez (Windows)
            try:
                self.tmp.cleanup()
                return
            except OSError:
                time.sleep(0.5)

    def kos(self, *argv, girdi=None):
        return subprocess.run([sys.executable, *argv], input=girdi, cwd=self.proje, env=self.env, capture_output=True,
                              text=True, encoding="utf-8", timeout=90)

    def test_doktor_kuru_temiz_makinede_calisir_ve_yazmaz(self):
        r = self.kos(os.path.join(SCRIPTS, "doktor.py"), "--kuru", "--json")
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        s = json.loads(r.stdout)
        self.assertEqual(s["zorunlu_hata"], [])
        self.assertEqual(len(s["kontroller"]), sum(s["ozet"].values()))
        self.assertEqual(os.listdir(self.home), ["AppData"])  # --kuru: ev dizinine hiçbir şey yazılmadı
        self.assertFalse(os.path.exists(os.path.join(self.home, ".claude")))

    @unittest.skipIf(ust_dizinde_orkestra_durumu_var(), ORTAM_KIRLI)
    def test_ilk_oturum_arka_planda_makine_config_yazar(self):
        girdi = json.dumps({"hook_event_name": "SessionStart", "cwd": self.proje, "session_id": "t", "source": "startup"})
        t = time.perf_counter()
        r = self.kos(os.path.join(SCRIPTS, "hook.py"), "SessionStart", girdi=girdi)
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        self.assertLess(time.perf_counter() - t, 10, "hook zaman aşımı sınırına yaklaştı")
        self.assertEqual(r.stdout.strip(), "")  # proje orkestrasız: hook sessiz geçer
        bitis = time.time() + 60
        d = {}
        while time.time() < bitis:
            try:
                with open(self.makine, encoding="utf-8") as f:
                    d = json.load(f)
            except (OSError, ValueError):
                d = {}
            if isinstance(d.get("son_doktor"), dict):
                break
            time.sleep(0.5)
        self.assertIn("python", d.get("degerler", {}), "arka plan doktor makine.json yazmadı")
        self.assertIsInstance(d.get("son_doktor"), dict)
        # yalnız ev dizinine yazıldı; boş proje dizini kirlenmedi
        self.assertEqual(os.listdir(self.proje), [])
        # ikinci oturum doktoru yeniden başlatmaz: makine.json değişmez
        once = os.path.getmtime(self.makine)
        self.kos(os.path.join(SCRIPTS, "hook.py"), "SessionStart", girdi=girdi)
        time.sleep(2)
        self.assertEqual(os.path.getmtime(self.makine), once)


if __name__ == "__main__":
    unittest.main()
