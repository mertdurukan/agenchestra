"""Görev türü kataloğu (ADR-0092): şema, varsayılan basamak, kanarya sayacı, tablo CLI, golge uyarıları."""
import copy
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import gorev_turleri as G  # noqa: E402


class KatalogTest(unittest.TestCase):
    def test_on_sekiz_tur_ve_kanarya(self):
        k = G.yukle()
        self.assertEqual(len(k["turler"]), 18)
        self.assertEqual(k["mod"], "ihlal")  # ADR-0096
        self.assertEqual((k["kanarya"]["min_n"], k["kanarya"]["marj"], k["kanarya"]["guven"]), (60, 0.10, 0.95))
        for ad, t in k["turler"].items():
            self.assertIn(t["varsayilan"], (None, "T0", "T1", "T2", "T3", "T4"), ad)
            self.assertNotEqual(t["varsayilan"], "T1", f"{ad}: T1 varsayılan olamaz (kanarya sonrası)")

    def test_varsayilan_basamak(self):
        self.assertEqual(G.varsayilan_basamak("kod"), "T2")
        self.assertEqual(G.varsayilan_basamak("Arastirma"), "T2")
        self.assertIsNone(G.varsayilan_basamak("yok-boyle-sinif"))
        self.assertIsNone(G.varsayilan_basamak(None))
        self.assertTrue(G.tur_var_mi("kod"))
        self.assertFalse(G.tur_var_mi("yok-boyle-sinif"))

    def test_sinif_tek_turde(self):
        goruldu = {}
        for ad, t in G.yukle()["turler"].items():
            for s in t["sinif"]:
                self.assertNotIn(s, goruldu, f"{s} hem {goruldu.get(s)} hem {ad} türünde")
                goruldu[s] = ad


class TabloTest(unittest.TestCase):
    def _sd(self, kartlar):
        sd = tempfile.mkdtemp()
        os.makedirs(os.path.join(sd, "gorevler"))
        for i, k in enumerate(kartlar):
            k.setdefault("id", f"G-{i + 1:03d}")
            with open(os.path.join(sd, "gorevler", k["id"] + ".json"), "w", encoding="utf-8") as f:
                json.dump(k, f)
        return sd

    def test_aday_sayaci_ve_kalan(self):
        sd = self._sd([{"sinif": "kod", "basamak": "T2", "baslangic_basamak": "T1"},
                       {"sinif": "kod", "basamak": "T1"},
                       {"sinif": "kod", "basamak": "T2"}])
        satir = {r["tur"]: r for r in G.tablo(sd)}
        self.assertEqual(len(satir), 18)
        self.assertEqual((satir["kod"]["n"], satir["kod"]["kalan"], satir["kod"]["min_n"]), (2, 58, 60))
        self.assertIsNone(satir["belge"]["kalan"])

    def test_cli_n_60_yazar_ve_kanarya_yoksa_hata(self):
        sd = self._sd([])
        cikti = io.StringIO()
        with redirect_stdout(cikti):
            self.assertEqual(G.main(["tablo", "--sd", sd]), 0)
        satirlar = cikti.getvalue().strip().splitlines()
        self.assertEqual(len(satirlar), 18)
        self.assertTrue(all("/60" in s for s in satirlar))
        kat = copy.deepcopy(G.yukle())
        del kat["kanarya"]
        with mock.patch.object(G, "yukle", return_value=kat), redirect_stderr(io.StringIO()):
            self.assertNotEqual(G.main(["tablo", "--sd", sd]), 0)


class KapiTest(unittest.TestCase):
    def test_eksikler(self):
        self.assertEqual(G.kapi_eksikleri("kod", "T2", None), [])
        self.assertIn("kataloğunda yok", G.kapi_eksikleri("yok-boyle", "T2", None)[0])
        self.assertIn("yüksek", G.kapi_eksikleri("kod", "T3", "K2: iki ret")[0])
        self.assertTrue(any("basamak_neden" in e for e in G.kapi_eksikleri("kod", "T3", None)))
        self.assertEqual(G.kapi_eksikleri("kod", "T1", None), [])

    def test_env_kapatir(self):
        with mock.patch.dict(os.environ, {"ORKESTRA_GOREV_TURU_KAPISI": "0"}):
            self.assertEqual(G.kapi_eksikleri("yok-boyle", "T4", None), [])


if __name__ == "__main__":
    unittest.main()
