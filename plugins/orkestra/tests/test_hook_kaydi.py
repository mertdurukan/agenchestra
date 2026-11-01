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
        self.assertEqual(H.rapor(self.sd)["hook"]["o1"]["SessionStart"]["zaman_asimi"], 1)

    def test_suresi_dolmamis_isaret_dokunulmaz(self):
        y = H.basla(self.sd, "Stop", "o1")
        self.assertEqual(H.yetim_tara(self.sd), 0)
        self.assertTrue(os.path.exists(y))

    def _yaz(self, **k):
        import ork_lib as L
        L.jsonl_ekle(os.path.join(self.sd, "gunluk.jsonl"), {"zaman": L.simdi(), **k})

    def test_skill_yuklendi_ve_hata_oturum_bazinda(self):
        self._yaz(oturum="o1", tur="skill", skill="devir")
        self._yaz(oturum="o1", tur="skill_hata", skill="caveman")
        r = H.rapor(self.sd)["skill"]["o1"]
        self.assertEqual(r, {"yuklendi": ["devir"], "hata": ["caveman"]})

    def test_acilis_eksik_oturum_yukleme_satiri_yoksa(self):
        H.yukleme_yaz(self.sd, "tamam")
        self._yaz(oturum="tamam", tur="hook_calisma", olay="Stop", sonuc="ok", sure_ms=5)
        self._yaz(oturum="eksik", tur="hook_calisma", olay="Stop", sonuc="ok", sure_ms=5)
        r = H.rapor(self.sd)
        self.assertEqual(r["acilis_eksik"], ["eksik"])
        y = [x for x in self._g() if x["tur"] == "oturum_yukleme"][0]
        self.assertIn("SessionStart", y["hook_olaylari"])
        self.assertGreater(y["skill_sayisi"], 10)

    def test_uyari_zaman_asimi_yoksa_bos_varsa_bir_kez(self):
        self.assertEqual(H.uyari(self.sd), "")
        self._yaz(oturum="o1", tur="hook_zaman_asimi", olay="SessionStart")
        u = H.uyari(self.sd)
        self.assertIn("SessionStart x1", u)
        self.assertLess(len(u), 140)
        self.assertEqual(H.uyari(self.sd), "")  # aynı zaman aşımı ikinci kez bildirilmez

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
