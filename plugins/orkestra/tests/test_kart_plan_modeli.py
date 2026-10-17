"""I-058 P1: kartta plan_modeli ve effort alanları + eski kartları dolduran betik.
`py -3.13 -m pytest plugins/orkestra/tests/test_kart_plan_modeli.py -q -p no:cacheprovider`
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_cekirdek as C  # noqa: E402

DOLDUR = os.path.join(C.KOK, "scripts", "plan_modeli_doldur.py")


def _satir(oturum, model, usd, gorev="-"):
    return {"zaman": "2026-10-17T10:00:00+03:00", "oturum": oturum, "gorev": gorev, "ajan": "ana-ajan",
            "agent_id": None, "model": model, "maliyet_usd": usd, "kaynak": "hook"}


class PlanModeli(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_pm_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        r = C.kos([C.CLI, "baslat"], self.proje)
        self.assertEqual(r.returncode, 0, r.stderr)

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)

    def cli(self, *a):
        return C.kos([C.CLI, *a], self.proje)

    def maliyet(self, satirlar):
        with open(os.path.join(self.sd, "maliyet.jsonl"), "w", encoding="utf-8") as f:
            for s in satirlar:
                f.write(json.dumps(s) + "\n")

    def yeni(self, *ek):
        r = self.cli("kart", "yeni", "--soru", "Kısa test sorusu?", "--baslik", "pm kartı", "--girdi", "x",
                     "--kabul", "k1", "--yazma", "docs/**", "--sinif", "belge", *ek)
        return r

    def oku(self, gid):
        with open(os.path.join(self.sd, "gorevler", f"{gid}.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_k1_model_bulunur(self):
        self.maliyet([_satir(C.OTURUM, "claude-sonnet-5-5", 1.0), _satir(C.OTURUM, "claude-opus-4-8", 5.0),
                      _satir(C.OTURUM, "claude-haiku-4-5", 99.0, gorev="G-001"), _satir("baska", "claude-x", 50.0)])
        r = self.yeni()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.oku(r.stdout.strip().splitlines()[-1])["plan_modeli"], "claude-opus-4-8")

    def test_k1_model_yoksa_tire(self):
        r = self.yeni()
        self.assertEqual(r.returncode, 0, r.stderr)
        k = self.oku(r.stdout.strip().splitlines()[-1])
        self.assertIn("plan_modeli", k)
        self.assertEqual(k["plan_modeli"], "-")

    def test_k2_effort_yazilir_ve_yoksa_yok(self):
        r = self.yeni("--effort", "high")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.oku(r.stdout.strip().splitlines()[-1])["effort"], "high")
        r2 = self.yeni()
        self.assertNotIn("effort", self.oku(r2.stdout.strip().splitlines()[-1]))

    def test_k2_gecersiz_effort(self):
        r = self.yeni("--effort", "ultra")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("effort", r.stderr)

    def test_k2_toplu_effort(self):
        kart = {"baslik": "toplu", "soru": "Test sorusu?", "girdi": "x", "kabul_kriterleri": ["k1"],
                "yazma_alani": ["docs/**"], "sinif": "belge", "effort": "xhigh"}
        dosya = os.path.join(self.proje, "toplu.json")
        with open(dosya, "w", encoding="utf-8") as f:
            json.dump([kart], f)
        r = self.cli("kart", "toplu", dosya)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        gid = json.loads(r.stdout)[0]["id"]
        self.assertEqual(self.oku(gid)["effort"], "xhigh")
        kart["effort"] = "ultra"
        with open(dosya, "w", encoding="utf-8") as f:
            json.dump([kart], f)
        self.assertNotEqual(self.cli("kart", "toplu", dosya).returncode, 0)

    def test_k3_doldur_idempotent(self):
        self.maliyet([_satir("o1", "claude-sonnet-5-5", 2.0), _satir("o1", "claude-opus-4-8", 1.0)])
        gd = os.path.join(self.sd, "gorevler")
        for gid, oturum, ek in (("G-901", "o1", {}), ("G-902", "yok", {}), ("G-903", "o1", {"plan_modeli": "-"}),
                                ("G-904", "o1", {"plan_modeli": "claude-elle"})):
            with open(os.path.join(gd, gid + ".json"), "w", encoding="utf-8") as f:
                json.dump({"id": gid, "oturum": oturum, **ek}, f)
        with open(os.path.join(gd, "G-901.denetim.json"), "w", encoding="utf-8") as f:
            json.dump([], f)
        r = subprocess.run([sys.executable, DOLDUR, self.sd], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("toplam 4", r.stdout)
        self.assertIn("dolduruldu 2", r.stdout)
        self.assertIn("plan_modeli boş: 0", r.stdout)
        self.assertEqual(self.oku("G-901")["plan_modeli"], "claude-sonnet-5-5")
        self.assertEqual(self.oku("G-902")["plan_modeli"], "-")
        self.assertEqual(self.oku("G-903")["plan_modeli"], "claude-sonnet-5-5")
        self.assertEqual(self.oku("G-904")["plan_modeli"], "claude-elle")
        r2 = subprocess.run([sys.executable, DOLDUR, self.sd], capture_output=True, text=True, encoding="utf-8")
        self.assertIn("dolduruldu 0", r2.stdout)
        self.assertIn("plan_modeli boş: 0", r2.stdout)

    def test_k4_goster_json(self):
        self.maliyet([_satir(C.OTURUM, "claude-sonnet-5-5", 1.0)])
        gid = self.yeni("--effort", "medium").stdout.strip().splitlines()[-1]
        r = self.cli("kart", "goster", gid, "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        k = json.loads(r.stdout)
        self.assertEqual(k["plan_modeli"], "claude-sonnet-5-5")
        self.assertEqual(k["effort"], "medium")


if __name__ == "__main__":
    unittest.main()
