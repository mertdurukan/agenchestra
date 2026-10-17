"""ork_lib.kalem_usd ve kalemler: token ve USD dört kalem kırılımı (I-064 P1).

Kabul kriterleri:
  K1  kalem_usd önbellek yazmayı satırın maliyet_usd'sinden kalan olarak verir; dört kalemin toplamı maliyet_usd'dir.
  K2  maliyet_usd yoksa önbellek yazma 1 sa tarifesiyle fiyatlanır (kullanim_maliyeti ile aynı toplam).
  K3  kalan negatif olamaz (maliyet_usd ilk üç kalemden küçükse yazma 0).
  K4  kalemler token ve USD toplamlarını dört kalem ve 'toplam' ile verir.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import ork_lib as L  # noqa: E402

SATIR = {"model": "claude-opus-5-5", "giris": 1000, "cikis": 2000, "onbellek_okuma": 100000, "onbellek_yazma": 50000}


class KalemUsd(unittest.TestCase):
    def test_k1_kalan_kurali_toplam_defterle_esit(self):
        r = dict(SATIR, maliyet_usd=0.55)
        k = L.kalem_usd(r)
        self.assertAlmostEqual(sum(k.values()), 0.55, places=9)
        self.assertAlmostEqual(k["giris"], 1000 * 4.0 / 1e6, places=9)
        self.assertAlmostEqual(k["cikis"], 2000 * 20.0 / 1e6, places=9)
        self.assertAlmostEqual(k["onbellek_okuma"], 100000 * 0.20 / 1e6, places=9)

    def test_k2_maliyet_yoksa_1sa_tarifesi(self):
        k = L.kalem_usd(SATIR)
        beklenen = L._satir_usd(SATIR)
        self.assertAlmostEqual(sum(k.values()), beklenen, places=9)
        self.assertAlmostEqual(k["onbellek_yazma"], 50000 * 8.0 / 1e6, places=9)

    def test_k3_negatif_olmaz(self):
        k = L.kalem_usd(dict(SATIR, maliyet_usd=0.0))
        self.assertEqual(k["onbellek_yazma"], 0.0)

    def test_k4_kalemler_toplamlar(self):
        s = [dict(SATIR, maliyet_usd=0.55), dict(SATIR, maliyet_usd=0.55)]
        k = L.kalemler(s)
        self.assertEqual(k["token"]["giris"], 2000)
        self.assertEqual(k["token"]["toplam"], 2 * (1000 + 2000 + 100000 + 50000))
        self.assertAlmostEqual(k["usd"]["toplam"], 1.10, places=6)
        self.assertEqual(set(k["usd"]), {"giris", "cikis", "onbellek_okuma", "onbellek_yazma", "toplam"})


if __name__ == "__main__":
    unittest.main()
