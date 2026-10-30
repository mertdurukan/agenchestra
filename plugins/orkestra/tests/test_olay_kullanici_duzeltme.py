"""Kullanıcı itirazı tespiti (I-286 P3): 5 düzeltme örneği olay üretir, 5 normal mesaj üretmez; boş kalıp listesi tür üretmez."""
import os
import sys
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import olay_duzeltme as D  # noqa: E402
import olay_kaydi as O  # noqa: E402

_, AYAR = O.ayar_yukle()

DUZELTME = [
    "Hayır, bunu istemedim",
    "yanlış anladın, tekrar bak",
    "bunu yapma, dosyayı silme",
    "böyle olmaz, başlığı değiştir",
    "Düzelt şunu: yanlış sayı yazmışsın",
]
NORMAL = [
    "Onaylıyorum",
    "planı oku ve özetle",
    "tabloya bir sütun ekle",
    "bu dosyada kaç satır var?",
    "devam et",
]


def istek(m):
    return {"zaman": "2026-10-30T10:00:00+03:00", "tur": "istek", "metin": m}


class DuzeltmeTesti(unittest.TestCase):
    def test_duzeltme_ornekleri_olay_uretir(self):
        for m in DUZELTME:
            self.assertEqual(len(D.bul([istek(m)], AYAR)), 1, m)

    def test_normal_mesaj_olay_uretmez(self):
        for m in NORMAL:
            self.assertEqual(D.bul([istek(m)], AYAR), [], m)

    def test_istek_disi_satir_atlanir(self):
        self.assertEqual(D.bul([{"tur": "ajan", "metin": "hayır"}], AYAR), [])

    def test_bos_kalip_listesi_tur_uretmez(self):
        self.assertEqual(D.bul([istek(DUZELTME[0])], dict(AYAR, duzeltme_kaliplari=[])), [])

    def test_bozuk_kalip_atlanir(self):
        ayar = dict(AYAR, duzeltme_kaliplari=[{"id": "x", "desen": "("}, {"id": "y", "desen": "hayır"}])
        self.assertEqual(D.bul([istek("hayır")], ayar)[0]["imza"], "duzeltme:y")

    def test_okuyucu_bu_turu_birlestirir(self):
        kat, ayar = O.ayar_yukle()
        olaylar = O.olaylari_cikar([istek(DUZELTME[0])], [], kat, ayar, D.bul([istek(DUZELTME[0])], ayar))
        self.assertEqual(O.tur_adetleri(olaylar), {"kullanici_duzeltme": 1})


if __name__ == "__main__":
    unittest.main()
