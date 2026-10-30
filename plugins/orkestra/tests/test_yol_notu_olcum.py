"""I-273 P6: yol notu ölçüm raporu — eşik, örnek büyüklüğü ve aralık kararı."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import yol_notu_olcum as Y  # noqa: E402


def kol(na, ka, nk, kk):
    return {"acik": [na, ka], "kapali": [nk, kk]}


class TestOlcum(unittest.TestCase):
    def test_aday_net_fark(self):
        r = Y.rapor(kol(80, 8, 80, 40))  # %10 ile %50
        self.assertEqual(r["fark_puan"], 40.0)
        self.assertGreater(r["aralik95_puan"][0], 0)
        self.assertIn("aday", r["karar"])

    def test_esik_alti_golgede_kal(self):
        r = Y.rapor(kol(80, 30, 80, 40))  # 12,5 puan
        self.assertEqual(r["karar"], "gölgede kal")

    def test_esik_siniri(self):
        self.assertIn("aday", Y.rapor(kol(80, 40, 80, 56))["karar"])  # tam 20 puan
        self.assertEqual(Y.rapor(kol(80, 41, 80, 56))["karar"], "gölgede kal")  # 18,75 puan

    def test_aralik_alt_siniri_sifirin_altindaysa_aday_degil(self):
        r = Y.rapor(kol(80, 40, 80, 40))
        self.assertLessEqual(r["aralik95_puan"][0], 0)
        self.assertEqual(r["karar"], "gölgede kal")

    def test_az_ornek_yetersiz(self):
        r = Y.rapor(kol(79, 0, 80, 80))
        self.assertIn("yetersiz örnek", r["karar"])

    def test_bos_kol_hata_vermez(self):
        r = Y.rapor(kol(0, 0, 0, 0))
        self.assertIn("yetersiz", r["karar"])

    def test_puan_ve_gunluk_okuma(self):
        with tempfile.TemporaryDirectory() as t:
            p, g = os.path.join(t, "p.jsonl"), os.path.join(t, "gunluk.jsonl")
            with open(p, "w", encoding="utf-8") as f:
                for k, x in (("acik", 0), ("acik", 1), ("kapali", 1), ("kapali", 1), ("diger", 1)):
                    f.write(json.dumps({"kol": k, "kacirilan": x}) + "\nbozuk\n")
            with open(g, "w", encoding="utf-8") as f:
                f.write(json.dumps({"tur": "yol_notu"}) + "\n" + json.dumps({"tur": "baska"}) + "\nbozuk\n")
            self.assertEqual(Y.puanlari_oku(p), {"acik": [2, 1], "kapali": [2, 2]})
            self.assertEqual(Y.yol_notu_say(g), 1)
            self.assertEqual(Y.main(["--puanlar", p, "--gunluk", g]), 0)

    def test_puan_dosyasi_yoksa_hata_kodu(self):
        self.assertEqual(Y.main(["--puanlar", os.path.join(tempfile.gettempdir(), "yok_xyz.jsonl")]), 2)


if __name__ == "__main__":
    unittest.main()
