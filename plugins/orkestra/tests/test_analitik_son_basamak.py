"""analitik: son basamak kart gecmis is-bitti kayıtlarından türetilir (K09), basamak alanından değil."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import analitik as A  # noqa: E402


def bitti(ajan):
    return {"olay": "is-bitti", "ajan": ajan}


def kart(id_="G-1", basamak="T2", baslangic="T2", gecmis=None, durum="teslim"):
    return {"id": id_, "basamak": basamak, "baslangic_basamak": baslangic, "durum": durum,
            "gecmis": gecmis or [], "denetimler": []}


def satirlar(sonuc):
    return {s["basamak"]: s for s in sonuc["satirlar"]}


class SonBasamak(unittest.TestCase):
    def test_en_yuksek_isci_secilir(self):
        k = kart(gecmis=[bitti("isci-t2"), bitti("isci-t3"), bitti("isci-t2")])
        self.assertEqual(A.son_basamak(k), "T3")

    def test_buyuk_harf_ve_t4(self):
        k = kart(gecmis=[bitti("isci-t1"), bitti("isci-t4"), bitti("isci-t3")])
        self.assertEqual(A.son_basamak(k), "T4")

    def test_isci_olmayan_ajanlar_yok_sayilir(self):
        k = kart(basamak="T1", baslangic="T1",
                 gecmis=[bitti("isci-t1"), bitti("test-yazari"), bitti("denetci"), bitti("orkestra:denetci")])
        self.assertEqual(A.son_basamak(k), "T1")

    def test_is_bitti_olmayan_olaylar_yok_sayilir(self):
        k = kart(basamak="T2", baslangic="T2",
                 gecmis=[{"olay": "yukseltme", "ajan": "isci-t4"}, {"olay": "durum", "ajan": "isci-t3"}])
        self.assertEqual(A.son_basamak(k), "T2")

    def test_is_bitti_yoksa_basamak_alanina_duser(self):
        self.assertEqual(A.son_basamak(kart(basamak="T3", baslangic="T2")), "T3")

    def test_is_bitti_ve_basamak_yoksa_baslangica_duser(self):
        k = kart(basamak=None, baslangic="T1")
        self.assertEqual(A.son_basamak(k), "T1")

    def test_gecmis_alani_yoksa(self):
        k = {"id": "G-2", "basamak": "T2", "baslangic_basamak": "T2"}
        self.assertEqual(A.son_basamak(k), "T2")

    def test_ajan_alani_bos_veya_none(self):
        k = kart(gecmis=[{"olay": "is-bitti"}, {"olay": "is-bitti", "ajan": None}, bitti("isci-t3")])
        self.assertEqual(A.son_basamak(k), "T3")

    def test_isci_olmayan_tek_is_bitti_dusme(self):
        k = kart(basamak="T3", baslangic="T2", gecmis=[bitti("denetci")])
        self.assertEqual(A.son_basamak(k), "T3")


class BasamakYukseltilen(unittest.TestCase):
    def test_basamak_alani_t2_ama_isci_t3_yukseltilen_sayilir(self):
        k = kart(basamak="T2", baslangic="T2", gecmis=[bitti("isci-t2"), bitti("isci-t3")])
        s = satirlar(A._basamak([k], []))
        self.assertEqual(s["T2"]["kart"], 1)
        self.assertEqual(s["T2"]["yukseltilen"], 1)
        self.assertEqual(s["T2"]["yukseltme_orani"], 1.0)

    def test_kucuk_pay_yukseltilen_karti_saymaz(self):
        k = kart(basamak="T2", baslangic="T2", gecmis=[bitti("isci-t2"), bitti("isci-t3")])
        sonuc = A._basamak([k], [])
        self.assertEqual(sonuc["teslim_kart"], 1)
        self.assertEqual(sonuc["kucuk_pay_kart"], 0.0)

    def test_yukseltilmemis_kart_kucuk_payda(self):
        k = kart(gecmis=[bitti("isci-t2")])
        sonuc = A._basamak([k], [])
        self.assertEqual(satirlar(sonuc)["T2"]["yukseltilen"], 0)
        self.assertEqual(sonuc["kucuk_pay_kart"], 1.0)

    def test_karisik_paylar(self):
        a = kart("G-1", gecmis=[bitti("isci-t2")])
        b = kart("G-2", gecmis=[bitti("isci-t2"), bitti("isci-t4")])
        sonuc = A._basamak([a, b], [])
        self.assertEqual(sonuc["teslim_kart"], 2)
        self.assertEqual(sonuc["kucuk_pay_kart"], 0.5)
        self.assertEqual(satirlar(sonuc)["T2"]["yukseltilen"], 1)

    def test_yukseltme_olayi_hala_sayilir(self):
        k = kart(gecmis=[bitti("isci-t2"), {"olay": "yukseltme"}])
        self.assertEqual(satirlar(A._basamak([k], []))["T2"]["yukseltilen"], 1)

    def test_kart_baslangic_basamagina_yazilir(self):
        k = kart(basamak="T2", baslangic="T2", gecmis=[bitti("isci-t3")])
        s = satirlar(A._basamak([k], []))
        self.assertNotIn("T3", s)

    def test_is_bitti_yoksa_eski_davranis(self):
        k = kart(basamak="T3", baslangic="T2")
        sonuc = A._basamak([k], [])
        self.assertEqual(satirlar(sonuc)["T2"]["yukseltilen"], 1)
        self.assertEqual(sonuc["kucuk_pay_kart"], 0.0)

    def test_denetim_basamagi_degismez(self):
        k = kart(basamak="T2", baslangic="T2", gecmis=[bitti("isci-t3")])
        k["denetimler"] = [{"sira": 1, "karar": "ret", "basamak": "T2"}]
        s = satirlar(A._basamak([k], []))
        self.assertEqual(s["T2"]["denetim"], 1)
        self.assertEqual(s["T2"]["ret"], 1)


if __name__ == "__main__":
    unittest.main()
