"""G-175: scripts/hata_kayit.py (imza, kaydet) ve üç kaynağın (hook, CLI, özet) bağlanması."""
import io
import json
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr
from unittest import mock

AD = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(AD, "..", "scripts")
sys.path.insert(0, SCRIPTS)

import hata_kayit as HK  # noqa: E402
import hook  # noqa: E402
import ozet  # noqa: E402
from komutlar import _ortak  # noqa: E402


def satirlar(sd):
    yol = os.path.join(sd, "hata.jsonl")
    if not os.path.exists(yol):
        return []
    with open(yol, encoding="utf-8") as f:
        return [json.loads(s) for s in f if s.strip()]


class Imza(unittest.TestCase):
    def test_gecici_dosya_ayni_imza(self):
        a = HK.imza("OSError", "[Errno 22] Invalid argument: 'C:\\x\\y\\.tmp_a1b2'")
        b = HK.imza("OSError", "[Errno 22] Invalid argument: 'D:\\baska\\.tmp_c9d8'")
        self.assertEqual(a, b)
        self.assertEqual(HK.imza("OSError", "[Errno 22] ... .tmp_a1b2"), HK.imza("OSError", "[Errno 22] ... .tmp_ff00"))

    def test_farkli_anahtar_farkli_imza(self):
        self.assertNotEqual(HK.imza("KeyError", "'Notification'"), HK.imza("KeyError", "'session_start'"))

    def test_sayi_ve_kimlik_cikar(self):
        self.assertEqual(HK.imza("E", "satir 12 kimlik deadbeef1234"), HK.imza("E", "satir 99 kimlik 0123abcd9999"))


class Kaydet(unittest.TestCase):
    def test_satir_alanlari(self):
        with tempfile.TemporaryDirectory() as sd:
            HK.kaydet(sd, "hook", "OSError", "x" * 500, {"yer": "t"})
            (s,) = satirlar(sd)
            for k in ("kaynak", "imza", "tur", "ileti", "zaman", "oturum"):
                self.assertIn(k, s)
            self.assertEqual(s["kaynak"], "hook")
            self.assertEqual(len(s["ileti"]), 300)

    def test_yazilamayan_dizin_istisna_yok(self):
        with tempfile.TemporaryDirectory() as sd:
            dosya = os.path.join(sd, "dosya")
            open(dosya, "w").close()
            hedef = os.path.join(dosya, "alt")   # dosyanın altı: dizin değil
            err = io.StringIO()
            with redirect_stderr(err):
                HK.kaydet(hedef, "cli", "E", "m")
            self.assertEqual(len(err.getvalue().strip().splitlines()), 1)


class Baglantilar(unittest.TestCase):
    def test_hook_gunluk_ve_kayit(self):
        with tempfile.TemporaryDirectory() as sd:
            hook._hata_yaz(sd, "yer1", KeyError("Notification"))
            with open(os.path.join(sd, "gunluk.jsonl"), encoding="utf-8") as f:
                g = json.loads(f.readline())
            self.assertEqual(g["tur"], "hook-hatasi")
            self.assertEqual(g["olay"], "yer1")
            (s,) = satirlar(sd)
            self.assertEqual(s["kaynak"], "hook")

    def test_hook_kaydet_patlarsa_dusmez(self):
        with tempfile.TemporaryDirectory() as sd:
            with mock.patch.object(HK, "kaydet", side_effect=RuntimeError("x")):
                hook._hata_yaz(sd, "yer", ValueError("v"))
            self.assertTrue(os.path.exists(os.path.join(sd, "gunluk.jsonl")))

    def test_cli_kod2_kaydedilmez(self):
        with tempfile.TemporaryDirectory() as sd, mock.patch.object(_ortak.L, "durum_dizini", return_value=sd):
            err = io.StringIO()
            with redirect_stderr(err), self.assertRaises(SystemExit) as c:
                _ortak.hata("kullanım hatası")
            self.assertEqual(c.exception.code, 2)
            self.assertIn("orkestra: kullanım hatası", err.getvalue())
            self.assertEqual(satirlar(sd), [])

    def test_cli_kod1_kaydedilir_ve_hizli(self):
        with tempfile.TemporaryDirectory() as sd, mock.patch.object(_ortak.L, "durum_dizini", return_value=sd):
            err = io.StringIO()
            t = time.perf_counter()
            with redirect_stderr(err), self.assertRaises(SystemExit) as c:
                _ortak.hata("bozuldu", 1)
            sure = time.perf_counter() - t
            self.assertEqual(c.exception.code, 1)
            self.assertIn("orkestra: bozuldu", err.getvalue())
            (s,) = satirlar(sd)
            self.assertEqual(s["kaynak"], "cli")
            self.assertLess(sure, 0.2)

    def test_ozet_hata_dali_kaydeder(self):
        with tempfile.TemporaryDirectory() as sd:
            with mock.patch.object(ozet, "olustur", side_effect=ValueError("bozuk")):
                self.assertIsNone(ozet.yaz(sd, "proje"))
            self.assertTrue(os.path.exists(os.path.join(sd, "ozet_hata.txt")))
            (s,) = satirlar(sd)
            self.assertEqual(s["kaynak"], "ozet")
            self.assertEqual(s["tur"], "ValueError")


if __name__ == "__main__":
    unittest.main()
