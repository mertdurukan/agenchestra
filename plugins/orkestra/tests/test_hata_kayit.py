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


class Davranis(unittest.TestCase):
    """ADR-0037: ajan davranış hatası sinif=davranis ve kök neden alanıyla kaydedilir; kod hatası satırı değişmez."""

    def test_davranis_satiri_kok_neden_alani(self):
        with tempfile.TemporaryDirectory() as sd:
            HK.davranis(sd, "is-klasoru-yanlis", "klasörde başka işin kaydı var: C:\\x\\y", {"komut": "is ac"})
            (s,) = satirlar(sd)
            self.assertEqual((s["kaynak"], s["sinif"], s["tur"]), ("davranis", "davranis", "is-klasoru-yanlis"))
            self.assertEqual(s["kok"]["kaynak"], "betik")
            self.assertIs(s["kok"]["onlenebilir"], True)
            self.assertTrue(s["kok"]["cozum"])
            self.assertEqual(s["baglam"], {"komut": "is ac"})

    def test_bilinmeyen_tur_belirsiz_ve_onlenebilir_null(self):
        with tempfile.TemporaryDirectory() as sd:
            HK.davranis(sd, "yeni-tur", "x")
            (s,) = satirlar(sd)
            self.assertEqual(s["kok"]["kaynak"], "belirsiz")
            self.assertIsNone(s["kok"]["onlenebilir"])

    def test_hook_red_kaynagi_kapi_kimligine_gore(self):
        self.assertEqual(HK.kok_neden("hook-red", "orkestra: K-003: kutu aracı")["kaynak"], "kural")
        self.assertEqual(HK.kok_neden("hook-red", "orkestra: ortak defter elle düzenlenmez")["kaynak"], "betik")

    def test_kod_hatasi_satirinda_sinif_ve_kok_yok(self):
        with tempfile.TemporaryDirectory() as sd:
            HK.kaydet(sd, "hook", "OSError", "x")
            (s,) = satirlar(sd)
            self.assertNotIn("sinif", s)
            self.assertNotIn("kok", s)

    def test_hata_en_cok_davranisi_sayar(self):
        import hata_en_cok as HE
        with tempfile.TemporaryDirectory() as sd:
            for _ in range(2):
                HK.davranis(sd, "kabuk-sozdizimi", "Get-ChildItem x")
            HK.kaydet(sd, "hook", "OSError", "x")
            r = [x for x in HE.birlestir(sd, kaynak="davranis")]
            self.assertEqual([(x["kaynak"], x["sayi"]) for x in r], [("davranis", 2)])
            self.assertTrue(any(x["kaynak"] == "davranis" for x in HE.birlestir(sd)))


class RetBaglami(unittest.TestCase):
    """I-224: hook reddi satırı araç, dosya, ajan, deneme, maskeli metin parçası ve R1–R9 sınıfı taşır."""

    def test_yeni_ret_kaydi_alanlari(self):
        with tempfile.TemporaryDirectory() as sd, mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "o1"}):
            HK.davranis(sd, "hook-red", "orkestra: P-016: onay bekleniyor", arac="Write", dosya="a/plan.md",
                        ajan="alt", metin="x" * 500)
            (s,) = satirlar(sd)
            self.assertEqual((s["arac"], s["dosya"], s["ajan"], s["deneme"]), ("Write", "a/plan.md", "alt", 1))
            self.assertEqual(len(s["metin200"]), 200)
            self.assertEqual((s["kapi"], s["ret_sinif"]), ("P-016", "R6"))
            self.assertEqual(s["sinif"], "davranis")   # eski anlam korunur

    def test_deneme_ayni_oturum_ayni_kapi(self):
        with tempfile.TemporaryDirectory() as sd:
            with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "o1"}):
                for _ in range(2):
                    HK.davranis(sd, "hook-red", "orkestra: K-003: x", arac="Write")
                HK.davranis(sd, "hook-red", "orkestra: P-005: sıra", arac="Write")
            with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "o2"}):
                HK.davranis(sd, "hook-red", "orkestra: K-003: x", arac="Write")
            self.assertEqual([(s["kapi"], s["deneme"]) for s in satirlar(sd)],
                             [("K-003", 1), ("K-003", 2), ("P-005", 1), ("K-003", 1)])

    def test_metin_maskelenir(self):
        with tempfile.TemporaryDirectory() as sd:
            sir = "password=Aa1" + "b" * 20
            HK.kaydet(sd, "hook", "hook-red", "orkestra: K-005", metin="önce " + sir)
            (s,) = satirlar(sd)
            self.assertNotIn("b" * 20, s["metin200"])
            self.assertIn("<gizli>", s["metin200"])

    def test_sinif_eslemesi(self):
        import ret_nedeni as RN
        self.assertEqual(RN.ret_sinifi("K-003"), "R1")
        self.assertEqual(RN.ret_sinifi("P-010"), "R8")
        self.assertEqual(RN.ret_sinifi("X-999"), RN.SINIFLANMAMIS)
        self.assertEqual(RN.ret_sinifi(None), RN.SINIFLANMAMIS)
        self.assertTrue(set(RN.KAPI_SINIF.values()) <= set(RN.RET_SINIFLARI))

    def test_gecersiz_ajan_null(self):
        with tempfile.TemporaryDirectory() as sd:
            HK.kaydet(sd, "hook", "hook-red", "m", ajan="baska")
            (s,) = satirlar(sd)
            self.assertIsNone(s["ajan"])
            self.assertEqual(s["ret_sinif"], "siniflanmamis")


class EskiBicim(unittest.TestCase):
    """I-224: ret bağlamsız eski satırlar okunur kalır; deneme sayımı onları saymaz, birleştirici bozulmaz."""

    def test_eski_satir_okunur(self):
        import hata_en_cok as HE
        eski = {"v": 1, "kaynak": "davranis", "imza": "hook-red: orkestra: K-N: x", "tur": "hook-red",
                "ileti": "orkestra: K-003: x", "zaman": "2026-10-22T10:00:00", "oturum": "o1", "sinif": "davranis",
                "kok": {"kaynak": "kural", "onlenebilir": None, "cozum": ""}}
        with tempfile.TemporaryDirectory() as sd:
            with open(os.path.join(sd, "hata.jsonl"), "w", encoding="utf-8") as f:
                f.write(json.dumps(eski, ensure_ascii=False) + "\n")
            self.assertEqual(HK.ret_baglami(eski), {k: None for k in HK.RET_ALANLARI})
            with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "o1"}):
                HK.davranis(sd, "hook-red", "orkestra: K-003: x", arac="Edit")
            eski_s, yeni_s = satirlar(sd)
            self.assertEqual(eski_s, eski)
            self.assertEqual(yeni_s["deneme"], 1)
            self.assertEqual(HK.ret_baglami(yeni_s)["arac"], "Edit")
            r = list(HE.birlestir(sd, kaynak="davranis"))
            self.assertEqual(sum(x["sayi"] for x in r), 2)

    def test_kwargssiz_cagri_eski_bicim(self):
        with tempfile.TemporaryDirectory() as sd:
            HK.davranis(sd, "hook-red", "orkestra: K-003: x")
            (s,) = satirlar(sd)
            for k in HK.RET_ALANLARI:
                self.assertNotIn(k, s)


if __name__ == "__main__":
    unittest.main()
