"""Ajan metinleri ile kaynakları eşit: sabit sayı, çift model adı ve ret kodu listesi (I-292 P1)."""
import glob
import os
import re
import sys
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import ret_nedeni  # noqa: E402

AJANLAR = sorted(glob.glob(os.path.join(KOK, "agents", "*.md")))
MODEL_ADI = re.compile(r"\b(?:Haiku|Sonnet|Opus)\b")


def oku(ad):
    with open(os.path.join(KOK, "agents", ad + ".md"), encoding="utf-8") as f:
        return f.read()


class AjanMetinKaynak(unittest.TestCase):
    def test_denetci_ret_kodlari_kaynakla_esit(self):
        govde = oku("denetci").split("## Ret nedeni", 1)[1].split("CLI örneği", 1)[0]
        metinde = set(re.findall(r"^- `([a-z-]+)`:", govde, re.M))
        self.assertEqual(metinde, set(ret_nedeni.NEDENLER))

    def test_ret_kodu_sayisi_metinde_yok(self):
        self.assertIsNone(re.search(r"\b\d+ kod", oku("denetci")))

    def test_skill_esigi_sabit_sayi_degil(self):
        for ad in ("skill-avcisi", "perspektif-ajani"):
            self.assertIn("sayac.py esik", oku(ad))
        self.assertNotRegex(oku("skill-avcisi"), r"en az \d+ kez")
        self.assertNotRegex(oku("perspektif-ajani"), r"en az \d+ kez tekrar")

    def test_description_model_adi_yok(self):
        for yol in AJANLAR:
            for satir in open(yol, encoding="utf-8"):
                if satir.startswith("description:"):
                    self.assertIsNone(MODEL_ADI.search(satir), os.path.basename(yol))

    def test_triyaj_basamak_modeli_politikadan(self):
        t = oku("triyaj")
        for b in ("T1", "T2", "T3", "T4"):
            self.assertRegex(t, rf"\*\*{b}\*\* \(model/effort: ayarlar/model_politikasi\.json\)")


if __name__ == "__main__":
    unittest.main()
