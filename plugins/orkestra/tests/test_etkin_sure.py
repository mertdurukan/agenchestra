"""I-259: ana tur satırında etkin süre (bekleme hariç) ve raporun etkin/ham ayrımı."""
import json
import os
import sys
import tempfile
import unittest

AD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AD, "..", "scripts"))

import etkin_sure as ES  # noqa: E402
import is_rapor  # noqa: E402

DK = 60000


class EsikTesti(unittest.TestCase):
    def test_esik_alti_ham_esit_ustu_sifir(self):
        self.assertEqual(ES.etkin_ms(10 * DK, esik=120), 10 * DK)
        self.assertEqual(ES.etkin_ms(120 * DK, esik=120), 120 * DK)
        self.assertEqual(ES.etkin_ms(121 * DK, esik=120), 0)

    def test_iki_esikle_iki_sonuc_ve_etkin_ham_asmaz(self):
        self.assertEqual(ES.etkin_ms(121 * DK, esik=60), 0)
        self.assertEqual(ES.etkin_ms(121 * DK, esik=240), 121 * DK)
        for sure in (0, 5 * DK, 119 * DK, 500 * DK):
            for esik in (60, 120, 240):
                self.assertLessEqual(ES.etkin_ms(sure, esik=esik), sure)

    def test_sure_yoksa_none(self):
        self.assertIsNone(ES.etkin_ms(None))
        self.assertIsNone(ES.etkin_ms("x"))

    def test_ayar_varsayilan_ve_proje_ezmesi(self):
        self.assertEqual(ES.esik_dk(), 120.0)  # ayarlar/zaman_etkin.json
        with tempfile.TemporaryDirectory() as sd:
            with open(os.path.join(sd, "zaman_etkin.json"), "w", encoding="utf-8") as f:
                json.dump({"esik_dk": 60}, f)
            self.assertEqual(ES.esik_dk(sd), 60.0)
            self.assertEqual(ES.etkin_ms(90 * DK, sd), 0)


class RaporTesti(unittest.TestCase):
    def test_alansiz_eski_satir_ham_sureye_duser(self):
        eski = {"tur": "ana", "sure_ms": 90 * DK}
        yeni = {"tur": "ana", "sure_ms": 300 * DK, "etkin_ms": 0}
        self.assertEqual(is_rapor._etkin(eski), 90 * DK)
        self.assertEqual(is_rapor._etkin(yeni), 0)

    def test_rapor_etkin_ve_ham_ayri(self):
        with tempfile.TemporaryDirectory() as sd:
            with open(os.path.join(sd, "zaman.jsonl"), "w", encoding="utf-8") as f:
                for r in ({"tur": "ana", "is": "I-001", "oturum": "s1", "zaman": "2026-10-30T10:00:00+03:00",
                           "sure_ms": 10 * DK, "etkin_ms": 10 * DK},
                          {"tur": "ana", "is": "I-001", "oturum": "s1", "zaman": "2026-10-30T11:00:00+03:00",
                           "sure_ms": 300 * DK, "etkin_ms": 0},
                          {"tur": "ana", "is": "I-001", "oturum": "s1", "zaman": "2026-10-30T12:00:00+03:00",
                           "sure_ms": 20 * DK}):
                    f.write(json.dumps(r) + "\n")
            satir = {s["is"]: s for s in is_rapor.rapor(sd)["satirlar"]}["I-001"]
            self.assertAlmostEqual(satir["claude_sn"], 330 * 60)
            self.assertAlmostEqual(satir["etkin_sn"], 30 * 60)


if __name__ == "__main__":
    unittest.main()
