"""İş şeridi 2b (G-027): teslim kartla eşleşen açık maddenin gizlenmemesi, G2a tipi adım
belirteci ve düz çıktıda adım tekrarının kırpılması."""
import json
import os
import shutil
import sys
import tempfile
import unittest

import test_cekirdek as TC

sys.path.insert(0, os.path.join(TC.KOK, "scripts"))
import is_kaydi as IK  # noqa: E402


class AdimBelirteci(unittest.TestCase):
    # kriter 3
    def test_adim_coz_kucuk_harf_son_ek(self):
        self.assertEqual(IK.adim_coz("PE-636 G2b: x"), "G2b")
        self.assertEqual(IK.adim_coz("G2a ajanda outcome"), "G2a")
        self.assertEqual(IK.adim_coz("G2: yalın"), "G2")

    def test_adim_coz_korunanlar(self):
        self.assertIsNone(IK.adim_coz("G-015 kart kimliği"))
        self.assertEqual(IK.adim_coz("PE-636: G7-G9 paralel"), "G7-G9")
        self.assertEqual(IK.adim_coz("PE-636 G7-A1: x"), "G7-A1")
        self.assertEqual(IK.adim_coz("PE-636 G8-B1/B2: x"), "G8-B1/B2")

    def test_adim_coz_gecersiz_son_ek(self):
        self.assertIsNone(IK.adim_coz("G2ab iki harf"))
        self.assertIsNone(IK.adim_coz("G2A büyük harf"))
        self.assertIsNone(IK.adim_coz("Genel G2a: ortada"))

    def test_todo_maddeleri_g2a_g2b(self):
        d = tempfile.mkdtemp(prefix="ork_duz_")
        try:
            with open(os.path.join(d, "TODO.md"), "w", encoding="utf-8", newline="\n") as f:
                f.write("- [ ] G2a ajanda outcome bağla\n- [ ] **G2b ilk tur**\n"
                        "- [ ] G-015 kart kimliği\n- [ ] G7-G9 paralel\n- [ ] G2ab geçersiz\n")
            m = IK.todo_maddeleri(d)
            self.assertEqual([x["adimlar"] for x in m],
                             [["G2a"], ["G2b"], [], ["G7-G9"], []])
        finally:
            shutil.rmtree(d, ignore_errors=True)


