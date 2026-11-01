import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import hook_kaydi as H  # noqa: E402


class HookKaydiTest(unittest.TestCase):
    def setUp(self):
        self.sd = tempfile.mkdtemp(prefix="ork_hk_")

    def _g(self):
        try:
            with open(os.path.join(self.sd, "gunluk.jsonl"), encoding="utf-8") as f:
                return [json.loads(x) for x in f if x.strip()]
        except OSError:
            return []

    def test_normal_bitis_isareti_siler_ve_satir_yazar(self):
        y = H.basla(self.sd, "Stop", "o1")
        self.assertTrue(os.path.exists(y))
        H.bitir(self.sd, y, "Stop", "o1", None, "ok", 120)
        self.assertFalse(os.path.exists(y))
        self.assertEqual([x["tur"] for x in self._g()], ["hook_calisma"])

    def test_hizli_pretooluse_satir_yazmaz_yavas_yazar(self):
        H.bitir(self.sd, H.basla(self.sd, "PreToolUse", "o1", "Bash"), "PreToolUse", "o1", "Bash", "ok", 40)
        self.assertEqual(self._g(), [])
        H.bitir(self.sd, H.basla(self.sd, "PreToolUse", "o1", "Bash"), "PreToolUse", "o1", "Bash", "ok", 1500)
        self.assertEqual(len(self._g()), 1)

    def test_oldurulmus_hook_zaman_asimi_olarak_kaydedilir(self):
        y = H.basla(self.sd, "SessionStart", "o1")
        with open(y, encoding="utf-8") as f:
            k = json.load(f)
        k["pid"] = 2 ** 22 + 12345  # ölü süreç
        k["t"] = time.time() - 60
        with open(y, "w", encoding="utf-8") as f:
            json.dump(k, f)
        self.assertEqual(H.yetim_tara(self.sd), 1)
        self.assertEqual(H.yetim_tara(self.sd), 0)
        g = self._g()
        self.assertEqual(g[0]["tur"], "hook_zaman_asimi")
        self.assertEqual(g[0]["olay"], "SessionStart")
        self.assertEqual(H.rapor(self.sd)["o1"]["SessionStart"]["zaman_asimi"], 1)

    def test_suresi_dolmamis_isaret_dokunulmaz(self):
        y = H.basla(self.sd, "Stop", "o1")
        self.assertEqual(H.yetim_tara(self.sd), 0)
        self.assertTrue(os.path.exists(y))

    def test_zaman_asimlari_hooks_json_ile_uyumlu(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "hooks", "hooks.json"), encoding="utf-8") as f:
            h = json.load(f)["hooks"]
        for olay, bloklar in h.items():
            for b in bloklar:
                for k in b["hooks"]:
                    if "hook.py" in k["command"]:
                        self.assertEqual(k["timeout"], H.ZA_S.get(olay, H.VARSAYILAN_ZA_S), olay)


if __name__ == "__main__":
    unittest.main()
