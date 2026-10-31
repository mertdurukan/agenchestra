"""Kilit zaman aşımı ölçümü (kilit_olcum.py).

`python -m pytest plugins/orkestra/tests/test_kilit_olcum.py`
"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

AD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AD, "..", "scripts"))
import kilit_olcum  # noqa: E402


class KilitOlcumTest(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.sd = self.t.name

    def yaz(self, ad, satirlar):
        with open(os.path.join(self.sd, ad), "w", encoding="utf-8") as f:
            f.write("\n".join(satirlar) + "\n")

    def test_sayim_surec_gun_ortalama(self):
        self.yaz("a.json.zaman_asimi.log", [
            "2026-10-22T10:00:00 kilit_zaman_asimi pid=1 surec=hook.py bekleme_ms=1000",
            "2026-10-22T11:00:00 kilit_zaman_asimi pid=2 surec=panel.py bekleme_ms=3000",
            "2026-10-23T11:00:00 kilit_zaman_asimi pid=3 surec=hook.py bekleme_ms=2000",
            "bozuk satir",
        ])
        self.yaz("b.jsonl.zaman_asimi.log", ["2026-10-23T12:00:00 kilit_zaman_asimi pid=4 surec=x bekleme_ms=500"])
        self.yaz("baska.log", ["yok sayilir"])
        v = kilit_olcum.olc(self.sd)
        self.assertEqual(set(v), {"a.json", "b.jsonl"})
        a = v["a.json"]
        self.assertEqual(a["kayit"], 4)
        self.assertEqual(a["ayrisamayan"], 1)
        self.assertEqual(a["surec"], {"hook.py": 2, "panel.py": 1})
        self.assertEqual(a["gun"], {"2026-10-22": 2, "2026-10-23": 1})
        self.assertEqual(a["ort_bekleme_ms"], 2000.0)
        self.assertEqual(a["en_uzun_bekleme_ms"], 3000)

    def test_json_ve_tablo_cikti(self):
        self.yaz("a.json.zaman_asimi.log", ["2026-10-22T10:00:00 kilit_zaman_asimi pid=1 surec=hook.py bekleme_ms=10"])
        tampon = io.StringIO()
        with redirect_stdout(tampon):
            self.assertEqual(kilit_olcum.main(["--sd", self.sd, "--json"]), 0)
        self.assertEqual(json.loads(tampon.getvalue())["a.json"]["kayit"], 1)
        tampon = io.StringIO()
        with redirect_stdout(tampon):
            kilit_olcum.main(["--sd", self.sd])
        self.assertIn("hook.py=1", tampon.getvalue())

    def test_bos_ve_olmayan_dizin(self):
        self.assertEqual(kilit_olcum.olc(self.sd), {})
        self.assertEqual(kilit_olcum.main(["--sd", os.path.join(self.sd, "yok")]), 2)


    def test_kapi_golge_gunluktan_sayilir(self):
        with open(os.path.join(self.sd, "gunluk.jsonl"), "w", encoding="utf-8") as f:
            for k in ("test_yonlendirme", "test_yonlendirme", "baska"):
                f.write(json.dumps({"tur": "kapi_golge", "kapi": k}) + "\n")
            f.write(json.dumps({"tur": "istek"}) + "\n")
        self.assertEqual(kilit_olcum.kapi_golge(self.sd), {"test_yonlendirme": 2, "baska": 1})


if __name__ == "__main__":
    unittest.main()
