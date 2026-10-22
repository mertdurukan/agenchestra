"""ADR-0029: perspektif talimatı iki yerde yaşar (agents/perspektif-ajani.md ve perspektif.ISTEM); anahtar ifadeler ikisinde de bulunur."""
import os
import re
import sys
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import perspektif as P  # noqa: E402

ANAHTARLAR = (
    "## Doğrulama (P-021)",
    "Geçtiği yerler:",
    "Düzeltme biçimi: kaynakta yeniden yaz, not ekleme",
    "orkestra perspektif dogrula",
    "Öneri yok: <neden>",
    "duzeltme_tekrari",
    "Kanıt:",
)


def _ajan():
    with open(os.path.join(KOK, "agents", "perspektif-ajani.md"), encoding="utf-8") as f:
        return f.read()


class PerspektifTalimat(unittest.TestCase):
    def test_anahtar_ifadeler_iki_kopyada(self):
        ajan, istem = _ajan(), P.ISTEM
        for a in ANAHTARLAR:
            self.assertIn(a, ajan, f"ajan dosyasında yok: {a}")
            self.assertIn(a, istem, f"ISTEM'de yok: {a}")

    def test_dogrulama_bolumu_iki_kopyada_ayni(self):
        def bolum(metin):
            m = re.search(r"## Doğrulama \(P-021\)\n(.*?)(?=\n## |\nKurallar:)", metin, re.S)
            self.assertIsNotNone(m)
            return m.group(1).strip()
        self.assertEqual(bolum(_ajan()), bolum(P.ISTEM))

    def test_istem_bicimlenir(self):
        x = P.ISTEM.format(hafiza="H", proje="P", sd="S")
        self.assertIn("Geçtiği yerler:", x)

    def test_akista_dogrula_kaydetten_once(self):
        ajan = _ajan()
        self.assertLess(ajan.index("perspektif dogrula <rapor yolu>"), ajan.index("perspektif kaydet <rapor yolu>"))


if __name__ == "__main__":
    unittest.main()