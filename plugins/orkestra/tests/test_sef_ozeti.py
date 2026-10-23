"""I-209: çalışma özeti Şef Özeti biçimi (şablon, kapanış kapısı, iş anlatısı); eski biçim geriye uyumlu kalır."""
import importlib
import os
import re
import sys
import tempfile
import unittest

AD = os.path.dirname(os.path.abspath(__file__))
KOK = os.path.join(AD, "..")
sys.path.insert(0, os.path.join(KOK, "scripts"))

import is_anlati as IA  # noqa: E402

SABLON = os.path.join(KOK, "sablonlar", "calisma_ozeti.md")
YENI = ("# T: çalışma özeti\n\n## Özet\n\n***Şef Özeti***\n\n**Amaç neydi?**\n\nÖzet biçimini düzeltmek.\n\n"
        "**Ne yapıldı?**\n\n- Şablonu yeniledim.\n\n**Amaca tamamen ulaşıldı mı?**\n\nEvet.\n\n"
        "**Tamamen yapılanlar:**\n\n- Şablon.\n\n**Açık kalanlar:**\n\n- Yok\n\n**Ölçüm saati:**\n\nx\n")
ESKI = "# T: çalışma özeti\n\n**Amaç:**\n\nEski amaç.\n\n**Ana bulgu:**\n\nEski bulgu.\n\n**Açık işler:**\n\n- Eski açık iş\n"


class Sablon(unittest.TestCase):
    def test_etiket_sirasi_ve_eski_etiketler_yok(self):
        with open(SABLON, encoding="utf-8") as f:
            t = f.read()
        sira = ["***Şef Özeti***", "**Amaç neydi?**", "**Ne yapıldı?**", "**Amaca tamamen ulaşıldı mı?**",
                "**Tamamen yapılanlar:**", "**Açık kalanlar:**"]
        yerler = [t.index("\n" + s + "\n") for s in sira]
        self.assertEqual(yerler, sorted(yerler))
        for eski in ("**Amaç:**", "**Ana bulgu:**", "**Açık işler:**"):
            self.assertNotIn(eski, t)


class Kapi(unittest.TestCase):
    def setUp(self):
        self.isler = importlib.import_module("komutlar.isler")
        self.k = tempfile.mkdtemp()
        self.yol = os.path.join(self.k, "calisma_ozeti_20261023.md")

    def yaz(self, metin):
        with open(self.yol, "w", encoding="utf-8", newline="\n") as f:
            f.write(metin)

    def test_yeni_dolu_gecer(self):
        self.yaz(YENI)
        self.assertIsNone(self.isler._ozet_eksigi(self.k))

    def test_eski_dolu_gecer(self):
        self.yaz(ESKI)
        self.assertIsNone(self.isler._ozet_eksigi(self.k))

    def test_bos_sablon_reddedilir(self):
        with open(SABLON, encoding="utf-8") as f:
            self.yaz(f.read().replace("{tarih}", "x").replace("{saat}", "y").replace("{baslik}", "T"))
        self.assertIn("Ne yapıldı?", self.isler._ozet_eksigi(self.k) or "")

    def test_ne_yapildi_bos_amaca_dolu_reddedilir(self):
        self.yaz(YENI.replace("- Şablonu yeniledim.\n\n", ""))
        self.assertIn("Ne yapıldı?", self.isler._ozet_eksigi(self.k) or "")

    def test_yalniz_yorum_bos_sayilir(self):
        self.yaz(YENI.replace("- Şablonu yeniledim.", "<!-- doldur: en çok 3 madde -->"))
        self.assertIn("Ne yapıldı?", self.isler._ozet_eksigi(self.k) or "")


class Anlati(unittest.TestCase):
    def paket(self, ozet):
        k = tempfile.mkdtemp()
        with open(os.path.join(k, "calisma_ozeti_20261023.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(ozet)
        return IA.paket({"id": "I-999", "baslik": "x", "durum": "acik", "klasor": k})

    def test_yeni_bicim_alanlari_okunur(self):
        p = self.paket(YENI.replace("**Açık kalanlar:**\n\n- Yok", "**Açık kalanlar:**\n\n- Karar bekliyor"))
        self.assertIn("Özet biçimini düzeltmek.", p["ne_icin"])
        self.assertEqual(p["sonuc"], ["Şablonu yeniledim."])
        self.assertIn("Açık iş: Karar bekliyor", p["sinirlar"])

    def test_yeni_bicimde_sonuc_baslik_ve_yorum_icermez(self):
        p = self.paket(YENI.replace("- Şablonu yeniledim.", "<!-- doldur -->\n- Şablonu yeniledim."))
        self.assertEqual(p["sonuc"], ["Şablonu yeniledim."])
        self.assertFalse(any("Şef" in s or "doldur" in s for s in p["sonuc"]))

    def test_yeni_bicimde_yok_acik_is_sayilmaz(self):
        self.assertEqual(self.paket(YENI)["sinirlar"], [])

    def test_eski_bicim_degismez(self):
        p = self.paket(ESKI)
        self.assertIn("Eski amaç.", p["ne_icin"])
        self.assertIn("Eski bulgu.", p["sonuc"])
        self.assertIn("Açık iş: Eski açık iş", p["sinirlar"])


class Etiket(unittest.TestCase):
    def test_soru_etiketi_alan_sonudur(self):
        m = "**Ne yapıldı?**\n\n- a\n\n**Amaca tamamen ulaşıldı mı?**\n\nEvet.\n"
        self.assertEqual(IA._etiket(m, "Ne yapıldı?"), ["a"])
        self.assertTrue(re.match(IA._ETIKET_RE, "**Amaca tamamen ulaşıldı mı?**"))


if __name__ == "__main__":
    unittest.main()
