"""G-134: is-bitti --teknik zorunlu teknik not kapısı testleri (K1-K6).

`python -m unittest discover -s plugins/orkestra/tests -p test_teknik_kapisi.py -v`

Spesifikasyondan, uygulamadan ÖNCE yazıldı. Kapı bu testlerde ORKESTRA_TEKNIK_KAPISI=1 ile açıkça kurulur.
"""
import copy
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
OTURUM = "test-oturum-tek"

BETIK = "import os, sys\nprint('kosuldu')\nsys.exit(0 if os.path.exists('bayrak.txt') else 1)\n"

ISCI = dict(ajan_id="w1", ajan_tipi="orkestra:isci-t2")
TEST_YAZARI = dict(ajan_id="ty1", ajan_tipi="orkestra:test-yazari")
ANA = dict(ajan_id="ana", ajan_tipi="ana")

GECERLI = {
    "yaklasim": "Doğrulama saf bir fonksiyonda toplandı ve CLI kapısından çağrılır.",
    "neden_bu_yol": "Saf fonksiyon ucuz test edilir; kapı tek noktada kalır.",
    "alternatifler": [{"secenek": "Kapıyı hook içinde koşmak", "neden_elendi": "Kart bağlamı hook içinde yok."}],
    "entegrasyon": ["kart.py → teknik_not.py: nesneyi doğrular"],
    "riskler": ["Eski kartlarda alan yok"],
}


def kos(args, cwd, kapi="1"):
    env = dict(os.environ, CLAUDE_CODE_SESSION_ID=OTURUM, PYTHONUTF8="1")
    env.pop("CLAUDE_PROJECT_DIR", None)
    env["ORKESTRA_TEKNIK_KAPISI"] = kapi
    return ic_kos.kos(args, cwd=cwd, env=env)


