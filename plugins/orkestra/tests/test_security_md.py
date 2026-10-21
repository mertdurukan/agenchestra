"""I-139 P4 (bce F67): SECURITY.md var, bilinen sınırları söyler, anılan ADR'ler gerçekten var, metinde sır yok."""
import glob
import os
import re
import sys
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import sir_yakala  # noqa: E402

DEPO = os.path.dirname(os.path.dirname(KOK))
YOL = os.path.join(DEPO, "SECURITY.md")


def _adr_dizini():
    """ADR'ler eklentiyi kullanan projededir; ORKESTRA_ADR_DIZINI ya da bu makinedeki McD projesi. Yoksa None."""
    for d in (os.environ.get("ORKESTRA_ADR_DIZINI"), r"C:\Mert\McD\adr"):
        if d and os.path.isdir(d):
            return d
    return None


class SecurityMd(unittest.TestCase):
    def setUp(self):
        with open(YOL, encoding="utf-8") as f:
            self.metin = f.read()

    def test_bilinen_sinirlar_basligi_ve_maddeleri(self):
        m = re.search(r"^## Bilinen sınırlar\s*\n(.*?)(?=^## |\Z)", self.metin, re.S | re.M)
        self.assertIsNotNone(m, "## Bilinen sınırlar başlığı yok")
        self.assertGreaterEqual(len(re.findall(r"^- ", m.group(1), re.M)), 3)

    def test_anilan_adr_dosyalari_var(self):
        kimlikler = sorted(set(re.findall(r"ADR-\d{4}", self.metin)))
        self.assertGreaterEqual(len(kimlikler), 5)
        dizin = _adr_dizini()
        if dizin is None:
            self.skipTest("ADR dizini bulunamadı (ORKESTRA_ADR_DIZINI)")
        for k in kimlikler:
            self.assertTrue(glob.glob(os.path.join(dizin, k + "-*.md")), f"{k} için ADR dosyası yok")

    def test_metinde_sir_kalibi_eslesmez(self):
        self.assertEqual(sir_yakala.yakala(self.metin), [])
        self.assertEqual(sir_yakala.yakala_serbest(self.metin), [])

    def test_anilan_ayar_dosyalari_var(self):
        for ad in sorted(set(re.findall(r"`ayarlar/([\w.]+\.json)`", self.metin))):
            self.assertTrue(os.path.isfile(os.path.join(KOK, "ayarlar", ad)), ad)


if __name__ == "__main__":
    unittest.main()
