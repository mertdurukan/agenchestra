"""is-bitti kanıt kapısı bağı (G-140): --kanit bayrağı, gölge/ihlal modu, hata yalıtımı, ajan tipi ayrımı."""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ic_kos  # noqa: E402

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(KOK, "scripts", "orkestra.py")
sys.path.insert(0, os.path.join(KOK, "scripts"))
OTURUM = "test-oturum-kib"
ISCI = dict(ajan_id="w1", ajan_tipi="orkestra:isci-t2")
TESTYAZARI = dict(ajan_id="ty1", ajan_tipi="orkestra:test-yazari")
UZUN = "x" * 900


class KanitIsBitti(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_kib_")
        r = self.kos([CLI, "baslat"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        r = self.cli("kart", "yeni", "--soru", "Kısa test sorusu?", "--baslik", "kanıt işi", "--basamak", "T2",
                     "--sinif", "arastirma", "--kabul", "K1: ilk kriter", "--kabul", "K2: ikinci kriter",
                     "--yazma", "src/**")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.gid = r.stdout.strip()

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)

    def kos(self, args):
        env = dict(os.environ, CLAUDE_CODE_SESSION_ID=OTURUM, PYTHONUTF8="1")
        env.pop("CLAUDE_PROJECT_DIR", None)
        return ic_kos.kos(args, cwd=self.proje, env=env)

    def cli(self, *args, ajan_id=None, ajan_tipi=None):
        a = [CLI] + list(args)
        if ajan_id:
            a += ["--ajan-id", ajan_id, "--ajan-tipi", ajan_tipi]
        return self.kos(a)

    def kural(self, mod="golge"):
        os.makedirs(os.path.join(self.sd, "kurallar"), exist_ok=True)
        with open(os.path.join(self.sd, "kurallar", "kurallar.json"), "w", encoding="utf-8") as f:
            json.dump({"kurallar": [{"id": "K-001", "durum": "etkin", "kontrol": "kanit-satiri"}]}, f)
        with open(os.path.join(self.sd, "on_kontrol.json"), "w", encoding="utf-8") as f:
            json.dump({"kontroller": {"kanit-satiri": {"mod": mod}}}, f)

    def goster(self):
        r = self.cli("kart", "goster", self.gid)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def bitti(self, *ek, ozet="bitti", **kim):
        return self.cli("kart", "durum", self.gid, "is-bitti", "--ozet", ozet, *ek, **(kim or ISCI))

    def olay_sayisi(self, k, olay):
        return sum(1 for g in k["gecmis"] if g["olay"] == olay)

    # K1
    def test_k1_kanit_son_kanit_yazar_maskeli_kirpik(self):
        r = self.bitti("--kanit", "K1: x", "--kanit", "K2: " + UZUN)
        self.assertEqual(r.returncode, 0, r.stderr)
        sk = self.goster()["son_kanit"]
        self.assertEqual(len(sk), 2)
        self.assertEqual(sk[0], "K1: x")
        self.assertEqual(len(sk[1]), 400)

    def test_k1_kanit_yoksa_alan_yazilmaz(self):
        r = self.bitti()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("son_kanit", self.goster())

    # K2
    def test_k2_kontrol_etkin_degilken_degismez(self):
        r = self.bitti()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("UYARI", r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip(), f"{self.gid} → denetimde")
        kapi = self.goster()["is_turlari"][-1].get("kapi") or {}
        self.assertFalse([x for x in kapi if x.startswith("kanit")])

    # K3
    def test_k3_golge_kanitsiz_basarili_uyari(self):
        self.kural("golge")
        r = self.bitti()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.count("UYARI (gölge)"), 1, r.stdout)
        k = self.goster()
        self.assertEqual(k["durum"], "denetimde")
        kapi = k["is_turlari"][-1]["kapi"]
        self.assertEqual(kapi["kanit"], "eksik:K1,K2")
        self.assertEqual(kapi["kanit_mod"], "golge")
        self.assertNotIn("_mesajlar", kapi)

    # K4
    def test_k4_ihlal_eksik_cikis4_kayit_yok(self):
        self.kural("ihlal")
        r = self.bitti()
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertIn("K1", r.stdout + r.stderr)
        self.assertIn("K2", r.stdout + r.stderr)
        self.assertIn('--kanit "K1:', r.stdout + r.stderr)
        k = self.goster()
        self.assertNotEqual(k["durum"], "denetimde")
        self.assertEqual(self.olay_sayisi(k, "kapi-gecmedi"), 1)
        self.assertFalse(k.get("is_turlari"))

    def test_k4_ihlal_kanitla_gecer(self):
        self.kural("ihlal")
        self.assertEqual(self.bitti().returncode, 4)
        r = self.bitti("--kanit", "K1: dosya.py:10 tamam", "--kanit", "K2: komut çıktısı 3 geçti")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        k = self.goster()
        self.assertEqual(k["durum"], "denetimde")
        self.assertEqual(k["is_turlari"][-1]["kapi"]["kanit"], "gecti")

    # K5
    def test_k5_kapi_istisnasi_isi_engellemez(self):
        import kanit_kapisi
        self.kural("ihlal")
        eski = kanit_kapisi.kapi

        def patlak(*a, **kw):
            raise RuntimeError("bozuk")
        kanit_kapisi.kapi = patlak
        try:
            r = self.bitti()
        finally:
            kanit_kapisi.kapi = eski
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        kapi = self.goster()["is_turlari"][-1]["kapi"]
        self.assertEqual(kapi["kanit_hata"], "RuntimeError")

    # K6
    def test_k6_test_yazari_kapi_kosmaz(self):
        self.kural("ihlal")
        r = self.bitti(**TESTYAZARI)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("UYARI", r.stdout + r.stderr)
        tur = self.goster()["is_turlari"][-1]
        self.assertFalse([x for x in (tur.get("kapi") or {}) if x.startswith("kanit")])

    def test_k6_ana_ajan_is_bitti_kapisiz_reddedilir(self):
        self.kural("ihlal")
        r = self.bitti(ajan_id="ana", ajan_tipi="ana")
        self.assertNotEqual(r.returncode, 4)
        self.assertNotIn("K-001", r.stdout + r.stderr)
        self.assertEqual(self.olay_sayisi(self.goster(), "kapi-gecmedi"), 0)


if __name__ == "__main__":
    unittest.main()
