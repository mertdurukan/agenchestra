"""I-209: çalışma özeti Şef Özeti biçimi (şablon, kapanış kapısı, iş anlatısı); eski biçim geriye uyumlu kalır.
I-227 (ADR-0085): iki katman: kısa `## Özet` ve kapsamlı `## Harita`; `sef_ozeti` gölge kapısı."""
import importlib
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

AD = os.path.dirname(os.path.abspath(__file__))
KOK = os.path.join(AD, "..")
sys.path.insert(0, os.path.join(KOK, "scripts"))

import is_anlati as IA  # noqa: E402
import is_kaydi as IK  # noqa: E402
import test_cekirdek as TC  # noqa: E402

SABLON = os.path.join(KOK, "sablonlar", "calisma_ozeti.md")
YENI = ("# T: çalışma özeti\n\n## Özet\n\n***Şef Özeti***\n\n**Amaç neydi?**\n\nÖzet biçimini düzeltmek.\n\n"
        "**Ne yapıldı?**\n\n- Şablonu yeniledim.\n\n**Amaca tamamen ulaşıldı mı?**\n\nEvet.\n\n"
        "**Tamamen yapılanlar:**\n\n- Şablon.\n\n**Açık kalanlar:**\n\n- Yok\n\n**Ölçüm saati:**\n\nx\n")
HARITA = ("\n## Harita\n\n**Ölçüm saati:**\n\n26.10 10:00\n\n**Denenenler:**\n\n"
          "| Katman ya da bileşen | Yöntem | Sonuç | Kanıt |\n| --- | --- | --- | --- |\n"
          "| Şablon | İki bölüm | işe yaradı | test_sef_ozeti.py |\n\n**Sayılar:**\n\n- 5 alan\n\n"
          "**Doğrulanmayanlar:**\n\n- Yok\n\n**Kararlar:**\n\n- Kapı gölgede açıldı (ADR-0085)\n")
IKI = YENI.replace("**Ölçüm saati:**\n\nx\n", "") + HARITA
ESKI = "# T: çalışma özeti\n\n**Amaç:**\n\nEski amaç.\n\n**Ana bulgu:**\n\nEski bulgu.\n\n**Açık işler:**\n\n- Eski açık iş\n"


class Sablon(unittest.TestCase):
    def test_etiket_sirasi_ve_eski_etiketler_yok(self):
        with open(SABLON, encoding="utf-8") as f:
            t = f.read()
        sira = ["***Şef Özeti***", "**Durum:**", "**Amaç neydi?**", "**Ne yapıldı?**", "**Nasıl karar verildi?**",
                "**Ana sayı:**", "**Senden beklenen:**", "**Açık kalanlar:**"]
        yerler = [t.index("\n" + s + "\n") for s in sira]
        self.assertEqual(yerler, sorted(yerler))
        harita = ["## Harita", "**Ölçüm saati:**", "**Denenenler:**", "**Sayılar:**", "**Doğrulanmayanlar:**",
                  "**Kararlar:**", "**Teslim:**", "**Açık işlerin ayrıntısı:**", "**İlgili dosyalar:**",
                  "## Plana göre gerçekleşen"]
        yerler = [t.index("\n" + s + "\n") for s in harita]
        self.assertEqual(yerler, sorted(yerler))
        self.assertGreater(yerler[0], t.index("\n**Açık kalanlar:**\n"))
        for eski in ("**Amaç:**", "**Ana bulgu:**", "**Açık işler:**", "**Amaca tamamen ulaşıldı mı?**",
                     "**Tamamen yapılanlar:**"):
            self.assertNotIn(eski, t)

    def test_teslim_bloku_dort_satir(self):
        """ADR-0091 (S1): Jira yorumunun beslendiği Teslim bloğu şablonda dört alanla durur."""
        with open(SABLON, encoding="utf-8") as f:
            t = f.read()
        self.assertGreaterEqual(t.count("Teslim"), 1)
        for ad in ("Değişiklik", "Test", "Deploy", "Geri alma"):
            self.assertIn(f"- **{ad}:**", t)


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


