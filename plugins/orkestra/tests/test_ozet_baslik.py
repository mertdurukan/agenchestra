"""ADR-0074: çalışma özeti başlığı yalnız Jira kodu ya da genel olamaz (Jira başlığı ya da en kısa görev başlığı)."""
import importlib
import os
import sys
import tempfile
import unittest
from unittest import mock

AD = os.path.dirname(os.path.abspath(__file__))
KOK = os.path.join(AD, "..")
sys.path.insert(0, os.path.join(KOK, "scripts"))

import is_kaydi as IK  # noqa: E402

GOVDE = ("\n## Özet\n\n***Şef Özeti***\n\n**Amaç neydi?**\n\nx\n\n**Ne yapıldı?**\n\n- Yaptım.\n\n"
         "**Amaca tamamen ulaşıldı mı?**\n\nEvet.\n\n**Tamamen yapılanlar:**\n\n- x\n\n**Açık kalanlar:**\n\n- Yok\n"
         "\n## Ayrıntılar\n\n**Denenenler:**\n\n- x\n\n**Doğrulanamayanlar:**\n\n- Yok\n\n**Kararlar:**\n\n- Yok\n")


class Baslik(unittest.TestCase):
    def test_yalniz_kod_ya_da_genel_eksik(self):
        for h in ("# PE-635 çalışma özeti (16.10.2026, güncel)", "# PE-635: çalışma özeti (23.10.2026)",
                  "# T: çalışma özeti", "# çalışma özeti", "başlıksız metin"):
            self.assertTrue(IK.ozet_baslik_eksigi(h), h)

    def test_jira_basligi_ya_da_gorev_basligi_tamam(self):
        for h in ("# PE-635 Prompt injection/guardrail katmanı: çalışma özeti (16.10.2026)",
                  "# Özet bandı sayaç düzeltmesi: çalışma özeti (23.10.2026)"):
            self.assertIsNone(IK.ozet_baslik_eksigi(h), h)

    def test_olculen_yanlis_pozitifler_tamam_sayilir(self):
        # 23.10.2026 ölçümünde taslak ölçütün yanlış işaretlediği gerçek başlıklar
        for h in ("# Çalışma özeti: plan ✅/❌ doğrulama kapısı (I-025)",
                  "# Çalışma özeti: hafıza düzeltmesi tekrarı (I-147, 22.10.2026)",
                  "# Çalışma özeti Şef Özeti formatı (üretim anında): çalışma özeti (23.10.2026)",
                  "# PE-640 query_forecast: çalışma özeti (22.10.2026)",
                  "# yap: çalışma özeti (20.10.2026)"):
            if h.startswith("# yap"):
                self.assertTrue(IK.ozet_baslik_eksigi(h), h)
            else:
                self.assertIsNone(IK.ozet_baslik_eksigi(h), h)

    def test_sablon_baslik_yonergesi_tasir(self):
        with open(os.path.join(KOK, "sablonlar", "calisma_ozeti.md"), encoding="utf-8") as f:
            t = f.read()
        self.assertIn("<!-- başlık:", t)
        self.assertIn("Jira", t.split("## Özet")[0])


class Kapi(unittest.TestCase):
    def test_golge_modunda_uyarir_engellemez(self):
        isler = importlib.import_module("komutlar.isler")
        k = tempfile.mkdtemp()
        with open(os.path.join(k, "calisma_ozeti_20261023.md"), "w", encoding="utf-8") as f:
            f.write("# PE-635 çalışma özeti (23.10.2026)\n" + GOVDE)
        with mock.patch("kapi_mod.mod", return_value="golge"), mock.patch("kapi_mod.kaydet", return_value=True):
            self.assertIsNone(isler._ozet_eksigi(k))

    def test_ihlal_modu_kod_basligini_reddeder_baslikli_ozeti_kabul_eder(self):
        isler = importlib.import_module("komutlar.isler")
        k = tempfile.mkdtemp()
        yol = os.path.join(k, "calisma_ozeti_20261023.md")
        with mock.patch("kapi_mod.mod", return_value="ihlal"), mock.patch("kapi_mod.ret_kaydet", return_value=True):
            with open(yol, "w", encoding="utf-8") as f:
                f.write("# PE-635 çalışma özeti (23.10.2026)\n" + GOVDE)
            self.assertIn("yalnız Jira kodu", isler._ozet_eksigi(k) or "")
            with open(yol, "w", encoding="utf-8") as f:
                f.write("# PE-635 Prompt injection guardrail katmanı: çalışma özeti (23.10.2026)\n" + GOVDE)
            self.assertIsNone(isler._ozet_eksigi(k))


if __name__ == "__main__":
    unittest.main()
