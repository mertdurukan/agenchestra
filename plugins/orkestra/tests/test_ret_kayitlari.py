"""analitik.ret_kayitlari: ret sayımının tek kuralı (iptal hariç, geçersiz kod sınıflanmamış, basamak yedeği)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import analitik as A  # noqa: E402


def kart(i, sinif="kod", durum="planlandi", bas="T2", denetimler=()):
    return {"id": i, "sinif": sinif, "baslangic_basamak": bas, "basamak": bas, "durum": durum,
            "gecmis": [], "denetimler": list(denetimler)}


def ret(neden=None, basamak=None):
    d = {"karar": "ret"}
    if neden:
        d["neden"] = neden
    if basamak:
        d["basamak"] = basamak
    return d


class RetKayitlari(unittest.TestCase):
    def test_iptal_kart_haric(self):
        ks = [kart("A", durum="iptal", denetimler=[ret("bicim")]), kart("B", denetimler=[ret("bicim")])]
        self.assertEqual([r[0]["id"] for r in A.ret_kayitlari(ks)], ["B"])

    def test_gecersiz_kod_siniflanmamis_ve_onay_atlanir(self):
        ks = [kart("A", denetimler=[ret("uydurma"), ret(), {"karar": "onay"}])]
        sonuc = list(A.ret_kayitlari(ks))
        self.assertEqual([(r[4], r[5]) for r in sonuc], [("siniflanmamis", "siniflanmamis")] * 2)

    def test_basamak_yedegi_ve_sinifsiz(self):
        ks = [kart("A", sinif=None, bas="T3", denetimler=[ret("bicim"), ret("bicim", basamak="T4")])]
        sonuc = list(A.ret_kayitlari(ks))
        self.assertEqual([(r[2], r[3]) for r in sonuc], [("sınıfsız", "T3"), ("sınıfsız", "T4")])

    def test_toplam_ders_ile_esit(self):
        ks = [kart("A", denetimler=[ret("bicim"), ret("kanit-yok")]), kart("B", durum="iptal", denetimler=[ret("bicim")]),
              kart("C", sinif="rapor", denetimler=[ret()])]
        toplam = sum(n["ret"] for n in A._ders(ks, [])["nedenler"])
        self.assertEqual(toplam, len(list(A.ret_kayitlari(ks))))
        self.assertEqual(toplam, 3)


if __name__ == "__main__":
    unittest.main()
