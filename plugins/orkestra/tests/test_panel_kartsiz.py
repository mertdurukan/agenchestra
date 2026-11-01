"""I-315 P1: kart listesi yalnız görevli satırlardan gelir; görevsiz harcama `kartsiz` alanında açıkça verilir (boş durum yalan söylemez)."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_panel_pencere_alanlari as T  # noqa: E402
import analitik as A  # noqa: E402
import ork_lib as L  # noqa: E402
import panel_tum as PT  # noqa: E402

KAYITLAR = [T.satir(0, 5.0, 500, gorev="-"), T.satir(0, 2.0, 200, gorev=None), T.satir(1, 3.0, 300, gorev="-")]


def pencereli(kayitlar):
    with mock.patch.object(L, "kart_durumu_hesapla", lambda k: k["durum"]):
        return A._pencereli([], kayitlar, [], T.BUGUN)


class Kartsiz(unittest.TestCase):
    def test_kartsiz_harcama_varken_kart_listesi_bos_ama_tutar_yazilir(self):
        p = pencereli(KAYITLAR)
        self.assertEqual(p["bugun"]["en_pahali"], [])   # ihlal vakası: eski arayüz bundan "harcama yok" üretiyordu
        self.assertEqual(p["bugun"]["kartsiz"], {"usd": 7.0, "token": 700})
        self.assertEqual(p["tum_zaman"]["kartsiz"], {"usd": 10.0, "token": 1000})

    def test_kartli_ve_kartsiz_toplami_pencere_toplamina_esit(self):
        kayitlar = KAYITLAR + [T.satir(0, 1.5, 150, gorev="G-1")]
        p = pencereli(kayitlar)
        kartli = sum(v for _, v in p["bugun"]["en_pahali"])
        self.assertAlmostEqual(kartli + p["bugun"]["kartsiz"]["usd"], L.pencere_toplamlari(kayitlar, T.BUGUN)["bugun"]["usd"])

    def test_birlesik_gorunum_alanlari_toplar(self):
        a = {"pencere": {w: {"kartsiz": {"usd": 1.25, "token": 10}} for w in L.PENCERELER}}
        b = {"pencere": {w: {"kartsiz": {"usd": 2.0, "token": 5}} for w in L.PENCERELER}}
        ok = [({"id": "A"}, a), ({"id": "B"}, b)]
        p = PT._pencere(ok, [])
        self.assertEqual(p["bugun"]["kartsiz"], {"usd": 3.25, "token": 15})


if __name__ == "__main__":
    unittest.main()