class TeknikKapisi(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_tek_")
        self.assertEqual(self.cli("baslat").returncode, 0)
        os.makedirs(os.path.join(self.proje, "testler"))
        self.yaz("testler/test_a.py", BETIK)
        self.komut = f'"{sys.executable}" testler/test_a.py'

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)

    # ---------------------------------------------------------- yardımcılar
    def yaz(self, goreli, icerik):
        yol = os.path.join(self.proje, *goreli.split("/"))
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with open(yol, "w", encoding="utf-8") as f:
            f.write(icerik)
        return yol

    def teknik_dosyasi(self, nesne=None, ad="teknik.json", ham=None):
        icerik = ham if ham is not None else json.dumps(GECERLI if nesne is None else nesne, ensure_ascii=False)
        return self.yaz(ad, icerik)

    def cli(self, *args, kapi="1", kim=None):
        a = [CLI] + list(args)
        if kim:
            a += ["--ajan-id", kim["ajan_id"], "--ajan-tipi", kim["ajan_tipi"]]
        return kos(a, self.proje, kapi=kapi)

    def goster(self, g):
        r = self.cli("kart", "goster", g)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def kart(self, sinif="arastirma"):
        a = ["kart", "yeni", "--soru", "Kısa test sorusu?", "--baslik", "iş", "--basamak", "T2", "--sinif", sinif,
             "--kabul", "çalışır", "--yazma", "src/**"]
        if sinif == "kod":
            a += ["--tdd", "--test-komutu", self.komut, "--test-alani", "testler/*.py"]
        r = self.cli(*a)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def kod_karti_kirmizi(self):
        g = self.kart("kod")
        bayrak = os.path.join(self.proje, "bayrak.txt")
        if os.path.exists(bayrak):
            os.remove(bayrak)
        r = self.cli("kart", "test-kos", g, "--asama", "kirmizi")
        self.assertEqual(r.returncode, 0, r.stderr)
        # Yeşil koşu geçebilsin: not eksikken yine de koşmadığı kanıtlanır.
        with open(bayrak, "w") as f:
            f.write("1")
        return g

    def bitir(self, g, teknik=None, kim=ISCI, kapi="1"):
        a = ["kart", "durum", g, "is-bitti", "--ozet", "bitti", "--cikti", "src/a.py"]
        if teknik is not None:
            a += ["--teknik", teknik]
        return self.cli(*a, kim=kim, kapi=kapi)

    def kayitsiz(self, g):
        k = self.goster(g)
        self.assertNotIn("is-bitti", [h.get("olay") for h in k["gecmis"]])
        self.assertNotIn("teknik", k)
        self.assertNotIn("teknik_zaman", k)

    def reddedildi(self, r, g, alan=None):
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        mesaj = r.stdout + r.stderr
        self.assertIn("is-bitti KAYDEDİLMEDİ: teknik not", mesaj)
        if alan:
            self.assertIn(alan, mesaj)
        self.kayitsiz(g)

    # ---------------------------------------------------------- K1
    def test_k1_gecerli_teknik_kaydedilir(self):
        g = self.kart()
        r = self.bitir(g, self.teknik_dosyasi())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        k = self.goster(g)
        self.assertIn("is-bitti", [h.get("olay") for h in k["gecmis"]])
        self.assertEqual(k["teknik"], GECERLI)
        self.assertTrue(isinstance(k.get("teknik_zaman"), str) and k["teknik_zaman"])

    def test_k1_bos_listeler_gecerli(self):
        g = self.kart()
        n = dict(GECERLI, alternatifler=[], entegrasyon=[], riskler=[])
        r = self.bitir(g, self.teknik_dosyasi(n))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.goster(g)["teknik"]["riskler"], [])

    def test_k1_sinir_20_ve_400_karakter_gecerli(self):
        g = self.kart()
        n = dict(GECERLI, yaklasim="a" * 20, neden_bu_yol="b" * 400)
        r = self.bitir(g, self.teknik_dosyasi(n))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_k1_kod_kartinda_gecerli_teknikle_kaydedilir(self):
        g = self.kod_karti_kirmizi()
        r = self.bitir(g, self.teknik_dosyasi())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.goster(g)["teknik"], GECERLI)

    # ---------------------------------------------------------- K2
    def test_k2_teknik_bayragi_yok(self):
        g = self.kart()
        self.reddedildi(self.bitir(g), g)

    def test_k2_dosya_yok(self):
        g = self.kart()
        self.reddedildi(self.bitir(g, os.path.join(self.proje, "yok.json")), g)

    def test_k2_json_bozuk(self):
        g = self.kart()
        self.reddedildi(self.bitir(g, self.teknik_dosyasi(ham="{bozuk json")), g)

    def test_k2_json_nesne_degil(self):
        g = self.kart()
        self.reddedildi(self.bitir(g, self.teknik_dosyasi(ham="[1, 2]")), g)

    def test_k2_yaklasim_19_karakter(self):
        g = self.kart()
        self.reddedildi(self.bitir(g, self.teknik_dosyasi(dict(GECERLI, yaklasim="a" * 19))), g, "yaklasim")

    def test_k2_yaklasim_401_karakter(self):
        g = self.kart()
        self.reddedildi(self.bitir(g, self.teknik_dosyasi(dict(GECERLI, yaklasim="a" * 401))), g, "yaklasim")

    def test_k2_neden_19_karakter(self):
        g = self.kart()
        self.reddedildi(self.bitir(g, self.teknik_dosyasi(dict(GECERLI, neden_bu_yol="a" * 19))), g, "neden_bu_yol")

    def test_k2_neden_401_karakter(self):
        g = self.kart()
        self.reddedildi(self.bitir(g, self.teknik_dosyasi(dict(GECERLI, neden_bu_yol="a" * 401))), g, "neden_bu_yol")

    def test_k2_yaklasim_metin_degil(self):
        g = self.kart()
        self.reddedildi(self.bitir(g, self.teknik_dosyasi(dict(GECERLI, yaklasim=12345))), g, "yaklasim")

    def test_k2_alternatifler_liste_degil(self):
        g = self.kart()
        self.reddedildi(self.bitir(g, self.teknik_dosyasi(dict(GECERLI, alternatifler="yok"))), g, "alternatifler")

    def test_k2_entegrasyon_liste_degil(self):
        g = self.kart()
        self.reddedildi(self.bitir(g, self.teknik_dosyasi(dict(GECERLI, entegrasyon={"a": "b"}))), g, "entegrasyon")

    def test_k2_riskler_liste_degil(self):
        g = self.kart()
        self.reddedildi(self.bitir(g, self.teknik_dosyasi(dict(GECERLI, riskler="risk yok"))), g, "riskler")

    def test_k2_alternatif_ogesi_anahtar_eksik(self):
        g = self.kart()
        n = dict(GECERLI, alternatifler=[{"secenek": "Yalnız seçenek var"}])
        self.reddedildi(self.bitir(g, self.teknik_dosyasi(n)), g, "neden_elendi")

    def _eksik_anahtar(self, anahtar):
        g = self.kart()
        n = copy.deepcopy(GECERLI)
        del n[anahtar]
        self.reddedildi(self.bitir(g, self.teknik_dosyasi(n)), g, anahtar)

    def test_k2_anahtar_eksik_yaklasim(self):
        self._eksik_anahtar("yaklasim")

    def test_k2_anahtar_eksik_neden_bu_yol(self):
        self._eksik_anahtar("neden_bu_yol")

    def test_k2_anahtar_eksik_alternatifler(self):
        self._eksik_anahtar("alternatifler")

    def test_k2_anahtar_eksik_entegrasyon(self):
        self._eksik_anahtar("entegrasyon")

    def test_k2_anahtar_eksik_riskler(self):
        self._eksik_anahtar("riskler")

    def test_k2_reddedilince_yeniden_denenebilir(self):
        g = self.kart()
        self.reddedildi(self.bitir(g), g)
        r = self.bitir(g, self.teknik_dosyasi())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("is-bitti", [h.get("olay") for h in self.goster(g)["gecmis"]])

    # ---------------------------------------------------------- K3
    def test_k3_not_eksikken_test_komutu_kosmaz(self):
        g = self.kod_karti_kirmizi()
        self.assertEqual([x["asama"] for x in self.goster(g)["test_kosulari"]], ["kirmizi"])
        self.reddedildi(self.bitir(g), g)
        self.assertEqual([x["asama"] for x in self.goster(g)["test_kosulari"]], ["kirmizi"])

    def test_k3_gecersiz_notla_test_ve_on_kontrol_kosmaz(self):
        g = self.kod_karti_kirmizi()
        self.reddedildi(self.bitir(g, self.teknik_dosyasi(dict(GECERLI, yaklasim="kısa"))), g, "yaklasim")
        k = self.goster(g)
        self.assertEqual([x["asama"] for x in k["test_kosulari"]], ["kirmizi"])
        notlar = " ".join(str(h.get("not", "")) for h in k["gecmis"] if h.get("olay") == "kapi-gecmedi")
        self.assertNotIn("yesil", notlar)
        self.assertNotIn("on_kontrol", notlar)

    def test_k3_not_gecerliyse_test_kosar(self):
        g = self.kod_karti_kirmizi()
        r = self.bitir(g, self.teknik_dosyasi())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([x["asama"] for x in self.goster(g)["test_kosulari"]], ["kirmizi", "yesil"])

    # ---------------------------------------------------------- K4
    def test_k4_test_yazari_kapidan_muaf(self):
        g = self.kart()
        r = self.bitir(g, kim=TEST_YAZARI)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("teknik not", r.stdout + r.stderr)

    def test_k4_ana_ajan_kapiyi_calistirmaz(self):
        g = self.kart()
        r = self.bitir(g, kim=ANA)
        # Ana ajan başka nedenle reddedilir; teknik not kapısı yüzünden değil.
        self.assertNotIn("teknik not", r.stdout + r.stderr)

    def test_k4_ortam_degiskeni_sifir_kapiyi_kapatir(self):
        g = self.kart()
        r = self.bitir(g, kapi="0")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("is-bitti", [h.get("olay") for h in self.goster(g)["gecmis"]])

    def test_k4_ortam_degiskeni_birken_isci_notsuz_reddedilir(self):
        g = self.kart()
        self.reddedildi(self.bitir(g, kapi="1"), g)

    # ---------------------------------------------------------- K5
    def _icerik(self, goreli):
        with open(os.path.join(KOK, *goreli.split("/")), encoding="utf-8") as f:
            return f.read()

    def _k5(self, goreli):
        t = self._icerik(goreli)
        self.assertIn("--teknik", t, goreli)
        for anahtar in ("yaklasim", "neden_bu_yol", "alternatifler", "entegrasyon", "riskler"):
            self.assertIn(anahtar, t, f"{goreli}: şemada {anahtar} yok")

    def test_k5_isci_t1(self):
        self._k5("agents/isci-t1.md")

    def test_k5_isci_t2(self):
        self._k5("agents/isci-t2.md")

    def test_k5_isci_t3(self):
        self._k5("agents/isci-t3.md")

    def test_k5_isci_t4(self):
        self._k5("agents/isci-t4.md")

    def test_k5_calistir_js_kapi_protokolu(self):
        t = self._icerik("workflows/calistir.js")
        i = t.index("KAPI_PROTOKOLU")
        self.assertIn("--teknik", t[i:])
        for anahtar in ("yaklasim", "neden_bu_yol", "alternatifler"):
            self.assertIn(anahtar, t[i:])

    def test_k5_is_skill(self):
        self._k5("skills/is/SKILL.md")

    # ---------------------------------------------------------- K6
    def test_k6_denetci_teknik_not_tutarliligi(self):
        t = self._icerik("agents/denetci.md").lower()
        self.assertIn("teknik not", t)
        self.assertIn("tutarl", t)

    def test_k6_kurallar_teknik_not_maddesi(self):
        t = self._icerik("KURALLAR.md").lower()
        self.assertIn("teknik not", t)
        self.assertIn("tutarl", t)

    # ---------------------------------------------------------- doğrulama modülü
    def test_teknik_not_modulu_dogrula(self):
        sys.path.insert(0, os.path.join(KOK, "scripts"))
        import teknik_not
        tamam, hatalar = teknik_not.dogrula(copy.deepcopy(GECERLI))
        self.assertTrue(tamam)
        self.assertEqual(list(hatalar), [])
        tamam, hatalar = teknik_not.dogrula(dict(GECERLI, yaklasim="kısa"))
        self.assertFalse(tamam)
        self.assertTrue(any("yaklasim" in h for h in hatalar))
        tamam, _ = teknik_not.dogrula("metin")
        self.assertFalse(tamam)


if __name__ == "__main__":
    unittest.main()
