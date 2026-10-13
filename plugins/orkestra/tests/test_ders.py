"""analitik._ders testleri: ret nedenleri (sınıf x basamak) ve verim (sınıf x başlangıç basamağı)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import analitik as A  # noqa: E402
import ret_nedeni as RN  # noqa: E402


def kart(i, sinif, bas="T2", durum="planlandi", tur=0, denetimler=()):
    return {"id": i, "sinif": sinif, "baslangic_basamak": bas, "basamak": bas, "durum": durum,
            "gecmis": [{"olay": "is-bitti"}] * tur, "denetimler": list(denetimler)}


def ret(neden=None, basamak="T2"):
    d = {"karar": "ret", "basamak": basamak}
    if neden:
        d["neden"] = neden
    return d


class DersTest(unittest.TestCase):
    def test_kodlu_ret_ve_kok(self):
        k = [kart("A", "kod", denetimler=[ret("bicim"), ret("kriter-belirsiz"), ret("yetenek-yetersiz")])]
        d = A._ders(k, [])
        self.assertEqual(len(d["nedenler"]), 1)
        n = d["nedenler"][0]
        self.assertEqual((n["sinif"], n["basamak"], n["ret"]), ("kod", "T2", 3))
        self.assertEqual(n["nedenler"], {"bicim": 1, "kriter-belirsiz": 1, "yetenek-yetersiz": 1})
        self.assertEqual(n["kok"], {"dikkat": 1, "kart": 1, "basamak": 1})

    def test_kodsuz_ret(self):
        k = [kart("A", "kod", denetimler=[ret(), ret("uydurma")])]
        n = A._ders(k, [])["nedenler"][0]
        self.assertEqual(n["nedenler"], {"siniflanmamis": 2})
        self.assertEqual(n["kok"], {"siniflanmamis": 2})

    def test_kok_esleme(self):
        self.assertEqual(len(RN.NEDENLER), 7)
        self.assertEqual(RN.kok("kriter-belirsiz"), "kart")
        self.assertEqual(RN.kok("yetenek-yetersiz"), "basamak")
        for kod in ("kapsam-eksik", "bicim", "sayi-tutarsiz", "kanit-yok", "talimat-ihlali"):
            self.assertEqual(RN.kok(kod), "dikkat")
        self.assertEqual(RN.kok(None), "siniflanmamis")
        self.assertEqual(RN.kok("x"), "siniflanmamis")

    def test_sinifsiz(self):
        k = [kart("A", None, denetimler=[ret()]), kart("B", "-")]
        d = A._ders(k, [])
        self.assertEqual({v["sinif"] for v in d["verim"]}, {"sınıfsız"})
        self.assertEqual(d["nedenler"][0]["sinif"], "sınıfsız")
        self.assertEqual(d["verim"][0]["kart"], 2)

    def test_onaylanan_sifir_null(self):
        d = A._ders([kart("A", "kod")], [{"gorev": "A", "maliyet_usd": 1.5}])
        v = d["verim"][0]
        self.assertEqual(v["onaylanan"], 0)
        self.assertIsNone(v["onayli_is_basi_usd"])
        self.assertEqual(v["toplam_usd"], 1.5)
        self.assertIsNone(d["toplam"]["onayli_is_basi_usd"])

    def test_ort_tur_ve_maliyet(self):
        k = [kart("A", "kod", durum="onaylandi", tur=3), kart("B", "kod", durum="teslim", tur=1),
             kart("C", "kod", tur=2)]
        kay = [{"gorev": "A", "maliyet_usd": 2.0}, {"gorev": "B", "maliyet_usd": 1.0},
               {"gorev": "C", "maliyet_usd": 3.0}, {"gorev": "-", "maliyet_usd": 9.0}]
        d = A._ders(k, kay)
        v = d["verim"][0]
        self.assertEqual((v["kart"], v["onaylanan"], v["ort_tur"]), (3, 2, 2.0))
        self.assertEqual(v["toplam_usd"], 6.0)
        self.assertEqual(v["onayli_is_basi_usd"], 3.0)
        self.assertEqual(d["toplam"]["ort_tur"], 2.0)


if __name__ == "__main__":
    unittest.main()
