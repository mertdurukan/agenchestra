"""L3: kural -> kayıtlı ön kontrol bağı (kural oner/ekle --kontrol, kural bagla), kural_aday kontrol alanı."""
import json
import os
import sys
import tempfile
import unittest

AD = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(AD, "..", "scripts")
ORKESTRA = os.path.join(SCRIPTS, "orkestra.py")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, AD)
import kanit_kapisi as KK  # noqa: E402
import kural_aday  # noqa: E402
import onay  # noqa: E402
import ic_kos  # noqa: E402


class Temel(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.proje = self.t.name
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(self.sd)
        self.md = os.path.join(self.proje, ".claude", "rules", "orkestra_kurallari.md")

    def tearDown(self):
        self.t.cleanup()

    def cli(self, *args):
        env = dict(os.environ, PYTHONUTF8="1", CLAUDE_PROJECT_DIR=self.proje)
        env.pop("CLAUDE_SESSION_ID", None)
        env.pop("CLAUDE_CODE_SESSION_ID", None)
        return ic_kos.kos([ORKESTRA, *args], cwd=self.proje, env=env)

    def kurallar(self):
        return onay.kurallar(self.sd)


class KuralKontrolTest(Temel):
    def test_k1_oner_kontrol_yazar(self):
        r = self.cli("kural", "oner", "--metin", "Kanıt ver", "--neden", "n", "--kontrol", "kanit-satiri")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.kurallar()[0]["kontrol"], "kanit-satiri")

    def test_k1_ekle_kontrol_yazar(self):
        r = self.cli("kural", "ekle", "--metin", "Kanıt ver", "--neden", "n", "--kontrol", "kanit-satiri")
        self.assertEqual(r.returncode, 0, r.stderr)
        k = self.kurallar()[0]
        self.assertEqual((k["kontrol"], k["durum"]), ("kanit-satiri", "etkin"))

    def test_k1_bilinmeyen_kimlik(self):
        for ad in ("oner", "ekle"):
            r = self.cli("kural", ad, "--metin", "x", "--neden", "n", "--kontrol", "yok-boyle")
            self.assertEqual(r.returncode, 2)
            for kim in KK.kontrol_kimlikleri():
                self.assertIn(kim, r.stderr)
        self.assertEqual(self.kurallar(), [])

    def test_k1_kontrolsuz_eskisi_gibi(self):
        self.assertEqual(self.cli("kural", "ekle", "--metin", "x", "--neden", "n").returncode, 0)
        self.assertNotIn("kontrol", self.kurallar()[0])

    def test_k2_bagla_ve_kaldir(self):
        self.cli("kural", "ekle", "--metin", "x", "--neden", "n")
        r = self.cli("kural", "bagla", "K-001", "--kontrol", "kanit-satiri")
        self.assertEqual(r.returncode, 0, r.stderr)
        k = self.kurallar()[0]
        self.assertEqual(k["kontrol"], "kanit-satiri")
        self.assertEqual((k["gecmis"][-1]["olay"], k["gecmis"][-1]["kontrol"]), ("kontrol-baglandi", "kanit-satiri"))
        r = self.cli("kural", "bagla", "K-001", "--kaldir")
        self.assertEqual(r.returncode, 0, r.stderr)
        k = self.kurallar()[0]
        self.assertNotIn("kontrol", k)
        self.assertEqual(k["gecmis"][-1]["olay"], "kontrol-kaldirildi")

    def test_k2_bilinmeyen_kural(self):
        r = self.cli("kural", "bagla", "K-099", "--kontrol", "kanit-satiri")
        self.assertEqual(r.returncode, 2)

    def test_k2_bilinmeyen_kimlik(self):
        self.cli("kural", "ekle", "--metin", "x", "--neden", "n")
        r = self.cli("kural", "bagla", "K-001", "--kontrol", "yok-boyle")
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("kontrol", self.kurallar()[0])

    def test_k3_liste(self):
        self.cli("kural", "ekle", "--metin", "bagli", "--neden", "n", "--kontrol", "sayi-tutarli")
        self.cli("kural", "ekle", "--metin", "bagsiz", "--neden", "n")
        j = json.loads(self.cli("kural", "liste", "--json").stdout)
        self.assertEqual(j[0]["kontrol"], "sayi-tutarli")
        self.assertNotIn("kontrol", j[1])
        satirlar = self.cli("kural", "liste").stdout.splitlines()
        self.assertIn("sayi-tutarli", satirlar[0])
        self.assertNotIn("sayi-tutarli", satirlar[1])
        g = onay.kural_gorunum(self.sd, self.proje)
        self.assertEqual(g["etkin"][0]["kontrol"], "sayi-tutarli")

    def test_k4_uctan_uca(self):
        self.cli("kural", "ekle", "--metin", "x", "--neden", "n", "--kontrol", "kanit-satiri")
        self.assertIn("kanit-satiri", KK.etkin_kontroller(self.sd))
        self.assertEqual(self.cli("kural", "kaldir", "K-001", "--not", "gerek yok").returncode, 0)
        self.assertNotIn("kanit-satiri", KK.etkin_kontroller(self.sd))

    def test_k4_oneri_etkin_sayilmaz(self):
        self.cli("kural", "oner", "--metin", "x", "--neden", "n", "--kontrol", "kanit-satiri")
        self.assertNotIn("kanit-satiri", KK.etkin_kontroller(self.sd))

    def test_k7_md_ayni_bicim(self):
        onay.kural_ekle(self.sd, "Metin", "Neden", kontrol="kanit-satiri")
        with open(self.md, encoding="utf-8") as f:
            a = f.read()
        self.assertNotIn("kontrol", a.lower())
        onay.kural_bagla(self.sd, "K-001", kaldir=True)
        with open(self.md, encoding="utf-8") as f:
            b = f.read()
        self.assertEqual(a, b)


class KuralAdayTest(unittest.TestCase):
    def kart(self, i, neden):
        return {"id": f"G-{i}", "sinif": "kod", "denetimler": [{"karar": "ret", "neden": neden}]}

    def test_k5_kontrol_kimligi(self):
        kartlar = []
        for i, n in enumerate(["kanit-yok", "kapsam-eksik", "sayi-tutarsiz", "bicim"]):
            kartlar += [self.kart(f"{i}{j}", n) for j in range(3)]
        out = {a["neden"]: a["kontrol_kimligi"] for a in kural_aday.kural_adaylari(kartlar, 3)}
        self.assertEqual(out, {"kanit-yok": "kanit-satiri", "kapsam-eksik": "kanit-satiri",
                               "sayi-tutarsiz": "sayi-tutarli", "bicim": None})

    def test_k5_rapor_kontrol_etkin(self):
        with tempfile.TemporaryDirectory() as sd:
            r = kural_aday.rapor(sd)
            self.assertEqual(set(r["kontrol_etkin"]), set(KK.kontrol_kimlikleri()))
            self.assertTrue(all(v is False for v in r["kontrol_etkin"].values()))
            onay.kural_ekle(sd, "x", "n", kontrol="kanit-satiri")
            r = kural_aday.rapor(sd)
            self.assertIs(r["kontrol_etkin"]["kanit-satiri"], True)
            self.assertEqual({"kural_adaylari", "anomaliler", "butce_tavani"} - set(r), set())


if __name__ == "__main__":
    unittest.main()
