"""G-124: denetçi onayında düşük riskli kod kartı kendiliğinden teslim (oto_teslim)."""
import contextlib
import io
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
OTURUM = "test-oturum-oto"

DENETCI = dict(ajan_id="d1", ajan_tipi="orkestra:denetci")
ISCI_KAPISIZ = dict(ajan_id="w1", ajan_tipi="orkestra:arsivci")
ANA = dict(ajan_id="ana", ajan_tipi="ana")
BETIK = "import os, sys\nsys.exit(0 if os.path.exists('bayrak.txt') else 1)\n"


def kos(args, cwd):
    env = dict(os.environ, CLAUDE_CODE_SESSION_ID=OTURUM, PYTHONUTF8="1")
    env.pop("CLAUDE_PROJECT_DIR", None)
    return ic_kos.kos(args, cwd=cwd, env=env)


class OtoTeslim(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_oto_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        self.assertEqual(kos([CLI, "baslat"], self.proje).returncode, 0)
        os.makedirs(os.path.join(self.proje, "testler"))
        with open(os.path.join(self.proje, "testler", "test_a.py"), "w", encoding="utf-8") as f:
            f.write(BETIK)
        self.komut = f'"{sys.executable}" testler/test_a.py'

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)

    def cli(self, *args, ajan_id=None, ajan_tipi=None):
        a = [CLI] + list(args)
        if ajan_id:
            a += ["--ajan-id", ajan_id, "--ajan-tipi", ajan_tipi]
        return kos(a, self.proje)

    def ok(self, *args, **kim):
        r = self.cli(*args, **kim)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def goster(self, g):
        return json.loads(self.ok("kart", "goster", g).stdout)

    def olaylar(self, g):
        return [x.get("olay") for x in self.goster(g)["gecmis"]]

    def kod_karti(self, *ek):
        r = self.ok("kart", "yeni", "--soru", "Kısa test sorusu?", "--baslik", "kod işi", "--basamak", "T2", "--sinif", "kod", "--tdd",
                    "--kabul", "çalışır", "--yazma", "src/**", "--test-komutu", self.komut,
                    "--test-alani", "testler/*.py", *ek)
        return r.stdout.strip()

    def belge_karti(self, *ek):
        r = self.ok("kart", "yeni", "--soru", "Kısa test sorusu?", "--baslik", "belge işi", "--basamak", "T1", "--sinif", "belge",
                    "--kabul", "yazıldı", "--yazma", "docs/**", *ek)
        return r.stdout.strip()

    def onaya_hazirla(self, g):
        """Kod kartı: kırmızı → is-bitti → yeşil (denetim onayına hazır)."""
        self.ok("kart", "test-kos", g, "--asama", "kirmizi")
        self.ok("kart", "durum", g, "is-bitti", "--ozet", "bitti", "--cikti", "src/a.py", **ISCI_KAPISIZ)
        with open(os.path.join(self.proje, "bayrak.txt"), "w") as f:
            f.write("1")
        self.ok("kart", "test-kos", g, "--asama", "yesil")

    def onay(self, g):
        return self.cli("kart", "denetim", g, "--karar", "onay", "--gerekce", "kriterler tamam", **DENETCI)

    # K1
    def test_k1_varsayilan_kodda_true_kod_disinda_false(self):
        self.assertIs(self.goster(self.kod_karti())["oto_teslim"], True)
        self.assertIs(self.goster(self.belge_karti())["oto_teslim"], False)

    def test_k1_elle_teslim_ve_oto_teslim_bayragi(self):
        self.assertIs(self.goster(self.kod_karti("--elle-teslim"))["oto_teslim"], False)
        self.assertIs(self.goster(self.belge_karti("--oto-teslim"))["oto_teslim"], True)

    def test_k1_toplu_json_varsayilan_ve_false(self):
        plan = [
            {"soru": "Kısa test sorusu?", "baslik": "k1", "sinif": "kod", "kabul_kriterleri": ["a"], "yazma_alani": ["src/a/**"],
             "test_komutu": self.komut, "test_alani": ["testler/*.py"]},
            {"soru": "Kısa test sorusu?", "baslik": "k2", "sinif": "kod", "kabul_kriterleri": ["a"], "yazma_alani": ["src/b/**"],
             "test_komutu": self.komut, "test_alani": ["testler/*.py"], "oto_teslim": False},
            {"soru": "Kısa test sorusu?", "baslik": "b1", "sinif": "belge", "kabul_kriterleri": ["a"], "yazma_alani": ["docs/a/**"]},
        ]
        yol = os.path.join(self.proje, "plan.json")
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(plan, f)
        s = json.loads(self.ok("kart", "toplu", yol).stdout)
        degerler = [self.goster(x["id"])["oto_teslim"] for x in s]
        self.assertEqual(degerler, [True, False, False])

    def test_k1_gecersiz_deger_reddedilir(self):
        plan = [{"soru": "Kısa test sorusu?", "baslik": "b", "sinif": "belge", "kabul_kriterleri": ["a"], "oto_teslim": "evet"}]
        yol = os.path.join(self.proje, "plan.json")
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(plan, f)
        self.assertNotEqual(self.cli("kart", "toplu", yol).returncode, 0)

    # K2
    def test_k2_onaydan_sonra_kod_karti_teslim_olur(self):
        g = self.kod_karti()
        self.onaya_hazirla(g)
        r = self.onay(g)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        k = self.goster(g)
        self.assertEqual(k["durum"], "teslim")
        o = self.olaylar(g)
        self.assertIn("oto-teslim", o)
        self.assertEqual(o.count("teslim"), 1)
        self.assertTrue(k["teslim_ozeti"].startswith("oto: kriterler tamam"))
        defter = self.ok("defter", "oku", "--gorev", g).stdout
        self.assertIn("TESLİM", defter)

    def test_k2_oto_teslim_olmus_karta_ana_ajan_teslimi_zararsiz(self):
        g = self.kod_karti()
        self.onaya_hazirla(g)
        self.assertEqual(self.onay(g).returncode, 0)
        self.ok("kart", "teslim", g, "--ozet", "tekrar", **ANA)
        self.assertEqual(self.olaylar(g).count("teslim"), 1)

    def test_k2_denetci_kart_teslim_hala_cikis_3(self):
        g = self.kod_karti("--elle-teslim")
        self.onaya_hazirla(g)
        self.assertEqual(self.onay(g).returncode, 0)
        self.assertEqual(self.cli("kart", "teslim", g, "--ozet", "x", **DENETCI).returncode, 3)

    # K3
    def test_k3_oto_teslim_false_kod_karti_onaylandi_kalir(self):
        g = self.kod_karti("--elle-teslim")
        self.onaya_hazirla(g)
        self.assertEqual(self.onay(g).returncode, 0)
        self.assertEqual(self.goster(g)["durum"], "onaylandi")
        self.assertNotIn("oto-teslim", self.olaylar(g))

    def test_k3_belge_karti_varsayilan_onaylandi_kalir(self):
        g = self.belge_karti()
        self.ok("kart", "durum", g, "is-bitti", "--ozet", "x", "--cikti", "docs/a.md", **ISCI_KAPISIZ)
        self.assertEqual(self.onay(g).returncode, 0)
        self.assertEqual(self.goster(g)["durum"], "onaylandi")

    def test_k3_ret_kararinda_hicbir_sey_degismez(self):
        g = self.kod_karti()
        self.onaya_hazirla(g)
        r = self.cli("kart", "denetim", g, "--karar", "ret", "--neden", "kapsam-eksik", "--gerekce", "K1 eksik",
                     **DENETCI)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.goster(g)["durum"], "reddedildi")
        self.assertNotIn("oto-teslim", self.olaylar(g))

    # I-145 P1/P5: alanı olmayan (G-124 öncesi) kart karar anında sınıftan türetilir
    def alani_sil(self, g):
        yol = os.path.join(self.sd, "gorevler", f"{g}.json")
        with open(yol, encoding="utf-8") as f:
            k = json.load(f)
        k.pop("oto_teslim", None)
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(k, f)

    def test_p1_alansiz_eski_kod_karti_onayda_teslim_olur(self):
        g = self.kod_karti()
        self.onaya_hazirla(g)
        self.alani_sil(g)
        self.assertEqual(self.onay(g).returncode, 0)
        self.assertEqual(self.goster(g)["durum"], "teslim")
        self.assertIn("oto-teslim", self.olaylar(g))

    def test_p1_alansiz_belge_karti_onaylandi_kalir(self):
        g = self.belge_karti()
        self.ok("kart", "durum", g, "is-bitti", "--ozet", "x", "--cikti", "docs/a.md", **ISCI_KAPISIZ)
        self.alani_sil(g)
        self.assertEqual(self.onay(g).returncode, 0)
        self.assertEqual(self.goster(g)["durum"], "onaylandi")

    def test_p1_acik_false_turetmeyi_gecer(self):
        g = self.kod_karti("--elle-teslim")
        self.onaya_hazirla(g)
        self.assertEqual(self.onay(g).returncode, 0)
        self.assertEqual(self.goster(g)["durum"], "onaylandi")

    # I-145 P2: onaylı ama teslim edilmemiş kartları toplayan tarama
    def onayli_birak(self, g, alan_sil=True):
        """Kod kartını teslim edilmeden onaylı bırakır (eski kartın durumu): alan yazılı false iken onaylanır."""
        bayrak = os.path.join(self.proje, "bayrak.txt")
        if os.path.exists(bayrak):
            os.remove(bayrak)  # kırmızı aşama için test başarısız olmalı
        self.onaya_hazirla(g)
        yol = os.path.join(self.sd, "gorevler", f"{g}.json")
        with open(yol, encoding="utf-8") as f:
            k = json.load(f)
        k["oto_teslim"] = False
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(k, f)
        self.assertEqual(self.onay(g).returncode, 0)
        self.assertEqual(self.goster(g)["durum"], "onaylandi")
        if alan_sil:
            self.alani_sil(g)

    def test_p2_tarama_uygun_onayli_kartlari_teslim_eder_ikincisi_bos(self):
        a, b = self.kod_karti(), self.kod_karti()
        self.onayli_birak(a)
        self.onayli_birak(b)
        elle = self.kod_karti("--elle-teslim")
        self.onayli_birak(elle, alan_sil=False)
        belge = self.belge_karti()
        self.ok("kart", "durum", belge, "is-bitti", "--ozet", "x", "--cikti", "docs/a.md", **ISCI_KAPISIZ)
        self.assertEqual(self.onay(belge).returncode, 0)
        r = self.ok("kart", "teslim-bekleyen", **ANA)
        self.assertIn("2 teslim", r.stdout)
        self.assertEqual([self.goster(g)["durum"] for g in (a, b, elle, belge)],
                         ["teslim", "teslim", "onaylandi", "onaylandi"])
        self.assertIn("0 teslim", self.ok("kart", "teslim-bekleyen", **ANA).stdout)

    def test_p2_session_start_onayli_karti_toplar_ve_stdout_sessiz(self):
        sys.path.insert(0, os.path.join(KOK, "scripts"))
        import hook
        g = self.kod_karti()
        self.onayli_birak(g)
        kapat = io.StringIO()
        with contextlib.redirect_stdout(kapat):
            satir, _ = hook._ss_birinci_satir(self.sd, None, [self.goster(g)])
        self.assertEqual(kapat.getvalue(), "")  # stdout hook çıktısıdır; tarama yazmaz
        self.assertIn(f"Teslim edildi (onaylı, toplanmamıştı): {g}", satir)
        self.assertEqual(self.goster(g)["durum"], "teslim")

    def test_p2_tarama_denetci_icin_cikis_3(self):
        self.assertEqual(self.cli("kart", "teslim-bekleyen", **DENETCI).returncode, 3)

    # K4
    def test_k4_teslim_hatasinda_kart_onaylandi_kalir_cikis_sifir(self):
        g = self.kod_karti()
        self.onaya_hazirla(g)
        yol = os.path.join(self.sd, "gorevler", f"{g}.json")
        with open(yol, encoding="utf-8") as f:
            k = json.load(f)
        # git deposu olmayan proje kökü ağaç gibi gösterilir: birleştirme "hata" döner (çalışma ağacı birleşmez)
        k["calisma_agaci"] = {"depo": self.proje, "yol": self.proje, "dal": "kart/yok", "taban": "0" * 40}
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(k, f)
        r = self.onay(g)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("oto-teslim yapılamadı", r.stderr)
        self.assertEqual(self.goster(g)["durum"], "onaylandi")
        o = self.olaylar(g)
        self.assertNotIn("teslim", o)
        self.assertNotIn("oto-teslim", o)


if __name__ == "__main__":
    unittest.main()
