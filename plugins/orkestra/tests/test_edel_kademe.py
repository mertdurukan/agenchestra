"""Üç değerli risk kademesi (ADR-0179): hafif / standart / kritik; eski `kucuk` hafif sayılır, kademesiz iş standarttır."""
import json
import os
import sys
import unittest
from unittest import mock

import test_cekirdek as TC

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import is_kaydi as IK  # noqa: E402
import is_sirasi as S  # noqa: E402
import muhendislik_kontrol as MK  # noqa: E402


class KademeNormal(unittest.TestCase):
    def test_tanimli_degerler(self):
        for k in S.KADEMELER:
            self.assertEqual(S.kademe_normal(k), k)
        self.assertEqual(S.kademe_normal("KRITIK"), "kritik")

    def test_kucuk_hafif_sayilir(self):
        self.assertEqual(S.kademe_normal("kucuk"), "hafif")

    def test_tanimsiz_none(self):
        for d in (None, "", "orta", 3):
            self.assertIsNone(S.kademe_normal(d))


class KademeKaydi(unittest.TestCase):
    cli = TC.Cekirdek.cli

    def setUp(self):
        TC.Cekirdek.setUp(self)
        self._ortam = mock.patch.dict(os.environ, {"ORKESTRA_SIRA_KAPISI": "1"})
        self._ortam.start()

    def tearDown(self):
        self._ortam.stop()
        TC.Cekirdek.tearDown(self)

    def is_klasoru(self, kayit, ad="001-deneme"):
        k = os.path.join(self.proje, "Claude_Orkestrasyon", ad)
        os.makedirs(k)
        with open(os.path.join(k, "is.json"), "w", encoding="utf-8") as f:
            json.dump(kayit, f)
        return k

    def test_kademesiz_is_standart(self):
        k = self.is_klasoru({"id": "I-001", "sira": S.SIRA_ADI})
        self.assertEqual(S.is_kademesi(k), S.KADEME_VARSAYILAN)
        self.assertEqual(S.is_kademesi(k), "standart")
        self.assertFalse(S.kucuk_kademe_mi(k))

    def test_eski_kucuk_hafif_ve_kucuk_kademe_suruyor(self):
        k = self.is_klasoru({"id": "I-001", "sira": S.SIRA_ADI, "kademe": "kucuk"})
        self.assertEqual(S.is_kademesi(k), "hafif")
        self.assertTrue(S.kucuk_kademe_mi(k))

    def test_hafif_kucuk_kademe_kapisini_da_acar(self):
        k = self.is_klasoru({"id": "I-001", "sira": S.SIRA_ADI, "kademe": "hafif"})
        self.assertTrue(S.kucuk_kademe_mi(k))

    def test_is_ac_kademe_yazar(self):
        for i, kademe in enumerate(("hafif", "standart", "kritik")):
            klasor = os.path.join(self.proje, "Claude_Orkestrasyon", f"00{i}-k")
            kayit = IK.is_ac(self.sd, f"kademe {kademe}", klasor, kademe=kademe)
            with open(os.path.join(kayit["klasor"], "is.json"), encoding="utf-8") as f:
                self.assertEqual(json.load(f).get("kademe"), kademe)
            self.assertEqual(S.is_kademesi(kayit["klasor"]), kademe)

    def test_is_ac_tanimsiz_kademe_reddedilir(self):
        with self.assertRaises(ValueError):
            IK.is_ac(self.sd, "kötü", os.path.join(self.proje, "Claude_Orkestrasyon", "009-k"), kademe="orta")

    def test_cli_kademe_kritik(self):
        klasor = os.path.join(self.proje, "Claude_Orkestrasyon", "010-kritik")
        r = self.cli("is", "ac", "kritik iş", "--klasor", klasor, "--kademe", "kritik")
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(klasor, "is.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f).get("kademe"), "kritik")

    def test_cli_tanimsiz_kademe_argparse_reddeder(self):
        r = self.cli("is", "ac", "x", "--kademe", "orta")
        self.assertNotEqual(r.returncode, 0)


class EdelAyari(unittest.TestCase):
    def test_her_kapi_her_kademeyi_tanimlar_ve_kontroller_bilinir(self):
        a = MK.ayar()
        self.assertEqual(a["mod"], "golge")
        for no in ("1", "2", "3"):
            tanim = a["kapilar"][no]
            for k in S.KADEMELER:
                self.assertTrue(tanim[k], f"kapı {no} {k} boş")
                for ad in tanim[k]:
                    self.assertIn(ad, MK.KONTROLLER, f"kapı {no} {k}: {ad}")
        esik = a["eval_min_kosu"]
        self.assertLess(esik["hafif"], esik["standart"])
        self.assertLess(esik["standart"], esik["kritik"])

    def test_kritik_standarttan_genis(self):
        a = MK.ayar()
        for no in ("1", "2", "3"):
            self.assertTrue(set(a["kapilar"][no]["standart"]) <= set(a["kapilar"][no]["kritik"]))


if __name__ == "__main__":
    unittest.main()
