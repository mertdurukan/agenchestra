"""Gidiş yolu önerisi (I-286 P4): n=4 öneri yok, n=5 ve 5/5 öneri var, alt sınır 0,49 öneri yok."""
import os
import sys
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import olay_yol as Y  # noqa: E402
import olay_kaydi as O  # noqa: E402
from kanit_olcum import wilson  # noqa: E402

_, AYAR = O.ayar_yukle()


def ol(sonuc, n, tur="kapi_ret", alt="a"):
    return [{"tur": tur, "ana_kategori": "x", "alt_kategori": alt, "sonuc": sonuc} for _ in range(n)]


class YolTesti(unittest.TestCase):
    def test_n4_oneri_yok(self):
        self.assertEqual(Y.oneriler(ol("duzeldi", 4), AYAR), [])

    def test_n5_hepsi_duzeldi_oneri_var(self):
        o = Y.oneriler(ol("duzeldi", 5), AYAR)
        self.assertEqual(len(o), 1)
        self.assertIn("a:", o[0]["oneri"])

    def test_alt_sinir_esik_altinda_oneri_yok(self):
        # 7 düzeldi + 5 tekrarladi: alt sınır < 0,5
        olaylar = ol("duzeldi", 7) + ol("tekrarladi", 5)
        self.assertLess(wilson(7, 12)[0], 0.5)
        self.assertEqual(Y.oneriler(olaylar, AYAR), [])

    def test_alt_sinir_0_49_oneri_yok(self):
        # 0,49'a yakın: 8/15 -> alt sınır ~0,27; eşiğe en yakın küçük n örneği
        for a, n in ((3, 5), (4, 6), (5, 8)):
            self.assertLess(wilson(a, n)[0], 0.5)
            self.assertEqual(Y.oneriler(ol("duzeldi", a) + ol("tekrarladi", n - a), AYAR), [])

    def test_acik_olaylar_paydaya_girmez(self):
        self.assertEqual(Y.oneriler(ol("duzeldi", 4) + ol("acik", 10), AYAR), [])

    def test_duzeltme_turu_varsayilan_oneriye_girmez(self):
        self.assertEqual(Y.oneriler(ol("duzeldi", 6, tur="kullanici_duzeltme"), AYAR), [])
        self.assertEqual(len(Y.oneriler(ol("duzeldi", 6, tur="kullanici_duzeltme"), dict(AYAR, duzeltme_oneriye_girer=True))), 1)


if __name__ == "__main__":
    unittest.main()
