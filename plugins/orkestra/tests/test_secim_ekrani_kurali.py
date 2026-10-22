"""P-028: karar anlarında seçim ekranı kuralı (ADR-0035) ve altyapısı.
`py -3.13 -m pytest -q plugins/orkestra/tests/test_secim_ekrani_kurali.py`
Eklenti deposundaki gerçek kural dosyasını salt okur; hiçbir şey yazmaz.
"""
import json
import os
import sys
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import is_onay  # noqa: E402

KURALLAR = os.path.join(KOK, "kurallar", "eklenti_kurallari.json")


def kural(kid: str) -> dict:
    with open(KURALLAR, encoding="utf-8") as f:
        liste = json.load(f)["kurallar"]
    bulunan = [k for k in liste if k["id"] == kid]
    assert bulunan, f"{kid} eklenti kurallarında yok"
    return bulunan[0]


class SecimEkraniKurali(unittest.TestCase):
    def test_p028_var_ve_etkin_eklenti_katmaninda(self):
        k = kural("P-028")
        self.assertEqual(k["durum"], "etkin")
        self.assertEqual(k["katman"], "plugin")
        self.assertTrue(k["metin"].startswith("ZORUNLU, istisnasız:"))

    def test_p028_anahtar_ifadeler(self):
        m = kural("P-028")["metin"]
        for parca in ("AskUserQuestion", "wrap_up", "2-4 seçenek", "ilk sırada", "izin sistemi", "doğrulanamadı",
                      "birden çok yol", "Kapsam dışı", "bilgi soruları", "Alt ajan"):
            self.assertIn(parca, m)

    def test_p008_p028e_atif_yapar(self):
        self.assertIn("P-028", kural("P-008")["metin"])

    def test_tur_bitiren_secim_araclarini_icerir(self):
        self.assertIn("AskUserQuestion", is_onay.TUR_BITIREN)
        self.assertIn("wrap_up", is_onay.TUR_BITIREN)

    def test_p028_kimligi_tekrarsiz(self):
        with open(KURALLAR, encoding="utf-8") as f:
            idler = [k["id"] for k in json.load(f)["kurallar"]]
        self.assertEqual(idler.count("P-028"), 1)


if __name__ == "__main__":
    unittest.main()
