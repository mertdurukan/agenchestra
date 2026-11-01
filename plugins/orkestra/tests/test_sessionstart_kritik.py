"""Kritik SessionStart bağlamı bağımsız ikinci hook'ta (ADR-0132, I-314 P2).

`py -3.13 -m pytest plugins/orkestra/tests/test_sessionstart_kritik.py`
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KRITIK = os.path.join(KOK, "scripts", "sessionstart_kritik.py")
HOOK = os.path.join(KOK, "scripts", "hook.py")
BASLIK = "[Sürekli açık skill: orkestra:caveman]"


def kos(cwd, **env_ek):
    env = dict(os.environ, PYTHONUTF8="1", ORKESTRA_SKILL_SUREKLI="1")  # conftest varsayılanı 0
    env.update(env_ek)
    return subprocess.run([sys.executable, KRITIK], input=json.dumps({"cwd": cwd, "session_id": "kr-1"}), cwd=cwd,
                          env=env, capture_output=True, text=True, encoding="utf-8")


class SessionStartKritik(unittest.TestCase):
    def setUp(self):
        self.proje = os.path.realpath(tempfile.mkdtemp(prefix="ork_kr_"))
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(self.sd)

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)

    def test_caveman_govdesi_ve_kural_yolu_cikar_kayit_yazilir(self):  # S3
        r = kos(self.proje)
        self.assertEqual(r.returncode, 0, r.stderr)
        ek = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn(BASLIK, ek)
        self.assertIn("Kurallar:", ek)
        with open(os.path.join(self.sd, "gunluk.jsonl"), encoding="utf-8") as f:
            kayit = [json.loads(s) for s in f if '"baglam_kritik"' in s]
        self.assertEqual(len(kayit), 1)
        self.assertEqual(kayit[0]["oturum"], "kr-1")
        self.assertIn("surum", kayit[0])
        self.assertEqual(kayit[0]["uzunluk"], len(ek))

    def test_orkestra_acik_olmayan_projede_sessiz(self):
        bos = os.path.realpath(tempfile.mkdtemp(prefix="ork_kr_bos_"))
        try:
            r = kos(bos)
            self.assertEqual((r.returncode, r.stdout.strip()), (0, ""))
        finally:
            shutil.rmtree(bos, ignore_errors=True)

    def test_kapatma_ortami_icerigi_keser(self):
        r = kos(self.proje, ORKESTRA_SKILL_SUREKLI="0")
        ek = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"] if r.stdout.strip() else ""
        self.assertNotIn(BASLIK, ek)

    def test_ana_hook_yavasligindan_bagimsiz_30_tekrar_p95_3sn(self):  # S3: ana hook 30 sn uyurken kritik hook ayrı süreçte teslim eder
        ana = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])  # yavaş ana hook benzetimi
        try:
            sureler = []
            for _ in range(30):
                t = time.perf_counter()
                r = kos(self.proje)
                sureler.append(time.perf_counter() - t)
                self.assertIn(BASLIK, json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"])
            sureler.sort()
            self.assertLessEqual(sureler[int(0.95 * len(sureler)) - 1], 3.0, sureler)
        finally:
            ana.kill()

    def test_ana_hook_artik_skill_baglami_uretmez_hooks_json_ikinci_komutu_icerir(self):  # S4: eski yapıda kırmızı
        with open(HOOK, encoding="utf-8") as f:
            self.assertNotIn("skill_surekli.baglam", f.read())
        with open(os.path.join(KOK, "hooks", "hooks.json"), encoding="utf-8") as f:
            komutlar = [h["command"] for g in json.load(f)["hooks"]["SessionStart"] for h in g["hooks"]]
        self.assertEqual(len(komutlar), 2)
        kritik = [k for k in komutlar if "sessionstart_kritik.py" in k]
        self.assertEqual(len(kritik), 1)
        s = '"${CLAUDE_PLUGIN_ROOT}/scripts/sessionstart_kritik.py"'  # ana hook ile aynı python/py -3/python3 seçicisi
        self.assertEqual(kritik[0], f"if command -v python >/dev/null 2>&1; then exec python {s}; "
                                    f"elif command -v py >/dev/null 2>&1; then exec py -3 {s}; else exec python3 {s}; fi")
        self.assertTrue(any("hook.py" in k and "SessionStart" in k for k in komutlar))


if __name__ == "__main__":
    unittest.main()