class SeritDuzelt(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown
    cli = TC.Cekirdek.cli

    def kart_yaz(self, gid, **alan):
        k = {"id": gid, "baslik": f"kart {gid}", "basamak": "T1", "durum": "planlandi",
             "bagimliliklar": []}
        k.update(alan)
        d = os.path.join(self.sd, "gorevler")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"{gid}.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(k, f, ensure_ascii=False, indent=2)

    def kur(self, todo):
        klasor = os.path.join(self.proje, "RNV", "05_x", "001-y")
        r = self.cli("is", "ac", "Deneme işi", "--klasor", klasor)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.is_id = r.stdout.strip().splitlines()[-1].split()[0]
        with open(os.path.join(klasor, "TODO.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(todo)

    def kart(self, gid, adim, durum, **ek):
        self.kart_yaz(gid, **{"is": self.is_id, "adim": adim, "durum": durum, **ek})

    def serit(self):
        return IK.is_serit(self.sd, self.is_id)

    def metinler(self, s, kova):
        return [o["metin"] for o in s[kova] if o["tur"] == "madde"]

    # kriter 1
    def test_acik_madde_yalniz_teslim_kartla_gorunur(self):
        self.kur("- [ ] G4 kalanlar: zamanlanmış görev\n")
        self.kart("G-001", "G4", "teslim", teslim_ozeti="G4 teslim")
        self.kart("G-002", "G4", "teslim", teslim_ozeti="G4 ikinci")
        s = self.serit()
        self.assertEqual(self.metinler(s, "planda_kart_yok"), ["G4 kalanlar: zamanlanmış görev"])
        self.assertEqual([o["kart"] for o in s["yapildi"] if o["tur"] == "kart"], ["G-001", "G-002"])

    def test_acik_madde_bitmemis_kartla_gizlenir(self):
        for durum in ("isleniyor", "planlandi", "denetimde", "onaylandi", "beklemede", "reddedildi"):
            with self.subTest(durum=durum):
                self.tearDown()
                self.setUp()
                self.kur("- [ ] G4 kalanlar\n")
                self.kart("G-001", "G4", "teslim")
                self.kart("G-002", "G4", durum)
                s = self.serit()
                for k in ("yapildi", "simdi", "sirada", "planda_kart_yok", "iptal"):
                    self.assertEqual(self.metinler(s, k), [], k)

    def test_acik_madde_teslim_ve_iptal_kartla_gorunur(self):
        self.kur("- [ ] G4 kalanlar\n")
        self.kart("G-001", "G4", "teslim")
        self.kart("G-002", "G4", "iptal")
        self.assertEqual(self.metinler(self.serit(), "planda_kart_yok"), ["G4 kalanlar"])

    def test_acik_madde_yalniz_iptal_kartla_gorunur(self):
        self.kur("- [ ] G4 kalanlar\n")
        self.kart("G-001", "G4", "iptal")
        self.assertEqual(self.metinler(self.serit(), "planda_kart_yok"), ["G4 kalanlar"])

    def test_suren_madde_yalniz_teslim_kartla_simdide(self):
        self.kur("- [~] G4 süren iş\n")
        self.kart("G-001", "G4", "teslim")
        s = self.serit()
        self.assertEqual(self.metinler(s, "simdi"), ["G4 süren iş"])
        self.assertEqual(self.metinler(s, "planda_kart_yok"), [])

    def test_suren_madde_bitmemis_kartla_gizlenir(self):
        self.kur("- [~] G4 süren iş\n")
        self.kart("G-001", "G4", "teslim")
        self.kart("G-002", "G4", "isleniyor")
        self.assertEqual(self.metinler(self.serit(), "simdi"), [])

    def test_onek_eslesmesi_teslim_kartla_yine_gorunur(self):
        self.kur("- [ ] G4 geri kalan\n")
        self.kart("G-001", "G4-A1", "teslim")
        self.assertEqual(self.metinler(self.serit(), "planda_kart_yok"), ["G4 geri kalan"])

    def test_g70_g7_eslesmez_korunur(self):
        self.kur("- [ ] G70 başka\n")
        self.kart("G-001", "G7", "planlandi")
        self.assertEqual(self.metinler(self.serit(), "planda_kart_yok"), ["G70 başka"])

    def test_g2a_g2b_birbiriyle_eslesmez(self):
        self.kur("- [ ] G2a madde\n")
        self.kart("G-001", "G2b", "planlandi")
        self.assertEqual(self.metinler(self.serit(), "planda_kart_yok"), ["G2a madde"])

    def test_g2a_madde_g2a_kartla_gizlenir(self):
        self.kur("- [ ] G2a madde\n")
        self.kart("G-001", IK.adim_coz("PE-636 G2a: x"), "isleniyor")
        self.assertEqual(self.metinler(self.serit(), "planda_kart_yok"), [])

    # kriter 2
    def test_bitmis_madde_teslim_kartla_gizlenir(self):
        self.kur("- [x] G4 bitti\n")
        self.kart("G-001", "G4", "teslim")
        s = self.serit()
        for k in ("yapildi", "simdi", "sirada", "planda_kart_yok", "iptal"):
            self.assertEqual(self.metinler(s, k), [], k)

    def test_bitmis_madde_yalniz_iptal_kartla_listelenir(self):
        self.kur("- [x] G4 bitti\n")
        self.kart("G-001", "G4", "iptal")
        self.assertEqual(self.metinler(self.serit(), "yapildi"), ["G4 bitti"])

    def test_ilerleme_sayisi_degismez(self):
        self.kur("- [ ] G4 kalanlar\n- [x] G5 bitti\n")
        self.kart("G-001", "G4", "teslim")
        self.kart("G-002", "G5", "teslim")
        self.assertEqual(self.serit()["ilerleme"], {"biten": 1, "toplam": 2})

    # kriter 4
    def test_duz_cikti_madde_adimi_bir_kez(self):
        self.kur("- [ ] G0 Langfuse envanteri\n")
        r = self.cli("is", "serit", self.is_id)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("  G0  Langfuse envanteri", r.stdout.splitlines())
        satir = [x for x in r.stdout.splitlines() if "Langfuse envanteri" in x][0]
        self.assertEqual(satir.count("G0"), 1)

    def test_duz_cikti_iki_nokta_ve_kalin(self):
        self.kur("- [ ] G3: kalan iş\n- [ ] **G2b ilk tur**\n")
        r = self.cli("is", "serit", self.is_id)
        self.assertEqual(r.returncode, 0, r.stderr)
        satirlar = r.stdout.splitlines()
        self.assertIn("  G3  kalan iş", satirlar)
        self.assertIn("  G2b  ilk tur", satirlar)

    def test_duz_cikti_kart_adimi_bir_kez(self):
        self.kur("")
        self.kart("G-001", "G1", "isleniyor", baslik="G1 kurulum")
        r = self.cli("is", "serit", self.is_id)
        self.assertEqual(r.returncode, 0, r.stderr)
        satir = [x for x in r.stdout.splitlines() if "kurulum" in x][0]
        self.assertEqual(satir.count("G1"), 1)
        self.assertIn("  G1  kurulum", satir)
        self.assertIn("(G-001)", satir)

    def test_duz_cikti_baslamayan_metin_kirpilmaz(self):
        self.kur("- [ ] Önce G5 sonra başka\n")
        r = self.cli("is", "serit", self.is_id)
        self.assertIn("  G5  Önce G5 sonra başka", r.stdout.splitlines())

    def test_json_metin_degismez(self):
        self.kur("- [ ] G0 Langfuse envanteri\n")
        r = self.cli("is", "serit", self.is_id, "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        j = json.loads(r.stdout)
        self.assertEqual(j["planda_kart_yok"][0]["metin"], "G0 Langfuse envanteri")
        self.assertEqual(j["planda_kart_yok"][0]["adimlar"], ["G0"])


if __name__ == "__main__":
    unittest.main()
