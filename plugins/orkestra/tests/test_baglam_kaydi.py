"""I-139 P2: hook'un enjekte ettiği bağlamın kaydı (gunluk.jsonl tur=baglam: hash ve uzunluk, metin yok)."""
import json
import os
import sys
import unittest
from unittest import mock

TESTLER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TESTLER)
sys.path.insert(0, os.path.join(os.path.dirname(TESTLER), "scripts"))
import baglam_kaydi  # noqa: E402
import test_hook_baglam_boyut as TB  # noqa: E402


def _satirlar(sd):
    yol = os.path.join(sd, "gunluk.jsonl")
    if not os.path.isfile(yol):
        return []
    with open(yol, encoding="utf-8") as f:
        return [json.loads(s) for s in f if s.strip()]


class BaglamKaydi(unittest.TestCase):
    def setUp(self):
        self.h = TB.BaglamBoyutu("test_kriter1_tablo_her_olay_icin_onceki_sonraki")
        self.h.setUp()
        self.addCleanup(self.h.tearDown)

    def test_user_prompt_submit_sonrasi_son_satir_baglam(self):
        ek = self.h.ups()
        baglam = [s for s in _satirlar(self.h.sd) if s["tur"] == "baglam"]
        self.assertEqual(len(baglam), 1)
        b = baglam[0]
        self.assertEqual(b["olay"], "UserPromptSubmit")
        self.assertEqual(len(b["hash"]), 12)
        self.assertEqual(b["uzunluk"], len(ek))
        self.assertEqual(b["hash"], baglam_kaydi.ozet(ek)["hash"])

    def test_session_start_kaydi(self):
        ek = self.h.session_start()
        b = [s for s in _satirlar(self.h.sd) if s["tur"] == "baglam"][-1]
        self.assertEqual((b["olay"], b["uzunluk"]), ("SessionStart", len(ek)))

    def test_satirda_baglam_metni_gecmez(self):
        ek = self.h.ups()
        ham = open(os.path.join(self.h.sd, "gunluk.jsonl"), encoding="utf-8").read()
        baglam_satiri = [s for s in ham.splitlines() if '"tur": "baglam"' in s][0]
        self.assertNotIn(ek.splitlines()[0][:40], baglam_satiri)

    def test_yazim_hatasi_hook_ciktisini_degistirmez(self):
        once = self.h.ups()
        gercek = baglam_kaydi.L.jsonl_ekle

        def bozuk(yol, kayit):
            if kayit.get("tur") == "baglam":
                raise OSError("disk")
            gercek(yol, kayit)

        with mock.patch.object(baglam_kaydi.L, "jsonl_ekle", side_effect=bozuk):
            sonra = self.h.ups()
        self.assertEqual(once, sonra)

    def test_kapatma_ve_bos_baglam(self):
        with mock.patch.dict(os.environ, {"ORKESTRA_BAGLAM_KAYDI": "0"}):
            self.h.ups()
        self.assertEqual([s for s in _satirlar(self.h.sd) if s["tur"] == "baglam"], [])
        baglam_kaydi.kaydet(self.h.sd, "X", "o", "")
        baglam_kaydi.kaydet(None, "X", "o", "metin")
        self.assertEqual([s for s in _satirlar(self.h.sd) if s["tur"] == "baglam"], [])


if __name__ == "__main__":
    unittest.main()
