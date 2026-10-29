"""Perspektif günlük özeti (ADR-0094): sentetik günlükle sayımlar.
`py -3.13 -m pytest plugins/orkestra/tests/test_perspektif_gunluk.py`
Hepsi geçici klasörde koşar; gerçek durum dizinine dokunulmaz.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import perspektif_gunluk as PG  # noqa: E402

Z = "2026-10-20T10:00:00+03:00"
ESKI = "2026-01-01T10:00:00+03:00"


class GunlukOzeti(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_pgunluk_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "gorevler"))
        self.addCleanup(shutil.rmtree, self.proje, True)

    def yaz(self, ad, kayitlar):
        with open(os.path.join(self.sd, ad), "a", encoding="utf-8") as f:
            for r in kayitlar:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def ozet(self):
        return PG.ozet(self.sd, "2026-10-01T00:00:00+03:00", "2026-10-31T00:00:00+03:00")

    def test_kapi_ve_kural_sayimlari(self):
        self.yaz("gunluk.jsonl", [
            {"zaman": Z, "tur": "kapi_golge", "kapi": "sozlesme", "is": "A"},
            {"zaman": Z, "tur": "kapi_golge", "kapi": "sozlesme", "is": "B"},
            {"zaman": Z, "tur": "kapi_ret", "kapi": "uretim_noktasi", "is": "A", "neden": "x" * 100},
            {"zaman": Z, "tur": "kural_ihlal", "kural": "belge_bicim", "mod": "golge"},
            {"zaman": Z, "tur": "kural_ihlal", "kural": "belge_bicim", "mod": "ihlal"},
            {"zaman": Z, "tur": "hook-hatasi"}, {"zaman": Z, "tur": "sikistirma"},
            {"zaman": ESKI, "tur": "kapi_golge", "kapi": "pencere_disi"},
        ])
        o = self.ozet()
        self.assertEqual(o["kapi_golge"], {"sozlesme": 2})
        self.assertEqual(o["kapi_ret"], {"uretim_noktasi": 1})
        self.assertEqual(len(o["ret_nedenleri"][0]["neden"]), 60)
        self.assertEqual(o["kural_ihlal"], {"belge_bicim": 2})
        self.assertEqual(o["kural_ihlal_mod"], {"golge": 1, "ihlal": 1})
        self.assertEqual((o["hook_hatasi"], o["sikistirma"]), (1, 1))

    def test_tekrarlayan_ret_uc_ve_ustu(self):
        self.yaz("gunluk.jsonl", [{"zaman": Z, "tur": "kapi_ret", "kapi": "k", "is": "A", "neden": "n"}] * 3
                 + [{"zaman": Z, "tur": "kapi_ret", "kapi": "k", "is": "B", "neden": "n"}])
        t = self.ozet()["tekrarlayan_ret"]
        self.assertEqual((t["cift"], t["uc_ve_ustu"], t["pay"]), (2, 1, 0.5))

    def test_tekrarlayan_ret_bir_iki_vakasi(self):
        self.yaz("gunluk.jsonl", [{"zaman": Z, "tur": "kapi_ret", "kapi": "k", "is": "A", "neden": "n"}] * 2
                 + [{"zaman": Z, "tur": "kapi_ret", "kapi": "k", "is": "B", "neden": "n"}])
        t = self.ozet()["tekrarlayan_ret"]
        self.assertEqual((t["uc_ve_ustu"], t["pay"]), (0, 0.0))

    def test_kullanilmayan_skill(self):
        for ad in ("kullanilan", "bos"):
            d = os.path.join(self.proje, ".claude", "skills", ad)
            os.makedirs(d)
            open(os.path.join(d, "SKILL.md"), "w").close()
        self.yaz("gunluk.jsonl", [{"zaman": Z, "tur": "skill", "skill": "eklenti:kullanilan"}])
        self.assertIn("bos", self.ozet()["kullanilmayan_skill"])
        self.assertNotIn("kullanilan", self.ozet()["kullanilmayan_skill"])

    def test_yukseltilen_kart(self):
        def kart(ad, olay, z):
            with open(os.path.join(self.sd, "gorevler", ad), "w", encoding="utf-8") as f:
                json.dump({"gecmis": [{"zaman": z, "olay": olay}]}, f)
        kart("G-001.json", "yukseltme", Z)
        kart("G-002.json", "yukseltme", ESKI)
        kart("G-003.json", "teslim", Z)
        self.assertEqual(self.ozet()["yukseltilen_kart"], 1)

    def test_denetim_payi_ve_cikti_olcum(self):
        self.yaz("maliyet.jsonl", [{"zaman": Z, "surec": "denetim", "maliyet_usd": 1.0},
                                   {"zaman": Z, "surec": "is", "maliyet_usd": 3.0}])
        self.yaz("gunluk.jsonl", [{"zaman": Z, "tur": "cikti_olcum", "toplam": t, "kapanis": k}
                                  for t, k in ((100, None), (200, 150), (300, None), (400, 350))])
        o = self.ozet()
        self.assertEqual(o["denetim_payi"], 0.25)
        self.assertEqual((o["cikti_olcum"]["adet"], o["cikti_olcum"]["kapanis_orani"]), (4, 0.5))

    def test_hata_ve_atif_ve_bos_dizin(self):
        self.yaz("hata.jsonl", [{"zaman": Z, "sinif": "davranis", "kok": {"kaynak": "kural"}}] * 2)
        self.yaz("atif.jsonl", [{"zaman": Z, "kaynak": "cli"}])
        o = self.ozet()
        self.assertEqual(o["hata"], {"sinif": {"davranis": 2}, "kok": {"kural": 2}})
        self.assertEqual(o["atif"], {"cli": 1})
        bos = PG.ozet(os.path.join(self.proje, "yok"), None, None)
        self.assertEqual((bos["denetim_payi"], bos["kapi_ret"]), (0.0, {}))


if __name__ == "__main__":
    unittest.main()
