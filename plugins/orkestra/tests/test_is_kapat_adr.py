"""ADR kapısı (P-015): `orkestra is kapat` plan.md'de geçerli bir 'ADR:' satırı olmadan reddeder."""
import os
import unittest

import test_cekirdek as TC


class IsKapatAdr(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown

    def cli(self, *args, kapi="1"):
        return TC.kos([TC.CLI, *args], self.proje, ortam={"ORKESTRA_ADR_KAPISI": kapi})

    def ac(self, plan=None):
        klasor = os.path.join(self.proje, "is1")
        r = self.cli("is", "ac", "Deneme işi", "--klasor", klasor, "--devral")  # test aynı klasörde kapalı işin yerine yenisini açar (ADR-0037)
        self.assertEqual(r.returncode, 0, r.stderr)
        if plan is not None:
            with open(os.path.join(klasor, "plan.md"), "w", encoding="utf-8", newline="\n") as f:
                f.write(plan)
        return r.stdout.strip().splitlines()[-1], klasor

    GECERLI_ADR = ("# ADR-0001\n\n**Durum:** Kabul edildi\n\n**Tarih:** 2026-10-18\n\n**Bağlam:** neden gerekti\n\n"
                   "**Karar:** şu yapıldı\n\n**Seçenekler:**\n- A: elendi, çünkü X\n\n**Sonuçlar:** olumlu, olumsuz, geri alma\n")

    def adr_yaz(self, ad="ADR-0001-deneme.md", icerik=None):
        os.makedirs(os.path.join(self.proje, "adr"), exist_ok=True)
        with open(os.path.join(self.proje, "adr", ad), "w", encoding="utf-8") as f:
            f.write(self.GECERLI_ADR if icerik is None else icerik)

    def test_adr_zorunlu_alan_eksikse_reddeder(self):
        self.adr_yaz(icerik="# ADR-0001\n\n**Durum:** Kabul edildi\n\n**Karar:** x\n")
        i, _ = self.ac("# Plan\n\n**ADR:** ADR-0001\n")
        r = self.kapat(i)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Tarih", r.stderr + r.stdout)

    def test_adr_bos_alan_reddedilir(self):
        self.adr_yaz(icerik=self.GECERLI_ADR.replace("**Karar:** şu yapıldı", "**Karar:**\n\n**Seçenekler:**", 1))
        i, _ = self.ac("# Plan\n\n**ADR:** ADR-0001\n")
        r = self.kapat(i)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Karar", r.stderr + r.stdout)

    def kapat(self, i):
        return self.cli("is", "kapat", i, kapi="1")

    def test_plan_yoksa_reddeder(self):
        i, _ = self.ac()
        r = self.kapat(i)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("ADR kaydı eksik", r.stderr + r.stdout)

    def test_adr_satiri_yoksa_reddeder(self):
        i, _ = self.ac("# Plan\n\nP1: bir şey\n")
        r = self.kapat(i)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("'ADR:' satırı yok", r.stderr + r.stdout)

    def test_var_olmayan_adr_dosyasi_reddedilir(self):
        i, _ = self.ac("# Plan\n\n**ADR:** ADR-0007\n")
        r = self.kapat(i)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("ADR-0007", r.stderr + r.stdout)

    def test_var_olan_adr_ile_kapanir(self):
        self.adr_yaz()
        i, _ = self.ac("# Plan\n\n**ADR:** ADR-0001\n")
        self.assertEqual(self.kapat(i).returncode, 0)

    def test_gerekmez_nedenle_kapanir(self):
        i, _ = self.ac("# Plan\n\n**ADR:** gerekmez — yalnız metin düzeltmesi\n")
        self.assertEqual(self.kapat(i).returncode, 0)

    def test_nedensiz_gerekmez_reddedilir(self):
        i, _ = self.ac("# Plan\n\n**ADR:** gerekmez\n")
        self.assertNotEqual(self.kapat(i).returncode, 0)

    def test_ozetsiz_ve_kapali_kapi_atlar(self):
        i, _ = self.ac()
        self.assertEqual(self.cli("is", "kapat", i, "--ozetsiz", "iş yapılmadı").returncode, 0)
        j, _ = self.ac()
        self.assertEqual(self.cli("is", "kapat", j, kapi="0").returncode, 0)


if __name__ == "__main__":
    unittest.main()
