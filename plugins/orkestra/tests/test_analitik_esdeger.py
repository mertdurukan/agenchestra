"""P2 (I-315): kart başına tam defter taramasının indekse çevrilmesi çıktıyı değiştirmez."""
import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import analitik as A  # noqa: E402


def _z(dk):
    return (datetime.datetime(2026, 11, 1, 10, 0, 0).astimezone() + datetime.timedelta(minutes=dk)).isoformat()


class AkisIndeksEsdegerligi(unittest.TestCase):
    def _kart(self, kid):
        return {"id": kid, "baslik": kid, "olusturma": _z(0), "gecmis": [
            {"zaman": _z(1), "olay": "isleniyor"}, {"zaman": _z(5), "olay": "is-bitti"},
            {"zaman": _z(12), "olay": "denetim:onay"}, {"zaman": _z(13), "olay": "teslim"}]}

    def test_denetci_koşusu_olmayan_kart_ayrilmaz_olarak_isaretlenir(self):
        # denetim-basladi olayı yok, denetçi kaydı yok -> bekleme/çalışma None (eski davranış)
        s = A._akis_kartlari([self._kart("K1")], [])[0]
        self.assertIsNone(s["denetim_bekleme_dk"])
        self.assertEqual(s["denetim_toplam_dk"], 7.0)

    def test_denetci_kaydi_yalniz_kendi_kartina_uygulanir(self):
        # K1 için denetçi 6. dk'da başlayıp 12'de biter; K2'nin kaydı K1'in sonucunu etkilememeli
        kayitlar = [
            {"gorev": "K1", "ajan": "orkestra:denetci", "sure_ms": 6 * 60000, "zaman": _z(12)},
            {"gorev": "K2", "ajan": "orkestra:denetci", "sure_ms": 1 * 60000, "zaman": _z(12)},
            {"gorev": "K1", "ajan": "orkestra:isci-t2", "sure_ms": 6 * 60000, "zaman": _z(12)},  # işçi sayılmaz
            {"gorev": "K1", "ajan": "orkestra:denetci", "sure_ms": 0, "zaman": _z(12)},          # süresiz sayılmaz
        ]
        k1, k2 = A._akis_kartlari([self._kart("K1"), self._kart("K2")], kayitlar)
        self.assertEqual((k1["denetim_bekleme_dk"], k1["denetim_calisma_dk"]), (1.0, 6.0))
        self.assertEqual((k2["denetim_bekleme_dk"], k2["denetim_calisma_dk"]), (6.0, 1.0))

    def test_indeks_eski_taramayla_ayni_sonucu_verir(self):
        kayitlar = [{"gorev": "K1", "ajan": "orkestra:denetci", "sure_ms": 6 * 60000, "zaman": _z(12)},
                    {"gorev": "K1", "ajan": "orkestra:denetci", "sure_ms": 9 * 60000, "zaman": _z(12)}]
        bitis, karar = A._zaman(_z(5)), A._zaman(_z(12))
        tam = A._denetci_basi("K1", kayitlar, bitis, karar)
        idx = [r for r in kayitlar if r.get("gorev") == "K1" and r.get("sure_ms") and A._rol(r.get("ajan")) == "denetci"]
        self.assertEqual(tam, A._denetci_basi("K1", idx, bitis, karar))


if __name__ == "__main__":
    unittest.main()
