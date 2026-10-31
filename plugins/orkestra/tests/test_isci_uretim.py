"""İşçi ajanları tek kaynaktan üretilir: üretilen = depodaki (I-292 P2)."""
import json
import os
import sys
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import ajan_uret  # noqa: E402


class IsciUretim(unittest.TestCase):
    def test_uretilen_depodakiyle_ayni(self):
        cikti = ajan_uret.uret()
        self.assertEqual(sorted(cikti), ["isci-t1.md", "isci-t2.md", "isci-t3.md", "isci-t4.md"])
        for ad, icerik in cikti.items():
            with open(os.path.join(KOK, "agents", ad), encoding="utf-8", newline="") as f:
                self.assertEqual(f.read(), icerik, ad + ": python scripts/ajan_uret.py çalıştır")

    def test_model_politikadan_gelir(self):
        with open(os.path.join(KOK, "ayarlar", "model_politikasi.json"), encoding="utf-8") as f:
            pol = json.load(f)
        pol["basamak"]["T3"] = {"model": "sonnet", "effort": "high"}
        t3 = ajan_uret.uret(politika=pol)["isci-t3.md"]
        self.assertIn("\nmodel: sonnet\neffort: high\n", t3)
        self.assertIn("(T3 · Sonnet · high)", t3)

    def test_govde_tum_basamaklarda_ortak(self):
        cikti = ajan_uret.uret()
        govdeler = {ad: i.split("\n---\n", 1)[1].split("\n", 1)[1] for ad, i in cikti.items()}
        self.assertEqual(len(set(govdeler.values())), 1)


if __name__ == "__main__":
    unittest.main()
