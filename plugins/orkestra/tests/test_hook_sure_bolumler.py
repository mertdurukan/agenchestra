"""SessionStart bölüm süreleri, hook_basla ve sessionstart_yavas gölge uyarısı (I-314 P3, ADR-0132).

`py -3.13 -m pytest plugins/orkestra/tests/test_hook_sure_bolumler.py`
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import hook  # noqa: E402


class HookSureBolumler(unittest.TestCase):
    def setUp(self):
        self.proje = os.path.realpath(tempfile.mkdtemp(prefix="ork_hb_"))
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(self.sd)

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)

    def _kayitlar(self):
        with open(os.path.join(self.sd, "gunluk.jsonl"), encoding="utf-8") as f:
            return [json.loads(s) for s in f if s.strip()]

    def test_bolumler_ve_yavas_bayragi_yazilir(self):  # S2
        hook._sure_yaz(self.sd, "o1", 350.4, {"hazirlik": 300, "uyarilar": 50})
        k = self._kayitlar()
        self.assertEqual([x["tur"] for x in k], ["hook_sure"])
        self.assertEqual(k[0]["bolumler"], {"hazirlik": 300, "uyarilar": 50})
        self.assertIs(k[0]["yavas"], False)

    def test_10_sn_ustu_sessionstart_yavas_golge_yazar_bolumleri_icerir(self):  # S2/S4
        hook._sure_yaz(self.sd, "o1", 12000, {"uyarilar": 11000})
        k = self._kayitlar()
        self.assertEqual([x["tur"] for x in k], ["hook_sure", "kapi_golge"])
        self.assertIs(k[0]["yavas"], True)
        self.assertEqual(k[1]["kapi"], "sessionstart_yavas")
        self.assertIn("uyarilar", k[1]["neden"])

    def test_hook_basla_kaydi_yazilir_orkestra_acik_degilse_sessiz(self):
        hook._hook_basla({"cwd": self.proje, "session_id": "o2"})
        k = self._kayitlar()
        self.assertEqual((k[0]["tur"], k[0]["oturum"], k[0]["olay"]), ("hook_basla", "o2", "SessionStart"))
        bos = os.path.realpath(tempfile.mkdtemp(prefix="ork_hb_bos_"))
        try:
            hook._hook_basla({"cwd": bos, "session_id": "o3"})  # hata fırlatmaz, dosya açmaz
            self.assertFalse(os.path.exists(os.path.join(bos, ".claude")))
        finally:
            shutil.rmtree(bos, ignore_errors=True)

    def test_gercek_sessionstart_basla_sonra_bolumlu_sure_yazar(self):  # S2 uçtan uca
        env = dict(os.environ, PYTHONUTF8="1")
        r = subprocess.run([sys.executable, os.path.join(KOK, "scripts", "hook.py"), "SessionStart"],
                           input=json.dumps({"cwd": self.proje, "session_id": "o4", "hook_event_name": "SessionStart"}),
                           cwd=self.proje, env=env, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        k = [x for x in self._kayitlar() if x.get("oturum") == "o4"]
        turler = [x["tur"] for x in k]
        self.assertLess(turler.index("hook_basla"), turler.index("hook_sure"))
        sure = next(x for x in k if x["tur"] == "hook_sure")
        for ad in ("hazirlik", "is_durumu", "uyarilar", "perspektif", "satirlar", "devir", "farkindalik"):
            self.assertIn(ad, sure["bolumler"])
        self.assertIn("baglam", turler)


if __name__ == "__main__":
    unittest.main()
