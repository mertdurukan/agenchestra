"""I-329 P4: araç hatası tekrar sayımı, kök neden durumu ve arac_metni bağlantısı (ADR-0141)."""
import json
import os
import sys
import tempfile
import unittest

AD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AD, "..", "scripts"))

import hata_en_cok as HE  # noqa: E402
import hata_kayit as HK  # noqa: E402
import kok_neden_enjeksiyonu as K  # noqa: E402

HATA = "Exit code 1: komut bulunamadı"


def yaz(sd, n, arac="Bash", ileti=HATA):
    for _ in range(n):
        HK.arac_hatasi(sd, arac, ileti, "ana")


def arac_satirlari(sd):
    return [r for r in HE.birlestir(sd, 0, "arac")]


class Sayim(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.sd = self._t.name

    def tearDown(self):
        self._t.cleanup()

    def test_arac_kaynagi_sayilir_ve_filtrelenir(self):
        yaz(self.sd, 2)
        HK.kaydet(self.sd, "hook", "hook-red", "x")
        (r,) = arac_satirlari(self.sd)
        self.assertEqual((r["kaynak"], r["sayi"], r["durum"]), ("arac", 2, "acik"))
        self.assertEqual({x["kaynak"] for x in HE.birlestir(self.sd)}, {"arac", "hook"})

    def test_farkli_arac_ayri_imza(self):
        yaz(self.sd, 1, "Bash")
        yaz(self.sd, 1, "Edit")
        self.assertEqual(len(arac_satirlari(self.sd)), 2)

    def test_eşik_uyarisi_2_yok_3_var(self):
        yaz(self.sd, 2)
        self.assertEqual(HE.esik_satiri(self.sd), "")
        yaz(self.sd, 1)
        self.assertIn("Bash", HE.esik_satiri(self.sd))

    def test_coz_yeniden_ac(self):
        yaz(self.sd, 3)
        im = arac_satirlari(self.sd)[0]["imza"]
        self.assertTrue(HE.coz(self.sd, im))
        self.assertEqual(arac_satirlari(self.sd)[0]["durum"], "cozuldu")
        self.assertEqual(HE.esik_satiri(self.sd), "")          # çözülen imza uyarı üretmez
        d = HE.kok_durum_oku(self.sd)                            # zaman damgası saniye çözünürlüklü: çözümü geçmişe al
        d[im]["zaman"] = "2000-01-01T00:00:00"
        with open(os.path.join(self.sd, HE.KOK_DURUM_DOSYA), "w", encoding="utf-8") as f:
            json.dump(d, f)
        yaz(self.sd, 1)                                          # çözümden sonra yeni satır
        self.assertEqual(arac_satirlari(self.sd)[0]["durum"], "yeniden_acildi")
        self.assertIn("Bash", HE.esik_satiri(self.sd))

    def test_bozuk_durum_dosyasi_acik_sayilir(self):
        yaz(self.sd, 1)
        with open(os.path.join(self.sd, HE.KOK_DURUM_DOSYA), "w") as f:
            f.write("{bozuk")
        self.assertEqual(arac_satirlari(self.sd)[0]["durum"], "acik")

    def test_satir_metni_durum_gosterir(self):
        yaz(self.sd, 1)
        self.assertIn("[açık]", HE.satir_metni(arac_satirlari(self.sd)[0]))


class AracMetniBaglanti(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.sd = self._t.name
        self.inp = {"session_id": "s", "tool_name": "Bash", "error": HATA}

    def tearDown(self):
        self._t.cleanup()

    def test_esik_altinda_not_yok_ustunde_var(self):
        yaz(self.sd, 2)
        self.assertEqual(K.tekrar_notu(self.inp, self.sd), "")
        yaz(self.sd, 1)
        n = K.tekrar_notu(self.inp, self.sd)
        self.assertIn("3 kez", n)
        self.assertIn("açık", n)

    def test_cozulunce_durum_degisir(self):
        yaz(self.sd, 3)
        HE.coz(self.sd, arac_satirlari(self.sd)[0]["imza"])
        self.assertIn("çözüldü", K.tekrar_notu(self.inp, self.sd))

    def test_baska_hata_not_almaz(self):
        yaz(self.sd, 3)
        self.assertEqual(K.tekrar_notu({"tool_name": "Edit", "error": "başka"}, self.sd), "")

    def test_bozuk_girdi_istisna_atmaz(self):
        self.assertEqual(K.tekrar_notu({}, self.sd), "")
        self.assertEqual(K.tekrar_notu(None, self.sd), "")


if __name__ == "__main__":
    unittest.main()
