"""I-319 P1: plan şablonlarındaki `**Üretim noktası:**` örnek satırı kapı ayrıştırıcısından geçer (madde işaretli örnek yok)."""
import os
import re
import sys
import unittest

KOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(KOK, "scripts"))
import is_sirasi as S  # noqa: E402

SABLONLAR = ("plan_sirali.md", "plan_dogrulamali.md")


def _oku(ad):
    with open(os.path.join(KOK, "sablonlar", ad), encoding="utf-8") as f:
        return f.read()


class SablonUretimOrnegi(unittest.TestCase):
    def test_ornek_satir_ayristiricidan_gecer(self):
        for ad in SABLONLAR:
            metin = _oku(ad)
            satirlar = [s for s in metin.splitlines()
                        if s.startswith("**Üretim noktası:**") and "<" in s]
            self.assertEqual(len(satirlar), 1, ad)
            deger = satirlar[0].split(":**", 1)[1].strip()
            # yer ve önleme yer tutucularını gerçek metinle doldur
            deger = re.sub(r"<kural\|[^>]*>", "kural", deger)
            deger = re.sub(r"<orada önleme[^>]*>", "soru plan yazılırken şablonda hazır durur", deger)
            tur, _yer, _g, hata = S.uretim_alan_ayristir(deger)
            self.assertIsNone(hata, f"{ad}: {hata}")
            self.assertEqual(tur, "duzeltme")
            self.assertTrue(S._uretim_yer_gecerli(_yer))

    def test_sablonda_madde_isaretli_ornek_yok(self):
        for ad in SABLONLAR:
            self.assertNotRegex(_oku(ad), r"(?m)^- `(Düzeltme|Kontrol|Yeni yetenek)")

    def test_enjeksiyon_ornegi_madde_isaretsiz(self):
        with open(os.path.join(KOK, "ayarlar", "uretim_enjeksiyonu.json"), encoding="utf-8") as f:
            self.assertIn("**Üretim noktası:** Düzeltme:", f.read())


if __name__ == "__main__":
    unittest.main()
