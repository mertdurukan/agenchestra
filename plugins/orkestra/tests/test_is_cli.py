"""`orkestra is ...` CLI'si ve kartın oturumun işine bağlanması (T-02/T-03). Geçici proje dizininde koşar."""
import json
import os
import unittest

import test_cekirdek as TC


class IsCli(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown
    cli = TC.Cekirdek.cli
    kart = TC.Cekirdek.kart

    def ac(self, baslik="Deneme işi", alt="is1"):
        klasor = os.path.join(self.proje, alt)
        r = self.cli("is", "ac", baslik, "--klasor", klasor, "--etiket", "x")
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip(), klasor

    def oku(self, yol):
        with open(yol, encoding="utf-8") as f:
            return json.load(f)

    def oturum_yolu(self):
        return os.path.join(self.sd, "oturumlar", TC.OTURUM + ".json")

    def kart_json(self, g):
        return self.oku(os.path.join(self.sd, "gorevler", f"{g}.json"))

    def test_ac_aktif_liste(self):
        self.assertIn("bağlı iş yok", self.cli("is", "aktif").stdout)
        i, klasor = self.ac()
        self.assertEqual(i, "I-001")
        for ad in ("plan.md", "todo.md", "oturumlar.md", "is.json"):
            self.assertTrue(os.path.exists(os.path.join(klasor, ad)), ad)
        self.assertIn("I-001", self.cli("is", "aktif").stdout)
        self.assertEqual(self.oku(self.oturum_yolu())["is"], "I-001")
        self.assertEqual(self.oku(os.path.join(klasor, "is.json"))["oturumlar"][0]["oturum"], TC.OTURUM)
        liste = self.cli("is", "liste").stdout
        self.assertIn("I-001", liste)
        self.assertIn("Deneme işi", liste)
        self.assertIn("0/0", liste)

    def test_liste_sayisal_siralama_ve_durum_suzgeci(self):
        for n in range(1, 4):
            self.ac(f"iş {n}", f"k{n}")
        self.assertEqual(self.cli("is", "kapat", "I-002").returncode, 0)
        satirlar = [s.split("\t")[0] for s in self.cli("is", "liste", "--durum", "hepsi").stdout.splitlines()[1:]]
        self.assertEqual(satirlar, ["I-001", "I-002", "I-003"])
        acik = [s.split("\t")[0] for s in self.cli("is", "liste").stdout.splitlines()[1:]]
        self.assertEqual(acik, ["I-001", "I-003"])
        kapali = self.cli("is", "liste", "--durum", "kapandi").stdout
        self.assertIn("I-002", kapali)
        self.assertNotIn("I-001", kapali)

    def test_devam_baglar_ve_eski_anahtarlari_korur(self):
        i, klasor = self.ac()
        with open(os.path.join(klasor, "todo.md"), "w", encoding="utf-8") as f:
            f.write("# t\n- [x] bitti\n- [ ] açık madde\n")
        with open(os.path.join(klasor, "oturumlar.md"), "a", encoding="utf-8") as f:
            f.write("- 2026-10-13 ilk oturum\n")
        yol = self.oturum_yolu()
        with open(yol, "w", encoding="utf-8") as f:
            json.dump({"ofset": 42, "gorev": "G-9", "surec": "is", "ajan": "x"}, f)
        r = self.cli("is", "devam", i)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("plan.md", r.stdout)
        self.assertIn("1/2", r.stdout)
        self.assertIn("açık madde", r.stdout)
        self.assertIn("ilk oturum", r.stdout)
        o = self.oku(yol)
        self.assertEqual((o["ofset"], o["gorev"], o["surec"], o["ajan"]), (42, "G-9", "is", "x"))
        self.assertEqual(o["is"], i)
        self.assertIn("is_baglanma", o)
        self.assertEqual([g["is"] for g in o["is_gecmis"]], [i])
        self.cli("is", "devam", i)
        self.assertEqual(len(self.oku(yol)["is_gecmis"]), 2)
        self.assertEqual(len(self.oku(os.path.join(klasor, "is.json"))["oturumlar"]), 1)
        self.assertIn("1/2", self.cli("is", "todo", i).stdout)

    def test_hook_oturum_dosyasini_ezerse_aktif_yine_bulunur(self):
        i, _ = self.ac()
        with open(self.oturum_yolu(), "w", encoding="utf-8") as f:
            json.dump({"ofset": 1}, f)  # Stop hook'unun yaptığı gibi
        self.assertIn(i, self.cli("is", "aktif").stdout)

    def test_gecersiz_is_hata(self):
        self.assertNotEqual(self.cli("is", "devam", "I-999").returncode, 0)
        self.assertNotEqual(self.cli("is", "kapat", "uydurma").returncode, 0)

    def test_aktif_is_varken_kartta_is_alani_ve_kartlar(self):
        i, klasor = self.ac()
        g = self.kart()
        self.assertEqual(self.kart_json(g)["is"], i)
        self.assertEqual(self.oku(os.path.join(klasor, "is.json"))["kartlar"], [g])
        self.assertIn("1", self.cli("is", "liste").stdout.splitlines()[1].split("\t")[4])

    def test_toplu_kartlar_ise_baglanir(self):
        i, klasor = self.ac()
        plan = os.path.join(self.proje, "plan.json")
        with open(plan, "w", encoding="utf-8") as f:
            json.dump([{"baslik": "a", "kabul_kriterleri": ["k"]}, {"baslik": "b", "kabul_kriterleri": ["k"]}], f)
        r = self.cli("kart", "toplu", plan)
        self.assertEqual(r.returncode, 0, r.stderr)
        ids = [x["id"] for x in json.loads(r.stdout)]
        self.assertEqual(self.oku(os.path.join(klasor, "is.json"))["kartlar"], ids)
        self.assertTrue(all(self.kart_json(g)["is"] == i for g in ids))

    def test_acik_is_secenegi_oturum_bagini_gecer(self):
        i1, k1 = self.ac("bir", "a")
        i2, k2 = self.ac("iki", "b")  # oturum artık I-002'ye bağlı
        g = self.kart("--is", i1)
        self.assertEqual(self.kart_json(g)["is"], i1)
        self.assertEqual(self.oku(os.path.join(k1, "is.json"))["kartlar"], [g])
        self.assertEqual(self.oku(os.path.join(k2, "is.json"))["kartlar"], [])

    def test_toplu_gecersiz_is_hic_kart_yazmaz(self):
        i, klasor = self.ac()
        plan = os.path.join(self.proje, "plan.json")
        with open(plan, "w", encoding="utf-8") as f:
            json.dump([{"baslik": "a", "kabul_kriterleri": ["k"]},
                       {"baslik": "b", "kabul_kriterleri": ["k"], "is": "I-777"}], f)
        gdir = os.path.join(self.sd, "gorevler")
        once = sorted(os.listdir(gdir)) if os.path.isdir(gdir) else []
        r = self.cli("kart", "toplu", plan)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(sorted(os.listdir(gdir)) if os.path.isdir(gdir) else [], once)
        self.assertEqual(self.oku(os.path.join(klasor, "is.json"))["kartlar"], [])
        g = self.kart()  # sayaç ilerlemedi
        self.assertEqual(g, "G-001")

    def test_kapali_ise_kart_baglanmaz(self):
        i, klasor = self.ac()
        self.assertEqual(self.cli("is", "kapat", i).returncode, 0)
        r = self.cli("kart", "yeni", "--baslik", "x", "--kabul", "k")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"{i} kapalı", r.stderr)
        self.assertEqual(len([s for s in r.stderr.splitlines() if "kapalı" in s]), 1)
        self.assertNotIn("is", self.kart_json(r.stdout.strip()))
        self.assertEqual(self.oku(os.path.join(klasor, "is.json"))["kartlar"], [])
        r2 = self.cli("kart", "yeni", "--baslik", "y", "--kabul", "k", "--is", i)
        self.assertNotEqual(r2.returncode, 0)
        self.assertEqual(self.oku(os.path.join(klasor, "is.json"))["kartlar"], [])

    def test_aktif_is_yokken_kart_eskisi_gibi(self):
        g = self.kart()
        k = self.kart_json(g)
        self.assertNotIn("is", k)
        self.assertFalse(os.path.exists(os.path.join(self.sd, "isler.json")))
        r = self.cli("kart", "yeni", "--baslik", "x", "--kabul", "k", "--is", "I-001")
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
