"""ork_lib.model_fiyati: model başına önbellek; fiyat tablosu nesnesi değişince yeni değer.

`python -m unittest discover -s plugins/orkestra/tests -p test_model_fiyati_onbellek.py -v`
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import ork_lib as L  # noqa: E402


def _tablo(giris):
    return {"varsayilan": "x", "modeller": {"x": {"giris": 1}, "claude-opus": {"giris": giris},
                                              "claude-opus-5": {"giris": giris + 1}}}


class ModelFiyatiOnbellekTesti(unittest.TestCase):
    def test_en_uzun_onek_kazanir_ve_onbellekten_gelir(self):
        t = _tablo(10)
        a = L.model_fiyati("claude-opus-5-5[1m]", t)
        self.assertEqual(a["giris"], 11)
        self.assertIs(L.model_fiyati("claude-opus-5-5[1m]", t), a)

    def test_bilinmeyen_model_varsayilana_duser(self):
        self.assertEqual(L.model_fiyati("baska", _tablo(10))["giris"], 1)
        self.assertEqual(L.model_fiyati(None, _tablo(10))["giris"], 1)

    def test_tablo_degisince_yeni_deger(self):
        self.assertEqual(L.model_fiyati("claude-opus-4", _tablo(10))["giris"], 10)
        self.assertEqual(L.model_fiyati("claude-opus-4", _tablo(20))["giris"], 20)

    def test_varsayilan_tabloyla_tutarli(self):
        t = L.fiyat_tablosu()
        for m in list(t["modeller"])[:3] + ["bilinmeyen-model"]:
            self.assertEqual(L.model_fiyati(m), L.model_fiyati(m, t))


if __name__ == "__main__":
    unittest.main()
