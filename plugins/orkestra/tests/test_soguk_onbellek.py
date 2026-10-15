"""Soğuk önbellek kapısı: `python -m unittest plugins/orkestra/tests/test_soguk_onbellek.py`"""
import datetime as D
import json
import os
import shutil
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import soguk_onbellek as S  # noqa: E402

SIMDI = D.datetime(2026, 10, 15, 12, 0, tzinfo=D.timezone.utc)


def asistan(dk_once: float, baglam: int, yan=False):
    z = (SIMDI - D.timedelta(minutes=dk_once)).isoformat().replace("+00:00", "Z")
    return {"type": "assistant", "isSidechain": yan, "timestamp": z,
            "message": {"model": "claude-opus-5-5", "usage": {"input_tokens": 10, "cache_read_input_tokens": baglam - 10,
                                                             "cache_creation_input_tokens": 0}}}


class SogukOnbellek(unittest.TestCase):
    def setUp(self):
        self.sd = tempfile.mkdtemp()
        self.tp = os.path.join(self.sd, "t.jsonl")

    def tearDown(self):
        shutil.rmtree(self.sd, ignore_errors=True)

    def yaz(self, *satirlar):
        with open(self.tp, "w", encoding="utf-8") as f:
            for s in satirlar:
                f.write(json.dumps(s) + "\n")

    def test_buyuk_baglam_uzun_ara_bir_kez_durdurur_sonra_gecer(self):
        self.yaz(asistan(90, 300_000))
        n = S.karar(self.sd, "o1", self.tp, SIMDI)
        self.assertIsNotNone(n)
        self.assertIn("300k", n)
        self.assertIn("USD", n)
        self.assertIn("orkestra is devam", n)
        self.assertIsNone(S.karar(self.sd, "o1", self.tp, SIMDI + D.timedelta(minutes=2)))  # bilerek sürdürüyor
        self.assertIsNotNone(S.karar(self.sd, "o1", self.tp, SIMDI + D.timedelta(minutes=3)))  # işaret tüketildi

    def test_kisa_ara_ya_da_kucuk_baglam_gecer(self):
        self.yaz(asistan(30, 300_000))
        self.assertIsNone(S.karar(self.sd, "o1", self.tp, SIMDI))
        self.yaz(asistan(120, 50_000))
        self.assertIsNone(S.karar(self.sd, "o1", self.tp, SIMDI))

    def test_yan_zincir_sayilmaz_ana_zincirin_son_cagrisi_esas(self):
        self.yaz(asistan(90, 300_000), asistan(1, 300_000, yan=True))
        self.assertIsNotNone(S.karar(self.sd, "o1", self.tp, SIMDI))

    def test_proje_ezmesi_kapatir_ve_esik_degistirir(self):
        self.yaz(asistan(90, 300_000))
        with open(os.path.join(self.sd, "onbellek_kapisi.json"), "w", encoding="utf-8") as f:
            json.dump({"acik": False}, f)
        self.assertIsNone(S.karar(self.sd, "o1", self.tp, SIMDI))
        with open(os.path.join(self.sd, "onbellek_kapisi.json"), "w", encoding="utf-8") as f:
            json.dump({"esik_token": 400_000}, f)
        self.assertIsNone(S.karar(self.sd, "o1", self.tp, SIMDI))

    def test_transkript_yok_ya_da_bozuk_gecer(self):
        self.assertIsNone(S.karar(self.sd, "o1", None, SIMDI))
        with open(self.tp, "w", encoding="utf-8") as f:
            f.write("bozuk\n{\n")
        self.assertIsNone(S.karar(self.sd, "o1", self.tp, SIMDI))


if __name__ == "__main__":
    unittest.main()
