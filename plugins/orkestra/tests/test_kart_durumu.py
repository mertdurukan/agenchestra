"""kart_durumu_hesapla: son denetim kararı geçerli; teslim/iptal yapışkan; beklemede yalnız sonrasında denetim yoksa."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import ork_lib as L  # noqa: E402


def d(sira, karar, zaman=None):
    x = {"sira": sira, "karar": karar}
    if zaman:
        x["zaman"] = zaman
    return x


def kart(durum="denetimde", denetimler=(), **ek):
    k = {"durum": durum, "son_is_sira": 1, "son_is_zamani": "2026-10-13T10:00:00+03:00",
         "denetimler": list(denetimler), "gecmis": []}
    k.update(ek)
    return k


class KartDurumuTest(unittest.TestCase):
    def test_ret_sonra_onay_onaylandi(self):
        self.assertEqual(L.kart_durumu_hesapla(kart(denetimler=[d(2, "ret"), d(3, "onay")])), "onaylandi")

    def test_onay_sonra_ret_reddedildi(self):
        self.assertEqual(L.kart_durumu_hesapla(kart(denetimler=[d(2, "onay"), d(3, "ret")])), "reddedildi")

    def test_ret_beklemede_onay_yeni_kart(self):
        k = kart("beklemede", [d(2, "ret"), d(4, "onay")], beklemede_sira=3)
        self.assertEqual(L.kart_durumu_hesapla(k), "onaylandi")

    def test_ret_beklemede_onay_eski_kart_zaman(self):
        k = kart("beklemede", [d(2, "ret", "2026-10-13T14:41:03+03:00"), d(3, "onay", "2026-10-13T15:07:46+03:00")],
                 gecmis=[{"zaman": "2026-10-13T14:41:37+03:00", "olay": "beklemede"}])
        self.assertEqual(L.kart_durumu_hesapla(k), "onaylandi")

    def test_beklemede_sonra_denetim_yok(self):
        self.assertEqual(L.kart_durumu_hesapla(kart("beklemede", [d(2, "ret")], beklemede_sira=3)), "beklemede")
        k = kart("beklemede", [d(2, "ret", "2026-10-13T14:41:03+03:00")],
                 gecmis=[{"zaman": "2026-10-13T14:41:37+03:00", "olay": "beklemede"}])
        self.assertEqual(L.kart_durumu_hesapla(k), "beklemede")

    def test_beklemede_sonra_ret(self):
        k = kart("beklemede", [d(2, "onay"), d(4, "ret")], beklemede_sira=3)
        self.assertEqual(L.kart_durumu_hesapla(k), "reddedildi")

    def test_teslim_ve_iptal_yapiskan(self):
        for durum in ("teslim", "iptal"):
            self.assertEqual(L.kart_durumu_hesapla(kart(durum, [d(2, "ret")])), durum)

    def test_yeni_is_sonrasi_eski_onay_sayilmaz(self):
        k = kart(denetimler=[d(2, "onay")], son_is_sira=3)
        self.assertEqual(L.kart_durumu_hesapla(k), "denetimde")

    def test_siraya_gore_liste_sirasi_onemsiz(self):
        self.assertEqual(L.kart_durumu_hesapla(kart(denetimler=[d(3, "onay"), d(2, "ret")])), "onaylandi")

    def test_denetim_yok_is_yok(self):
        self.assertEqual(L.kart_durumu_hesapla({"durum": "planlandi", "denetimler": []}), "planlandi")


if __name__ == "__main__":
    unittest.main()
