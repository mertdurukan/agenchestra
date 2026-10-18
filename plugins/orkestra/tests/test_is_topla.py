"""041 P1: `orkestra is topla <id>` — işin onaylı kartlarını teslim eder, todo durumunu ve anomali özetini basar."""
import json
import os
import unittest

import test_cekirdek as TC

ANA = {"ajan_id": "ana", "ajan_tipi": "ana"}
ISCI = {"ajan_id": "w1", "ajan_tipi": "orkestra:isci-t1"}
DENETCI = {"ajan_id": "d1", "ajan_tipi": "orkestra:denetci"}


class IsTopla(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown
    cli = TC.Cekirdek.cli
    kart = TC.Cekirdek.kart

    def ok(self, *args, **kim):
        r = self.cli(*args, **kim)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def is_ac(self, ad="001-deneme"):
        klasor = os.path.join(self.proje, "isler", ad)
        r = self.ok("is", "ac", "Deneme işi " + ad, "--klasor", klasor)
        i = r.stdout.split()[0]
        with open(os.path.join(klasor, "todo.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("# T\n\n- [ ] birinci madde\n- [ ] ikinci madde\n")
        return i

    def onayli(self, is_id, madde=None):
        ek = ["--is", is_id] + (["--madde", madde] if madde else [])
        g = self.kart(*ek)
        self.ok("kart", "durum", g, "is-bitti", "--ozet", "eklendi", "--cikti", "docs/a.md", **ISCI)
        self.ok("kart", "denetim", g, "--karar", "onay", "--gerekce", "k1 tamam", **DENETCI)
        return g

    def oku(self, g):
        with open(os.path.join(self.sd, "gorevler", f"{g}.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_onayli_kartlari_teslim_eder_todo_ve_anomali_basar(self):
        i = self.is_ac()
        a = self.onayli(i, madde="birinci madde")
        b = self.onayli(i)
        r = self.cli("is", "topla", i, "--ozet", "tamam", **ANA)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"{a} → teslim", r.stdout)
        self.assertIn(f"{b} → teslim", r.stdout)
        self.assertEqual(self.oku(a)["durum"], "teslim")
        self.assertEqual(self.oku(b)["teslim_ozeti"], "tamam")
        self.assertIn(f"{i} todo 1/2", r.stdout)  # kartın madde alanı teslimde [x] yapıldı
        self.assertIn("Maliyet anomalisi yok", r.stdout)

    def test_baska_isin_karti_ve_onaysiz_kart_teslim_edilmez(self):
        i = self.is_ac()
        diger = self.onayli(self.is_ac("002-baska"))  # başka işe bağlı onaylı kart
        denetimde = self.kart("--is", i)
        self.ok("kart", "durum", denetimde, "is-bitti", "--ozet", "eklendi", "--cikti", "docs/a.md", **ISCI)
        r = self.cli("is", "topla", i, **ANA)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("teslim edilecek onaylı kart yok", r.stdout)
        self.assertIn(f"bekleyen: {denetimde} [denetimde]", r.stdout)
        self.assertEqual(self.oku(diger)["durum"], "onaylandi")

    def test_ozet_json_dosyasindan_gelir_varsayilan_kart_basligi(self):
        i = self.is_ac()
        a, b = self.onayli(i), self.onayli(i)
        yol = os.path.join(self.proje, "ozet.json")
        with open(yol, "w", encoding="utf-8") as f:
            json.dump([{"id": a, "ozet": "birinci özel"}], f)
        self.assertEqual(self.cli("is", "topla", i, "--json-dosya", yol, **ANA).returncode, 0)
        self.assertEqual(self.oku(a)["teslim_ozeti"], "birinci özel")
        self.assertEqual(self.oku(b)["teslim_ozeti"], "README satırı")

    def test_yalniz_ana_ajan_ve_var_olan_is(self):
        i = self.is_ac()
        self.assertEqual(self.cli("is", "topla", i, **ISCI).returncode, 3)
        self.assertNotEqual(self.cli("is", "topla", "I-404", **ANA).returncode, 0)


class SkillBoyutu(unittest.TestCase):
    """041 P1 bitiş ölçütü: SKILL.md en çok 60 satır; ayrıntı ayrı dosyada; `is topla` skill'de anılır."""
    KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def test_skill_60_satir_ayrinti_var_topla_anilir(self):
        with open(os.path.join(self.KOK, "skills", "is", "SKILL.md"), encoding="utf-8") as f:
            satirlar = f.read().splitlines()
        self.assertLessEqual(len(satirlar), 60, len(satirlar))
        self.assertIn("orkestra is topla", " ".join(satirlar))
        self.assertTrue(os.path.isfile(os.path.join(self.KOK, "skills", "is", "ayrinti.md")))


if __name__ == "__main__":
    unittest.main()
