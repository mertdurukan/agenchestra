"""ADR-0092 K6: `denetim_politika.py tablo --kesim` T3/T4 kartları denetci.baslangic öncesi/sonrası ayrı gruplar;
`karar()` örnekleme grupları (grup_tablosu) değişmez."""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import denetim_politika as D  # noqa: E402


def kart(i, zaman, ilk, basamak="T3", sinif="kod"):
    return {"id": f"G-{i:03d}", "sinif": sinif, "basamak": basamak, "denetimler": [{"karar": ilk, "zaman": zaman}]}


KARTLAR = [kart(1, "2026-10-20T10:00:00+03:00", "ret"), kart(2, "2026-10-21T10:00:00+03:00", "onay"),
           kart(3, "2026-10-30T10:00:00+03:00", "onay"), kart(4, "2026-10-31T10:00:00+03:00", "onay"),
           kart(5, "2026-10-31T10:00:00+03:00", "ret", basamak="T2")]


class KesimTest(unittest.TestCase):
    def test_kesim_iki_grup_t2_haric(self):
        t = D.kesim_tablosu(KARTLAR, D.ayar_yukle(), "2026-10-29")
        self.assertEqual(set(t), {"kod|T3|oncesi", "kod|T3|sonrasi"})
        self.assertEqual((t["kod|T3|oncesi"]["n"], t["kod|T3|oncesi"]["ilk_ret"]), (2, 1))
        self.assertEqual((t["kod|T3|sonrasi"]["n"], t["kod|T3|sonrasi"]["ilk_ret"]), (2, 0))

    def test_karar_gruplari_degismez(self):
        cfg = D.ayar_yukle()
        once = D.grup_tablosu(KARTLAR, cfg)
        D.kesim_tablosu(KARTLAR, cfg, "2026-10-29")
        self.assertEqual(D.grup_tablosu(KARTLAR, cfg), once)
        self.assertEqual(set(once), {"kod|T3", "kod|T2"})

    def test_cli_kesim_bayragi(self):
        with tempfile.TemporaryDirectory() as sd:
            os.makedirs(os.path.join(sd, "gorevler"))
            for k in KARTLAR:
                with open(os.path.join(sd, "gorevler", k["id"] + ".json"), "w", encoding="utf-8") as f:
                    json.dump(k, f)
            cikti = io.StringIO()
            with redirect_stdout(cikti):
                self.assertEqual(D.main(["tablo", "--sd", sd, "--json", "--kesim"]), 0)
            j = json.loads(cikti.getvalue())
            self.assertIn("kesim", j)
            self.assertIn("kod|T3|sonrasi", j["kesim"])
            cikti = io.StringIO()
            with redirect_stdout(cikti):
                D.main(["tablo", "--sd", sd, "--json"])
            self.assertNotIn("kesim", json.loads(cikti.getvalue()))

    def test_baslangic_yoksa_kesim_yok(self):
        with mock.patch.object(D, "denetci_baslangic", return_value=None):
            with tempfile.TemporaryDirectory() as sd:
                os.makedirs(os.path.join(sd, "gorevler"))
                cikti = io.StringIO()
                with redirect_stdout(cikti):
                    D.main(["tablo", "--sd", sd, "--json", "--kesim"])
                self.assertNotIn("kesim", json.loads(cikti.getvalue()))


if __name__ == "__main__":
    unittest.main()