YENI_B1 = ("# T: çalışma özeti\n\n## Özet\n\n***Şef Özeti***\n\n"
           "**Durum:** Kısmen. Kod, test ve ölçüm tamam; entegrasyon testi VPN kapalı olduğu için koşulmadı ve sütun anlamı "
           "platform sahibinden teyit bekliyor.\n\n"
           "**Amaç neydi?** PE-640: `query_forecast` aracının nihai (after-process) tahmin değerlerini okuması ve \"bu tahmin "
           "nasıl üretildi\" sorularının kodla reddedilmesi.\n\n"
           "**Ne yapıldı?**\n\n"
           "- [Doğrulandı] Araç `fact_replenishment_report.forecast_quantity_1/2` ve `replenishment_quantity` alanlarını okur; "
           "model alanları kaldırıldı. 3912 test geçti.\n"
           "- [Doğrulandı] Metodoloji sorusu modele gitmeden sabit yanıtla reddedilir; sızıntı yapan yanıt tablo yanıtına düşer.\n"
           "- [Planlandı] Jira yorumu taslağı yazıldı; Jira'ya yazılmadı.\n\n"
           "**Nasıl karar verildi?** Nihai değerin yeri 33 şemalık katalog ve prosedür gövdeleriyle bulundu, dört şemada eşleşti. "
           "Ret, giriş sınıflandırması ve çıkış doğrulamasıyla kodda zorlandı; üç kör turda yakalama yaklaşık %60 kaldı, bu sınır "
           "açıkça yazıldı.\n\n"
           "**Ana sayı:** `pytest tests/unit tests/contract` → 3912 passed, 1 skipped (27.10.2026).\n\n"
           "**Senden beklenen:** Entegrasyon testi için VPN bağlantısı; Jira yorumu, push ve PR kararı.\n\n"
           "**Açık kalanlar:**\n\n- Entegrasyon testi: kopya sunucuya bağlanılamadı (VPN).\n"
           "- Sütun anlamı teyidi: platform sahibi; ADR-0011 bu teyide kadar Önerildi.\n")
TESLIM_B1 = ("\n**Teslim:**\n\n- **Değişiklik:** PR açılmadı; push ve PR kararı kullanıcıda.\n"
             "- **Test:** `pytest tests/unit tests/contract` 3912 passed, 1 skipped; entegrasyon testi çalışmadı.\n"
             "- **Deploy:** çıkmadı; PR ve sütun anlamı teyidi bekliyor.\n- **Geri alma:** canlıya değişiklik çıkmadı.\n")


