"""A9 kapısı (ADR-0083): denetçinin mekanik düzeltmesi. Birim: duzeltme_kapisi.kapi; uçtan uca: kart denetim."""
import json
import os
import sys
import tempfile
import unittest

import test_cekirdek as TC
from test_cekirdek import CLI

sys.path.insert(0, os.path.dirname(CLI))
import duzeltme_kapisi as DK  # noqa: E402
import kural_aday as KA  # noqa: E402


def gecer(kod=0, cikti=""):
    return lambda komut, proje: (kod, cikti)


class KapiBirim(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.proje = self.tmp.name
        self.yol = os.path.join(self.proje, "r.md")
        self.yaz("Toplam kart: 12\n")
        self.taban = DK.dosya_shalari(self.proje, ["r.md"])

    def tearDown(self):
        self.tmp.cleanup()

    def yaz(self, metin):
        with open(self.yol, "w", encoding="utf-8", newline="") as f:
            f.write(metin)

    def satir(self, **ek):
        d = {"dosya": "r.md", "tur": "sayi", "once": "12", "sonra": "14", "kanit_komutu": "say"}
        d.update(ek)
        return d

    def kapi(self, duz, kos=None):
        return DK.kapi(self.proje, ["r.md"], self.taban, duz, kos or gecer(0, "Toplam kart: 14"))

    def test_degisim_yok_satir_yok_gecer(self):
        self.assertEqual(self.kapi([]), [])
        self.assertEqual(self.kapi(None), [])

    def test_gecerli_sayi_duzeltmesi(self):
        self.yaz("Toplam kart: 14\n")
        self.assertEqual(self.kapi([self.satir()]), [])
        self.assertEqual(DK.neden_kodlari([self.satir()]), ["duzeltildi:sayi-tutarsiz"])

    def test_degisen_dosya_satirsiz_reddedilir(self):
        self.yaz("Toplam kart: 14\n")
        h = self.kapi([])
        self.assertEqual(len(h), 1)
        self.assertIn("duzeltmeler[] satırı yok", h[0])

    def test_degismeyen_dosya_icin_satir_reddedilir(self):
        h = self.kapi([self.satir(sonra="12x")])
        self.assertIn("değişmemiş", h[0])

    def test_sonra_dosyada_yok(self):
        self.yaz("Toplam kart: 13\n")
        self.assertIn("sonra metni dosyada yok", self.kapi([self.satir()])[0])

    def test_sayi_kanit_komutu_sart(self):
        self.yaz("Toplam kart: 14\n")
        self.assertIn("kanit_komutu şart", self.kapi([self.satir(kanit_komutu="")])[0])

    def test_kanit_komutu_basarisiz(self):
        self.yaz("Toplam kart: 14\n")
        self.assertIn("çıkış 1", self.kapi([self.satir()], gecer(1, "Toplam kart: 14"))[0])

    def test_sayi_cikti_sonra_degerini_icermiyor(self):
        self.yaz("Toplam kart: 14\n")
        h = self.kapi([self.satir()], gecer(0, "Toplam kart: 99"))
        self.assertIn("sonra değerini", h[0])

    def test_bicim_komutsuz_gecer(self):
        self.yaz("Toplam kart: 12\r\n")
        d = self.satir(tur="bicim", once="12\n", sonra="12\r\n")
        d.pop("kanit_komutu")
        self.assertEqual(self.kapi([d]), [])
        self.assertEqual(DK.neden_kodlari([d]), ["duzeltildi:bicim"])

    def test_gecersiz_tur_ve_eksik_alan(self):
        self.yaz("Toplam kart: 14\n")
        self.assertIn("geçersiz", self.kapi([self.satir(tur="icerik")])[0])
        self.assertIn("alanı eksik", self.kapi([self.satir(once="")])[0])
        self.assertIn("aynı", self.kapi([self.satir(sonra="12")])[0])

    def test_kart_ciktisi_olmayan_dosya(self):
        self.yaz("Toplam kart: 14\n")
        self.assertIn("kartın çıktısı değil", self.kapi([self.satir(dosya="baska.md")])[0])

    def test_taban_yoksa_yalniz_satirlar_sinanir(self):
        self.yaz("Toplam kart: 14\n")
        self.assertEqual(DK.kapi(self.proje, ["r.md"], None, [], gecer()), [])
        self.assertIn("sonra metni", DK.kapi(self.proje, ["r.md"], None, [self.satir(sonra="77")], gecer())[0])

    def test_liste_degil(self):
        self.assertTrue(self.kapi({"dosya": "r.md"}))


class KartDenetimUcUca(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown
    cli = TC.Cekirdek.cli
    kart = TC.Cekirdek.kart

    def yaz(self, ad, metin):
        yol = os.path.join(self.proje, ad)
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with open(yol, "w", encoding="utf-8", newline="") as f:
            f.write(metin)
        return yol

    def hazir(self):
        self.yaz("docs/a.md", "Toplam kart: 12\n")
        g = self.kart()
        r = self.cli("kart", "durum", g, "is-bitti", "--ozet", "eklendi", "--cikti", "docs/a.md",
                     ajan_id="w1", ajan_tipi="orkestra:isci-t1")
        self.assertEqual(r.returncode, 0, r.stderr)
        return g

    def kart_json(self, g):
        with open(os.path.join(self.sd, "gorevler", f"{g}.json"), encoding="utf-8") as f:
            return json.load(f)

    def duz_dosyasi(self, **ek):
        d = {"dosya": "docs/a.md", "tur": "sayi", "once": "12", "sonra": "14",
             "kanit_komutu": '"%s" -c "print(\'Toplam kart: 14\')"' % sys.executable}
        d.update(ek)
        yol = os.path.join(self.proje, "duz.json")
        with open(yol, "w", encoding="utf-8") as f:
            json.dump([d], f)
        return yol

    def den(self, g, *ek):
        return self.cli("kart", "denetim", g, "--gerekce", "x", *ek, ajan_id="d1", ajan_tipi="orkestra:denetci")

    def test_is_bitti_dosya_shasini_kaydeder(self):
        g = self.hazir()
        sha = self.kart_json(g)["is_turlari"][-1]["cikti_dosya_sha"]
        self.assertEqual(len(sha), 1)
        self.assertTrue(all(v for v in sha.values()))

    def test_degisim_yoksa_eski_davranis(self):
        g = self.hazir()
        r = self.den(g, "--karar", "onay")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("duzeltmeler", self.kart_json(g)["denetimler"][-1])

    def test_bildirimsiz_degisiklik_onayi_reddedilir(self):
        g = self.hazir()
        self.yaz("docs/a.md", "Toplam kart: 14\n")
        r = self.den(g, "--karar", "onay")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("A9", r.stderr)
        self.assertEqual(self.kart_json(g)["denetimler"], [])

    def test_gecerli_duzeltme_onaylanir_ve_kayda_duser(self):
        g = self.hazir()
        self.yaz("docs/a.md", "Toplam kart: 14\n")
        r = self.den(g, "--karar", "onay", "--duzeltmeler-dosya", self.duz_dosyasi())
        self.assertEqual(r.returncode, 0, r.stderr)
        kayit = self.kart_json(g)["denetimler"][-1]
        self.assertEqual(kayit["karar"], "onay")
        self.assertEqual(kayit["duzeltildi"], ["duzeltildi:sayi-tutarsiz"])
        self.assertEqual(kayit["duzeltmeler"][0]["sonra"], "14")

    def test_basarisiz_kanit_komutu_onayi_reddeder(self):
        g = self.hazir()
        self.yaz("docs/a.md", "Toplam kart: 14\n")
        r = self.den(g, "--karar", "onay", "--duzeltmeler-dosya",
                     self.duz_dosyasi(kanit_komutu='"%s" -c "raise SystemExit(3)"' % sys.executable))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("çıkış 3", r.stderr)
        self.assertEqual(self.kart_json(g)["denetimler"], [])

    def test_retle_birlikte_duzeltme_verilemez(self):
        g = self.hazir()
        self.yaz("docs/a.md", "Toplam kart: 14\n")
        r = self.den(g, "--karar", "ret", "--neden", "kapsam-eksik", "--duzeltmeler-dosya", self.duz_dosyasi())
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("yalnız onay", r.stderr)


class RetDefteri(unittest.TestCase):
    def test_duzeltildi_ret_nedeni_sayimina_katilir(self):
        k = {"id": "G-1", "sinif": "belge", "denetimler": [
            {"karar": "onay", "duzeltildi": ["duzeltildi:sayi-tutarsiz"]},
            {"karar": "ret", "neden": "sayi-tutarsiz"}]}
        kartlar = [k, dict(k, id="G-2"), dict(k, id="G-3")]
        a = KA.kural_adaylari(kartlar, esik=3)
        sayi = [x for x in a if x["neden"] == "sayi-tutarsiz"]
        self.assertEqual(sayi[0]["sayi"], 6)  # 3 ret + 3 düzeltme

    def test_duzeltmesiz_onay_sayilmaz(self):
        k = {"id": "G-1", "sinif": "belge", "denetimler": [{"karar": "onay"}]}
        self.assertEqual(KA._neden_kayitlari(k), [])


if __name__ == "__main__":
    unittest.main()
