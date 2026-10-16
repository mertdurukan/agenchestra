"""`is kapat` teknik_detay.md üretimi (G-137, K1-K5). Geçici proje dizininde koşar."""
import io
import os
import re
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace
from unittest import mock

import test_cekirdek as TC
import test_is_cli as _TI

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from komutlar import isler  # noqa: E402
import teknik  # noqa: E402
import is_kaydi  # noqa: E402
import is_kaydi  # noqa: E402


class TeknikDetay(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown
    cli = TC.Cekirdek.cli
    kart = TC.Cekirdek.kart
    ac = _TI.IsCli.ac
    oku = _TI.IsCli.oku
    kart_json = _TI.IsCli.kart_json

    def kartli_is(self, kart_sayisi=2):
        i, klasor = self.ac()
        for n in range(kart_sayisi):
            r = self.yeni_kart(i, f"Kart sırası {n + 1}", "Çalışır mı?")
            self.assertEqual(r.returncode, 0, r.stderr)
        return i, klasor

    def yeni_kart(self, i, baslik, soru):
        return self.cli("kart", "yeni", "--is", i, "--baslik", baslik, "--soru", soru, "--sinif", "belge",
                        "--kabul", "k", "--yazma", "docs/**")

    def dosya(self, klasor):
        return os.path.join(klasor, "teknik_detay.md")

    def kapat_dogrudan(self, i):
        err, out = io.StringIO(), io.StringIO()
        with mock.patch.object(isler, "sd_gerekli", return_value=self.sd), redirect_stderr(err), redirect_stdout(out):
            isler.cmd_is_kapat(SimpleNamespace(is_id=i))
        return err.getvalue(), out.getvalue()

    def test_k1_kartli_is_dosya_olusur_sirayla(self):
        i, klasor = self.kartli_is()
        self.assertFalse(os.path.exists(self.dosya(klasor)))
        r = self.cli("is", "kapat", i)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.exists(self.dosya(klasor)))
        with open(self.dosya(klasor), encoding="utf-8") as f:
            m = f.read()
        kartlar = self.oku(os.path.join(klasor, "is.json"))["kartlar"]
        self.assertEqual(len(kartlar), 2)
        yerler = [m.find(g) for g in kartlar]
        self.assertTrue(all(y >= 0 for y in yerler), yerler)
        self.assertEqual(yerler, sorted(yerler))
        self.assertIn(f"# Teknik detay — {i}", m)

    def test_k2_kartsiz_is_dosya_yazilmaz(self):
        i, klasor = self.ac()
        r = self.cli("is", "kapat", i)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(self.dosya(klasor)))
        self.assertEqual(self.oku(os.path.join(klasor, "is.json"))["durum"], "kapandi")

    def test_k3_yeniden_acilip_kapanirsa_guncellenir_kopya_olmaz(self):
        i, klasor = self.kartli_is(1)
        self.cli("is", "kapat", i)
        with open(self.dosya(klasor), encoding="utf-8") as f:
            ilk = f.read()
        is_kaydi.is_durum(self.sd, i, "acik")  # yeniden aç
        r = self.yeni_kart(i, "Sonradan", "Peki?")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.cli("is", "kapat", i)
        with open(self.dosya(klasor), encoding="utf-8") as f:
            ikinci = f.read()
        self.assertGreater(len(ikinci), len(ilk))
        self.assertIn("Sonradan", ikinci)
        md_ler = [a for a in os.listdir(klasor) if a.lower().endswith(".md") and "teknik" in a.lower()]
        self.assertEqual(md_ler, ["teknik_detay.md"])

    def test_k4a_uretici_hata_firlatirsa_kapanis_bozulmaz(self):
        i, klasor = self.kartli_is(1)
        with mock.patch.object(teknik, "md", side_effect=RuntimeError("patladı")):
            err, out = self.kapat_dogrudan(i)
        self.assertIn("uyarı", err)
        self.assertIn("kapandi", out)
        self.assertEqual(self.oku(os.path.join(klasor, "is.json"))["durum"], "kapandi")
        self.assertFalse(os.path.exists(self.dosya(klasor)))

    def test_k4b_klasor_yazilamazsa_kapanis_bozulmaz(self):
        i, klasor = self.kartli_is(1)
        os.makedirs(self.dosya(klasor))  # dosya yolu dizin: yazma başarısız olur
        r = self.cli("is", "kapat", i)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("uyarı", r.stderr)
        self.assertEqual(self.oku(os.path.join(klasor, "is.json"))["durum"], "kapandi")

    def test_k5_sir_maskeli_ve_ilk_satir_zaman(self):
        i, klasor = self.ac()
        r = self.yeni_kart(i, "password=Hunter2Gizli kartı", "token: abc123gizli?")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.cli("is", "kapat", i)
        with open(self.dosya(klasor), encoding="utf-8") as f:
            m = f.read()
        self.assertNotIn("Hunter2Gizli", m)
        self.assertNotIn("abc123gizli", m)
        self.assertRegex(m.splitlines()[0], r"^_Üretim zamanı: \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


if __name__ == "__main__":
    unittest.main()
