"""P5 (I-315): ölçüm betiğinin saf parçaları (HTTP'siz)."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import panel_olcum as O  # noqa: E402


class OlcumTesti(unittest.TestCase):
    def test_yuzdelik_ve_ozet(self):
        s = [0.1] * 19 + [3.0]
        o = O._ozet(s)
        self.assertEqual(o["medyan_s"], 0.1)
        self.assertEqual(o["en_yavas_s"], 3.0)
        self.assertEqual(O._yuzdelik(s, 0.95), 0.1)
        self.assertEqual(O._yuzdelik(s, 1.0), 3.0)

    def test_etiket_kalani_yeni_satiri_yakalar(self):
        simdi = O.L.simdi()
        satirlar = [{"surec": "tip-okunamadi", "zaman": "2026-10-20T10:00:00+03:00"}, {"ajan": "?", "zaman": simdi},
                    {"surec": "is", "ajan": "ana-ajan", "zaman": simdi}]
        with mock.patch.object(O.L, "maliyet_kayitlari", return_value=satirlar):
            r = O.etiket_kalani("sd")
        self.assertEqual(r["toplam"], 2)
        self.assertEqual(r["son_24_saat"], 1)
        self.assertFalse(r["tamam"])


if __name__ == "__main__":
    unittest.main()
