"""is-anlati taslak denetimi (A01-A09).

`py -3.13 -m pytest plugins/orkestra/tests/test_is_anlati_denetle.py`
Sahte veri kullanır; komut satırı testleri main(argv) işlevini süreç içinde çağırır.
"""
import contextlib
import importlib.util
import io
import os
import tempfile
import unittest

AD = os.path.dirname(os.path.abspath(__file__))
BETIK = os.path.join(AD, "..", "scripts", "is_anlati_denetle.py")
spec = importlib.util.spec_from_file_location("is_anlati_denetle", BETIK)
ad = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ad)

P1 = ("**Ne yaptım?** Orkestra panelindeki arka plan görevleri şeridinde görevin ne kadar süredir "
      "çalıştığının görünmemesi sorununu ele aldım. Süreyi her görevin yanında gösteren ve açık sayfada "
      "kendiliğinden ilerleyen bir yardımcı ekledim; şeritte görülen ham tarih metninin de nedenini bulup "
      "düzelttim. Değişiklik iki sayfada çalışıyor, gerçek bir arka plan görevinde henüz gözlenmedi.")
P2 = ("**Nasıl yaptım?** Önce şeridi besleyen veri yolunu ve hatalı tarih çağrısını agent ile okuyarak "
      "sorunun biçimleyici işlevinin eksik olmasından geldiğini gösterdim. Sonra dört maddelik küçük bir "
      "plan hazırladım, süreyi tek ortak yardımcıda topladım ve canlı panelde sahte bir görev kaydıyla "
      "süre ilerlemesini ölçtüm. Gerçek görevle denemeyi bilerek sınır olarak bıraktım.")
IYI = P1 + "\n\n" + P2


def kodlar(metin, baglam=None):
    return {k for k, _ in ad.denetle(metin, baglam)}


class DenetleTest(unittest.TestCase):
    def test_iyi_taslak_temiz(self):
        self.assertEqual(ad.denetle(IYI), [])
        self.assertEqual(ad.denetle(IYI, {"guclu_fiil_izni": True}), [])

    def test_a01_paragraf_sayisi(self):
        uc = IYI + "\n\nBu üçüncü bir paragraf olarak geldi."
        self.assertEqual(kodlar(uc), {"A01"})
        self.assertEqual(kodlar(P1), {"A01"})

    def test_a02_etiket(self):
        self.assertEqual(kodlar(P1 + "\n\n" + P2.replace("**Nasıl yaptım?** ", "")), {"A02"})
        self.assertEqual(kodlar(P1 + "\n\n" + P2.replace("**Nasıl yaptım?**", "# Başlık\n**Nasıl yaptım?**")), {"A02"})

    def test_a03_kelime_araligi(self):
        kisa = "**Ne yaptım?** Bir şeyi düzelttim."
        self.assertEqual(kodlar(kisa + "\n\n" + P2), {"A03"})
        uzun = P1 + " " + " ".join(["ayrıntı"] * 60) + " ekledim."
        self.assertEqual(kodlar(uzun + "\n\n" + P2), {"A03"})

    def test_a04_madde_isareti(self):
        for isaret in ("- ", "* ", "1. "):
            with self.subTest(isaret=isaret):
                self.assertEqual(kodlar(P1 + "\n" + isaret + "bir madde\n\n" + P2), {"A04"})

    def test_a04_diger_alt_durumlar(self):
        durumlar = {
            "sha": "a1b2c3d4e5f",
            "yol": "plugins/orkestra/scripts/panel.py",
            "surucu_yolu": "C:\\Mert\\panel",
            "ters_tirnak": "`panel`",
            "tablo": "a | b",
            "url": "https://example.com",
        }
        for ad_, ek in durumlar.items():
            with self.subTest(durum=ad_):
                self.assertEqual(kodlar(P1 + " " + ek + "\n\n" + P2), {"A04"})

    def test_a05_sir(self):
        self.assertEqual(kodlar(P1 + " parola: Gizli123x\n\n" + P2), {"A05"})
        self.assertEqual(kodlar(P1 + " postgres://kullanici:Gizli123@sunucu\n\n" + P2), {"A05"})
        self.assertEqual(kodlar(P1 + " Zx9Qw8Er7Ty6Ui5Op4As3Df2Gh1Jk0LzXc\n\n" + P2), {"A05"})

    def test_a06_sahis(self):
        self.assertEqual(kodlar(P1 + "\n\n" + P2.replace("gösterdim", "gösterildi gibi").replace(
            "hazırladım", "hazırlanır").replace("topladım", "toplanır").replace(
            "ölçtüm", "ölçülür").replace("bıraktım", "bırakıldı")), {"A06"})
        self.assertEqual(kodlar(P1 + " Bunu birlikte yaptık.\n\n" + P2), {"A06"})

    def test_a06_yanlis_pozitif_yok(self):
        # otomatik, pratik, kritik, istatistik, mantık, sistematik: -dık/-tık/-dik/-tik ile biten sözcükler
        ek = " Otomatik ve pratik bir yol seçtim; kritik adımda istatistik ve sistematik mantık kullandım."
        self.assertEqual(kodlar(P1 + ek + "\n\n" + P2), set())

    def test_a07_abarti(self):
        self.assertEqual(kodlar(P1 + " Kusursuz oldu.\n\n" + P2), {"A07"})
        self.assertEqual(kodlar(P1 + " Sorunu çözdüm.\n\n" + P2), {"A07"})

    def test_a07_izinli_fiil(self):
        cozdum = P1 + " Sorunu çözdüm.\n\n" + P2
        self.assertEqual(kodlar(cozdum, None), {"A07"})
        self.assertEqual(kodlar(cozdum, {"guclu_fiil_izni": False}), {"A07"})
        self.assertEqual(kodlar(cozdum, {"guclu_fiil_izni": True}), set())
        self.assertEqual(kodlar(P1 + " Kusursuz oldu.\n\n" + P2, {"guclu_fiil_izni": True}), {"A07"})

    def test_a08_ic_surec(self):
        for ek in ("P1 maddesi", "K-003", "ADR-0037", "hook çalıştı", "kapı geçti", "orkestra kuralı gereği", "G2"):
            with self.subTest(ek=ek):
                self.assertEqual(kodlar(P1 + " " + ek + "\n\n" + P2), {"A08"})

    def test_a09_tekrar(self):
        yinelenen = P2 + " Panelindeki arka plan görevleri şeridinde görevin ne kadar süredir çalıştığı."
        self.assertEqual(kodlar(P1 + "\n\n" + yinelenen), {"A09"})

    def test_cli_temiz(self):
        with tempfile.TemporaryDirectory() as d:
            yol = os.path.join(d, "t.md")
            with open(yol, "w", encoding="utf-8") as f:
                f.write(IYI)
            cikti = io.StringIO()
            with contextlib.redirect_stdout(cikti):
                kod = ad.main([yol])
        self.assertEqual(kod, 0)
        self.assertEqual(cikti.getvalue().strip(), "temiz")

    def test_cli_ihlal(self):
        with tempfile.TemporaryDirectory() as d:
            yol = os.path.join(d, "t.md")
            with open(yol, "w", encoding="utf-8") as f:
                f.write(P1 + " Kusursuz oldu.\n\n" + P2)
            cikti = io.StringIO()
            with contextlib.redirect_stdout(cikti):
                kod = ad.main([yol])
        self.assertEqual(kod, 1)
        self.assertTrue(cikti.getvalue().startswith("A07: "))


if __name__ == "__main__":
    unittest.main()
