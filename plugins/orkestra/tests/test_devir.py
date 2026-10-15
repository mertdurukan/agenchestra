"""devir.devir_metni: şablonlu devir özeti (model yok)."""
import os
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import devir  # noqa: E402


class DevirMetni(unittest.TestCase):
    def test_alanlar_ve_acik_maddeler(self):
        with tempfile.TemporaryDirectory() as k:
            with open(os.path.join(k, "plan.md"), "w", encoding="utf-8") as f:
                f.write("# Plan\n\nFatura ekranını düzelt.\n")
            with open(os.path.join(k, "rapor.md"), "w", encoding="utf-8") as f:
                f.write("x")
            m = devir.devir_metni({"id": "I-009", "baslik": "Fatura", "klasor": k},
                                  {"toplam": 2, "biten": 1, "acik_maddeler": ["testleri koş"]})
        for beklenen in ("I-009", "Fatura ekranını düzelt.", "1/2", "[ ] testleri koş", "rapor.md"):
            self.assertIn(beklenen, m)

    def test_bos_klasor_cokmez(self):
        m = devir.devir_metni({"id": "I-1", "baslik": "B", "klasor": "yok/yol"},
                              {"toplam": 0, "biten": 0, "acik_maddeler": []})
        self.assertIn("(yok)", m)


if __name__ == "__main__":
    unittest.main()
