"""Olay okuyucu ve sonuç türetimi (I-286 P2): 6., 7., 8. gün sınırları, tür birleştirme, yazmama."""
import datetime
import os
import sys
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import olay_kaydi as O  # noqa: E402

T0 = datetime.datetime(2026, 10, 1, 12, 0).astimezone()
SIMDI = T0 + datetime.timedelta(days=30)


def ol(imza, gun):
    return {"zaman": (T0 + datetime.timedelta(days=gun)).isoformat(), "tur": "kapi_ret", "ana_kategori": "kapi",
            "alt_kategori": "x", "baglam": "", "imza": imza, "sonuc": "acik"}


class SonucTesti(unittest.TestCase):
    def sonuclar(self, gun):
        o = O.sonuc_turet([ol("a", 0), ol("a", gun)], SIMDI, 7)
        return o[0]["sonuc"], o[1]["sonuc"]

    def test_6_gun_tekrarladi(self):
        self.assertEqual(self.sonuclar(6), ("tekrarladi", "duzeldi"))

    def test_7_gun_tekrarladi(self):
        self.assertEqual(self.sonuclar(7), ("tekrarladi", "duzeldi"))

    def test_8_gun_duzeldi(self):
        self.assertEqual(self.sonuclar(8), ("duzeldi", "duzeldi"))

    def test_pencere_dolmadi_acik(self):
        o = O.sonuc_turet([ol("a", 0)], T0 + datetime.timedelta(days=6), 7)
        self.assertEqual(o[0]["sonuc"], "acik")

    def test_farkli_imza_birbirini_etkilemez(self):
        o = O.sonuc_turet([ol("a", 0), ol("b", 1)], SIMDI, 7)
        self.assertEqual([x["sonuc"] for x in o], ["duzeldi", "duzeldi"])


class CikarmaTesti(unittest.TestCase):
    def setUp(self):
        self.kat, self.ayar = O.ayar_yukle()

    def test_dort_tur(self):
        gunluk = [
            {"zaman": T0.isoformat(), "tur": "kural_ihlal", "kural": "secim_ekrani", "dosya": "x.md"},
            {"zaman": T0.isoformat(), "tur": "kapi_ret", "kapi": "uretim_noktasi", "neden": "P3 yer eksik"},
            {"zaman": T0.isoformat(), "tur": "onay-ekran", "bicim": "dict:answers"},
        ]
        hata = [{"kaynak": "davranis", "tur": "hook-red", "imza": "hook-red: K-N", "zaman": T0.isoformat()}]
        duz = [{"zaman": T0.isoformat(), "imza": "duzeltme:d1", "baglam": "hayır"}]
        olaylar = O.olaylari_cikar(gunluk, hata, self.kat, self.ayar, duz)
        self.assertEqual(sorted(O.tur_adetleri(olaylar)), ["karar", "kapi_ret", "kullanici_duzeltme", "yanlis_oneri"])
        self.assertEqual(sum(O.tur_adetleri(olaylar).values()), 5)

    def test_bilinmeyen_kural_diger(self):
        o = O.olaylari_cikar([{"zaman": T0.isoformat(), "tur": "kural_ihlal", "kural": "yeni_kural_x"}], [], self.kat, self.ayar)[0]
        self.assertEqual((o["ana_kategori"], o["alt_kategori"]), ("diger", "siniflanmamis"))

    def test_kapi_ret_alt_kategori_kapi_adi(self):
        o = O.olaylari_cikar([{"zaman": T0.isoformat(), "tur": "kapi_ret", "kapi": "adr", "neden": "n"}], [], self.kat, self.ayar)[0]
        self.assertEqual(o["alt_kategori"], "adr")

    def test_okuyucu_yazmaz(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            sd = os.path.join(d, ".claude", "orkestra")
            os.makedirs(sd)
            yol = os.path.join(sd, "gunluk.jsonl")
            with open(yol, "w", encoding="utf-8") as f:
                f.write('{"zaman": "%s", "tur": "kapi_ret", "kapi": "k", "neden": "n"}\n' % T0.isoformat())
            once = os.path.getsize(yol)
            O.oku(d, SIMDI)
            self.assertEqual(os.path.getsize(yol), once)
            self.assertEqual(sorted(os.listdir(sd)), ["gunluk.jsonl"])


if __name__ == "__main__":
    unittest.main()