class YeniBicim(unittest.TestCase):
    """ADR-0091 (S1): PE-640 B1 biçimli, yedi alanlı Özet + Teslim bloğu mevcut kapıdan boş uyarı listesiyle geçer."""

    def test_b1_ozet_kapidan_temiz_gecer(self):
        metin = YENI_B1 + HARITA.rstrip("\n") + "\n" + TESLIM_B1
        self.assertEqual(IK.sef_ozeti_eksigi(metin, 1200), [])

    def test_b1_ozet_1200_icinde(self):
        n = sum(len(IK._alan_govdesi(YENI_B1, ad) or "") for ad in
                ("Durum", "Amaç neydi?", "Ne yapıldı?", "Nasıl karar verildi?", "Ana sayı", "Senden beklenen", "Açık kalanlar"))
        self.assertLessEqual(n, 1200, n)

    def test_b1_kapanis_kapisindan_gecer(self):
        isler = importlib.import_module("komutlar.isler")
        k = tempfile.mkdtemp()
        with open(os.path.join(k, "calisma_ozeti_20261027.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(YENI_B1 + HARITA + TESLIM_B1)
        self.assertIsNone(isler._ozet_eksigi(k))


class SefEksigi(unittest.TestCase):
    """is_kaydi.sef_ozeti_eksigi: saf işlev (ADR-0085)."""

    def test_tam_iki_katman_gecer(self):
        self.assertEqual(IK.sef_ozeti_eksigi(IKI), [])

    def test_eski_bicim_etkilenmez_haritasiz_yeni_bicim_uyarilir(self):
        self.assertEqual(IK.sef_ozeti_eksigi(ESKI), [])
        e = IK.sef_ozeti_eksigi(YENI)
        self.assertTrue(any("`## Harita` bölümü yok" in x for x in e), e)

    def test_bos_sablon_uc_zorunlu_alan_icin_uyarir(self):
        with open(SABLON, encoding="utf-8") as f:
            e = IK.sef_ozeti_eksigi(f.read())
        for ad in ("Denenenler", "Doğrulanmayanlar", "Kararlar"):
            self.assertTrue(any(ad in x and "boş" in x for x in e), e)

    def test_zorunlu_alan_eksik_ya_da_bos(self):
        yok = IKI.replace("**Kararlar:**\n\n- Kapı gölgede açıldı (ADR-0085)\n", "")
        self.assertTrue(any("Kararlar" in x and "yok" in x for x in IK.sef_ozeti_eksigi(yok)))
        bos = IKI.replace("- Kapı gölgede açıldı (ADR-0085)", "<!-- doldur -->")
        self.assertTrue(any("Kararlar" in x and "boş" in x for x in IK.sef_ozeti_eksigi(bos)))
        bos_tablo = IKI.replace("| Şablon | İki bölüm | işe yaradı | test_sef_ozeti.py |\n", "| | | | |\n")
        self.assertTrue(any("Denenenler" in x and "boş" in x for x in IK.sef_ozeti_eksigi(bos_tablo)))

    def test_katman1_uzunluk_esigi(self):
        uzun = IKI.replace("Özet biçimini düzeltmek.", "x" * 1300)  # varsayılan eşik 1200 (ADR-0091)
        e = IK.sef_ozeti_eksigi(uzun)
        self.assertTrue(any("katman 1" in x for x in e), e)
        self.assertEqual(IK.sef_ozeti_eksigi(uzun, katman1_azami=2000), [])

    def test_harita_icerigi_katman1_uzunlugunu_sismirmez(self):
        self.assertEqual(IK.sef_ozeti_eksigi(IKI.replace("- 5 alan", "- " + "y" * 3000)), [])

    def test_yontem_ayrintisi_ozete_yazilirsa_yakalanir(self):
        """PE-635 olayı: yöntem ve katman ayrıntısı Şef Özeti'ne yazılınca özet kısa kalmaz."""
        sisik = IKI.replace("- Şablonu yeniledim.", "- " + "Yöntem ve katman ayrıntısı. " * 40)
        self.assertTrue(any("katman 1" in x for x in IK.sef_ozeti_eksigi(sisik)))


IHLAL_SEF = lambda kapi, klasor=None: "ihlal" if kapi == "sef_ozeti" else "golge"  # noqa: E731


class SefKapi(unittest.TestCase):
    """isler._ozet_eksigi içindeki sef_ozeti kapısı: gölge uyarır ve kaydeder, ihlal reddeder."""
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown

    def klasor(self, metin):
        k = os.path.join(self.proje, "Claude_Orkestrasyon", "001-deneme")
        os.makedirs(k)
        with open(os.path.join(k, "calisma_ozeti_20261026.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(metin)
        return k

    def test_golge_engellemez_ama_kaydeder(self):
        isler = importlib.import_module("komutlar.isler")
        self.assertIsNone(isler._ozet_eksigi(self.klasor(YENI)))
        with open(os.path.join(self.sd, "gunluk.jsonl"), encoding="utf-8") as f:
            olaylar = [json.loads(s) for s in f if s.strip()]
        self.assertTrue(any(o.get("tur") == "kapi_golge" and o.get("kapi") == "sef_ozeti" for o in olaylar), olaylar)

    def test_ihlal_modunda_haritasiz_reddedilir_tam_ozet_gecer(self):
        import kapi_mod as KM
        isler = importlib.import_module("komutlar.isler")
        k = self.klasor(YENI)
        with mock.patch.object(KM, "mod", side_effect=IHLAL_SEF):
            self.assertIn("## Harita", isler._ozet_eksigi(k) or "")
        os.rename(os.path.join(self.proje, "Claude_Orkestrasyon"), os.path.join(self.proje, "eski"))
        k2 = self.klasor(IKI)
        with mock.patch.object(KM, "mod", side_effect=IHLAL_SEF):
            self.assertIsNone(isler._ozet_eksigi(k2))

    def test_kapi_kapatilabilir(self):
        import kapi_mod as KM
        isler = importlib.import_module("komutlar.isler")
        k = self.klasor(YENI)
        with mock.patch.object(KM, "mod", side_effect=IHLAL_SEF), \
                mock.patch.dict(os.environ, {"ORKESTRA_SEF_OZETI_KAPISI": "0"}):
            self.assertIsNone(isler._ozet_eksigi(k))


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
