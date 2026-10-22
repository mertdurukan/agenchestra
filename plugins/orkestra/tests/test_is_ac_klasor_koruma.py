"""ADR-0037 (I-189): `is ac` klasörde başka işin is.json'unu ezmez; devralma yalnız --devral ile; reddi hata defterine düşer."""
import json
import os
import sys
import tempfile
import unittest

import test_cekirdek as TC

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import is_kaydi as IK  # noqa: E402


def _eski_is(klasor, durum="kapandi"):
    os.makedirs(klasor, exist_ok=True)
    yol = os.path.join(klasor, "is.json")
    with open(yol, "w", encoding="utf-8") as f:
        json.dump({"id": "I-009", "baslik": "eski", "durum": durum, "oturumlar": [{"oturum": "abc", "baglanma": "z"}]}, f)
    with open(yol, "rb") as f:
        return yol, f.read()


class IsAcKlasorKorumasi(unittest.TestCase):
    def test_baska_isin_kaydi_ezilmez_acik_ve_kapali(self):
        for durum in ("kapandi", "acik"):
            sd = tempfile.mkdtemp()
            yol, once = _eski_is(os.path.join(tempfile.mkdtemp(), "001-eski"), durum)
            with self.assertRaises(IK.IsKlasoruHatasi) as c:
                IK.is_ac(sd, "yeni is", os.path.dirname(yol))
            self.assertIn("alt klasör", str(c.exception))
            with open(yol, "rb") as f:
                self.assertEqual(f.read(), once)  # is.json baytları değişmedi
            self.assertFalse(os.path.exists(os.path.join(os.path.dirname(yol), "oturumlar.md")))  # yan etki yok

    def test_devral_eski_davranisi_korur(self):
        sd = tempfile.mkdtemp()
        yol, _ = _eski_is(os.path.join(tempfile.mkdtemp(), "001-eski"))
        yeni = IK.is_ac(sd, "yeni is", os.path.dirname(yol), devral=True)
        takma = json.load(open(os.path.join(sd, "isler.json"), encoding="utf-8")).get("takma")
        self.assertEqual(takma, {"I-009": yeni["id"]})
        self.assertEqual([o["oturum"] for o in yeni["oturumlar"]], ["abc"])

    def test_bos_klasor_acilir(self):
        sd = tempfile.mkdtemp()
        self.assertTrue(IK.is_ac(sd, "yeni", os.path.join(tempfile.mkdtemp(), "001-bos"))["id"])


class IsAcCli(TC.Cekirdek):
    def hata_satirlari(self):
        yol = os.path.join(self.sd, "hata.jsonl")
        if not os.path.exists(yol):
            return []
        with open(yol, encoding="utf-8") as f:
            return [json.loads(s) for s in f if s.strip()]

    def test_cli_reddeder_ve_davranis_hatasi_yazar(self):
        klasor = os.path.join(self.proje, "001-eski")
        yol, once = _eski_is(klasor)
        r = self.cli("is", "ac", "yeni", "--klasor", klasor)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("alt klasör", r.stderr)
        with open(yol, "rb") as f:
            self.assertEqual(f.read(), once)
        (s,) = self.hata_satirlari()
        self.assertEqual((s["tur"], s["sinif"], s["kok"]["kaynak"]), ("is-klasoru-yanlis", "davranis", "betik"))

    def test_cli_devral_bayragi(self):
        klasor = os.path.join(self.proje, "001-eski")
        _eski_is(klasor)
        r = self.cli("is", "ac", "yeni", "--klasor", klasor, "--devral")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.hata_satirlari(), [])
        with open(os.path.join(klasor, "is.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["baslik"], "yeni")


if __name__ == "__main__":
    unittest.main()
