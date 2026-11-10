"""Nesne kartı doğrulayıcısı (ADR-0177) birim testleri: derece, kaynak hiyerarşisi, kaynakça, sır, döküm eşleşmesi."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import nesne_karti as NK  # noqa: E402

KAYNAK_VT = ("- K1: tür=Veritabanı kataloğu; komut=SELECT data_type FROM information_schema.columns "
             "WHERE column_name = 'is_applied' | yol=-; ortam=kopya; saat=10.11.2026 14:39")
KAYNAK_PROSEDUR = ("- K2: tür=Prosedür gövdesi; komut=SELECT pg_get_functiondef('sportive.sp_transfer_applied_check'::regproc); "
                   "ortam=kopya; saat=10.11.2026 14:40")
KAYNAK_DOK = "- K3: tür=Doküman; yol=RNV/00_ortak/referans/klibre_veritabani_referans.md; ortam=repo; saat=10.11.2026 14:41"

GECERLI = "\n".join([
    "# sportive.fact_transfer_report.is_applied",
    "",
    "- [KESİN] Kolon tipi boolean, boş değer kabul eder (K1)",
    "- [KESİN] Prosedür kolonu FALSE yapar (K2)",
    "- [GÜÇLÜ] Alan uygulandı bilgisini taşır (K3)",
    "- [DOĞRULANMADI] TRUE değerini kimin yazdığı (K2)",
    "  - Neden: yazan satır prosedür gövdelerinde bulunamadı",
    "  - Kapatma: uygulama kodunda UPDATE ... is_applied taraması",
    "",
    KAYNAK_VT, KAYNAK_PROSEDUR, KAYNAK_DOK,
])


def turler(b):
    return sorted({x["tur"] for x in b})


class DogrulaTesti(unittest.TestCase):
    def setUp(self):
        self.ayar = NK.ayar_oku()

    def test_gecerli_kart_bulgusuz(self):  # S1
        self.assertEqual(NK.dogrula(GECERLI, self.ayar), [])

    def test_derecesiz_iddia_bulgu(self):  # S1
        k = GECERLI + "\n- Kolon her zaman dolu (K1)"
        self.assertEqual(turler(NK.dogrula(k, self.ayar)), ["derece_yok"])

    def test_bilinmeyen_derece_bulgu(self):
        k = GECERLI.replace("[GÜÇLÜ]", "[SANIRIM]")
        self.assertEqual(turler(NK.dogrula(k, self.ayar)), ["derece_yok"])

    def test_ascii_derece_kabul(self):
        k = GECERLI.replace("[KESİN]", "[KESIN]")
        self.assertEqual(NK.dogrula(k, self.ayar), [])

    def test_kesin_ikincil_kaynak_bulgu(self):  # S2
        k = GECERLI.replace("boş değer kabul eder (K1)", "boş değer kabul eder (K3)")
        self.assertEqual(turler(NK.dogrula(k, self.ayar)), ["kesin_ikincil_kaynak"])

    def test_kesin_birincil_ve_ikincil_karisik_gecer(self):  # S2
        k = GECERLI.replace("boş değer kabul eder (K1)", "boş değer kabul eder (K1, K3)")
        self.assertEqual(NK.dogrula(k, self.ayar), [])

    def test_guclu_ikincil_kaynakla_gecer(self):  # S2
        self.assertEqual(NK.dogrula(GECERLI, self.ayar), [])

    def test_atifsiz_kesin_bulgu(self):
        k = GECERLI.replace("boş değer kabul eder (K1)", "boş değer kabul eder")
        self.assertIn("kaynakca_eksik", turler(NK.dogrula(k, self.ayar)))

    def test_tanimsiz_atif_bulgu(self):
        k = GECERLI.replace("(K2)\n- [GÜÇLÜ]", "(K9)\n- [GÜÇLÜ]")
        b = NK.dogrula(k, self.ayar)
        self.assertIn("kaynakca_eksik", turler(b))
        self.assertTrue(any("K9" in x["ayrinti"] for x in b))

    def test_kaynakca_saat_eksik(self):  # S3
        k = GECERLI.replace("; saat=10.11.2026 14:39", "")
        b = NK.dogrula(k, self.ayar)
        self.assertEqual(turler(b), ["kaynakca_eksik"])
        self.assertIn("saat", b[0]["ayrinti"])

    def test_kaynakca_ortam_eksik(self):  # S3
        k = GECERLI.replace("ortam=kopya; ", "", 1)
        self.assertIn("kaynakca_eksik", turler(NK.dogrula(k, self.ayar)))

    def test_kaynakca_komut_ve_yol_yok(self):  # S3
        k = GECERLI.replace("yol=RNV/00_ortak/referans/klibre_veritabani_referans.md; ", "")
        self.assertIn("kaynakca_eksik", turler(NK.dogrula(k, self.ayar)))

    def test_bilinmeyen_kaynak_turu(self):
        k = GECERLI.replace("tür=Doküman", "tür=Kulaktan dolma")
        self.assertIn("kaynakca_eksik", turler(NK.dogrula(k, self.ayar)))

    def test_sir_kalibi_bulgu_degeri_yazmaz(self):  # S3
        k = GECERLI + "\n- K4: tür=Kod; komut=psql postgresql://kullanici:gizli123@sunucu/db; ortam=kopya; saat=10.11.2026 14:42"
        b = NK.dogrula(k, self.ayar)
        self.assertIn("kaynakca_sir", turler(b))
        self.assertNotIn("gizli123", json.dumps(b, ensure_ascii=False))

    def test_parola_atamasi_sir(self):  # S3
        k = GECERLI + "\n- K4: tür=Kod; komut=PGPASSWORD=abc123 psql; ortam=kopya; saat=10.11.2026 14:42"
        self.assertIn("kaynakca_sir", turler(NK.dogrula(k.replace("PGPASSWORD=", "password="), self.ayar)))

    def test_dogrulanmadi_neden_kapatma_eksik(self):  # S5
        k = GECERLI.replace("  - Kapatma: uygulama kodunda UPDATE ... is_applied taraması\n", "")
        b = NK.dogrula(k, self.ayar)
        self.assertEqual(turler(b), ["dogrulanmadi_eksik"])
        self.assertIn("Kapatma", b[0]["ayrinti"])

    def test_dogrulanmadi_alt_satirsiz(self):  # S5
        k = GECERLI.replace("  - Neden: yazan satır prosedür gövdelerinde bulunamadı\n", "") \
                   .replace("  - Kapatma: uygulama kodunda UPDATE ... is_applied taraması\n", "")
        self.assertEqual(len([x for x in NK.dogrula(k, self.ayar) if x["tur"] == "dogrulanmadi_eksik"]), 2)

    def test_bos_kart(self):
        self.assertEqual(turler(NK.dogrula("# Başlık\n\nSerbest metin.", self.ayar)), ["kart_bos"])
        self.assertEqual(turler(NK.dogrula("", self.ayar)), ["kart_bos"])

    def test_tek_hata_tek_bulgu(self):
        k = GECERLI.replace("; saat=10.11.2026 14:41", "")
        self.assertEqual(len(NK.dogrula(k, self.ayar)), 1)

    def test_proje_ayari_ezer(self):
        with tempfile.TemporaryDirectory() as sd:
            with open(os.path.join(sd, "nesne_karti.json"), "w", encoding="utf-8") as f:
                json.dump({"birincil_turler": ["Veritabanı kataloğu", "Prosedür gövdesi", "Doküman"]}, f, ensure_ascii=False)
            ayar = NK.ayar_oku(sd)
        k = GECERLI.replace("boş değer kabul eder (K1)", "boş değer kabul eder (K3)")
        self.assertEqual(NK.dogrula(k, ayar), [])

    def test_kapali_mod_ortam_degiskeni(self):
        eski = os.environ.get("ORKESTRA_NESNE_KARTI")
        os.environ["ORKESTRA_NESNE_KARTI"] = "0"
        try:
            self.assertEqual(NK.mod(self.ayar), "kapali")
        finally:
            if eski is None:
                os.environ.pop("ORKESTRA_NESNE_KARTI")
            else:
                os.environ["ORKESTRA_NESNE_KARTI"] = eski

    def test_ihlal_ayari_engelleyici_olmaz(self):
        self.assertEqual(NK.mod({"mod": "ihlal"}), "golge")


class DokumTesti(unittest.TestCase):
    def setUp(self):
        self.ayar = NK.ayar_oku()
        self.dokum = ("SELECT data_type FROM information_schema.columns WHERE column_name = 'is_applied'\n"
                      "boolean\n"
                      "SELECT pg_get_functiondef('sportive.sp_transfer_applied_check'::regproc)\n")

    def test_dokumde_gecen_kaynak_gecer(self):  # S4
        self.assertEqual(NK.dogrula(GECERLI, self.ayar, self.dokum), [])

    def test_bosluk_ve_harf_farki_normallesir(self):  # S4
        d = self.dokum.replace(" FROM ", "\n   from   ").upper()
        self.assertEqual(NK.dogrula(GECERLI, self.ayar, d), [])

    def test_dokumde_olmayan_kesin_kaynak_bulgu(self):  # S4
        b = NK.dogrula(GECERLI, self.ayar, "boolean\n")
        self.assertEqual(turler(b), ["kaynak_okunmadi"])
        self.assertEqual(len(b), 2)

    def test_kismi_eslesme_bulgu(self):  # S4 tam eşleşme: dökümde kaynak değerinin yalnız parçası var
        d = "SELECT data_type FROM information_schema.columns\n" + self.dokum.split("\n")[2]
        b = NK.dogrula(GECERLI, self.ayar, d)
        self.assertEqual([x["tur"] for x in b], ["kaynak_okunmadi"])
        self.assertIn("K1", b[0]["ayrinti"])

    def test_yalniz_guclu_kaynak_dokumde_aranmaz(self):  # S4 kapsamı: KESİN iddianın kaynakları
        self.assertEqual(NK.dogrula(GECERLI, self.ayar, self.dokum), [])

    def test_dokum_verilmezse_eslesme_aranmaz(self):
        self.assertEqual(NK.dogrula(GECERLI, self.ayar), [])


class BicimTesti(unittest.TestCase):  # S10
    def test_iddia_ve_kaynak_satiri_ayristirilir(self):
        iddialar, kaynaklar, hatali = NK._ayristir(GECERLI.splitlines())
        self.assertEqual([i["derece_ham"] for i in iddialar], ["KESİN", "KESİN", "GÜÇLÜ", "DOĞRULANMADI"])
        self.assertEqual(iddialar[0]["atif"], ["K1"])
        self.assertEqual(iddialar[3]["alt"], {"neden": "yazan satır prosedür gövdelerinde bulunamadı",
                                              "kapatma": "uygulama kodunda UPDATE ... is_applied taraması"})
        self.assertEqual(sorted(kaynaklar), ["K1", "K2", "K3"])
        self.assertEqual(hatali, [])

    def test_komut_ve_yol_ayiraci(self):
        _, kaynaklar, _ = NK._ayristir([KAYNAK_VT])
        a = kaynaklar["K1"]["alan"]
        self.assertEqual(a["tur"], "Veritabanı kataloğu")
        self.assertTrue(a["komut"].startswith("SELECT data_type"))
        self.assertEqual(a["yol"], "-")
        self.assertEqual((a["ortam"], a["saat"]), ("kopya", "10.11.2026 14:39"))

    def test_komutta_noktali_virgul_alan_ayirmaz(self):
        _, kaynaklar, _ = NK._ayristir([KAYNAK_PROSEDUR])
        self.assertTrue(kaynaklar["K2"]["alan"]["komut"].endswith("::regproc)"))

    def test_kart_var(self):
        self.assertTrue(NK.kart_var(GECERLI))
        self.assertFalse(NK.kart_var("Serbest anlatım, kart yok."))
        self.assertFalse(NK.kart_var("- [SANIRIM] bir şey"))


if __name__ == "__main__":
    unittest.main()
