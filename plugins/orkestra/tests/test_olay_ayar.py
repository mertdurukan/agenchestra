"""Olay kaydı ayarları (I-286 P1): kategori eşlemesi ve gölge kapı modu."""
import json
import os
import re
import sys
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import kapi_mod  # noqa: E402

AYAR = os.path.join(KOK, "ayarlar")

# 30.10.2026 17:28 gunluk.jsonl'da görülen kural_ihlal kuralları (betikle sayıldı)
GORULEN_KURALLAR = ["belge_bicim", "belge_baglantisi_yok", "kimlik_once_bak", "secim_ekrani_yapisal", "secim_ekrani",
                    "konu_disi_oneri", "kapanis_atlandi", "kanitsiz_iddia", "plan_dogrulama", "genis_tarama"]


def yukle(ad):
    with open(os.path.join(AYAR, ad), encoding="utf-8") as f:
        return json.load(f)


class OlayAyarTesti(unittest.TestCase):
    def test_iki_dosya_gecerli_json(self):
        self.assertIsInstance(yukle("olay_kategorileri.json"), dict)
        self.assertIsInstance(yukle("olay_kaydi.json"), dict)

    def test_kapi_modu_golge(self):
        self.assertEqual(kapi_mod.mod("olay_kaydi"), "golge")

    def test_gorulen_kurallar_eslemede_ya_da_diger(self):
        k = yukle("olay_kategorileri.json")
        for kural in GORULEN_KURALLAR:
            e = k["kural_ihlal"].get(kural, k["varsayilan"])
            self.assertIn(e.get("tur", "kapi_ret"), k["turler"] + ["kapi_ret"])
            self.assertTrue(e["ana"] and e["alt"], kural)

    def test_esleme_turleri_gecerli(self):
        k = yukle("olay_kategorileri.json")
        for bolum in ("kural_ihlal", "davranis_sinif"):
            for ad, e in k[bolum].items():
                self.assertIn(e["tur"], k["turler"], ad)

    def test_esikler_ve_kaliplar(self):
        a = yukle("olay_kaydi.json")
        self.assertEqual(a["oneri_esik"], {"n_min": 5, "wilson_alt_min": 0.5})
        self.assertEqual(a["pencere_gun"], 7)
        for kalip in a["duzeltme_kaliplari"]:
            re.compile(kalip["desen"], re.IGNORECASE)


if __name__ == "__main__":
    unittest.main()
