"""Orkestra test kapısı (kod kartları için kırmızı/yeşil) CLI testleri.

`python -m unittest discover -s plugins/orkestra/tests -p test_test_kapisi.py -v`

Spesifikasyondan, uygulamadan ÖNCE yazıldı. Geçici projede çalışır; ağ ya da DB kullanmaz.
Test komutu, geçici projedeki küçük bir python dosyasının çıkış koduna bağlıdır:
`bayrak.txt` varsa 0, yoksa 1.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(KOK, "scripts", "orkestra.py")
OTURUM = "test-oturum-tk"

BETIK = (
    "import os, sys\n"
    "print('kosuldu')\n"
    "sys.exit(0 if os.path.exists('bayrak.txt') else 1)\n"
)
UZUN_BETIK = (
    "import os, sys\n"
    "print('x' * 5000 + 'SON_IZ')\n"
    "sys.exit(0 if os.path.exists('bayrak.txt') else 1)\n"
)
UYKU_BETIK = "import time\ntime.sleep(30)\n"

DENETCI = dict(ajan_id="d1", ajan_tipi="orkestra:denetci")
ISCI = dict(ajan_id="w1", ajan_tipi="orkestra:isci-t2")
# Onay kapısını tek başına sınamak için kapısız is-bitti (işçi is-bitti'si testi kendisi koşar; bkz. test_is_bitti_kapisi).
ISCI_KAPISIZ = dict(ajan_id="w1", ajan_tipi="orkestra:arsivci")
ANA = dict(ajan_id="ana", ajan_tipi="ana")


def kos(args, cwd):
    env = dict(os.environ, CLAUDE_CODE_SESSION_ID=OTURUM, PYTHONUTF8="1")
    env.pop("CLAUDE_PROJECT_DIR", None)
    return subprocess.run([sys.executable] + args, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8")


class TestKapisi(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_tk_")
        r = kos([CLI, "baslat"], self.proje)
        self.assertEqual(r.returncode, 0, r.stderr)
        os.makedirs(os.path.join(self.proje, "testler"))
        self.yaz("testler/test_a.py", BETIK)
        self.yaz("testler/uyku.py", UYKU_BETIK)
        self.komut = f'"{sys.executable}" testler/test_a.py'

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)

    # ---------------------------------------------------------- yardımcılar
    def yaz(self, goreli, icerik):
        yol = os.path.join(self.proje, *goreli.split("/"))
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with open(yol, "w", encoding="utf-8") as f:
            f.write(icerik)

    def sil(self, goreli):
        os.remove(os.path.join(self.proje, *goreli.split("/")))

    def bayrak(self, var):
        yol = os.path.join(self.proje, "bayrak.txt")
        if var:
            with open(yol, "w") as f:
                f.write("1")
        elif os.path.exists(yol):
            os.remove(yol)

    def cli(self, *args, ajan_id=None, ajan_tipi=None):
        a = [CLI] + list(args)
        if ajan_id:
            a += ["--ajan-id", ajan_id, "--ajan-tipi", ajan_tipi]
        return kos(a, self.proje)

    def kod_karti(self, komut=None, alanlar=("testler/*.py",), sinif="kod"):
        a = ["kart", "yeni", "--baslik", "kod işi", "--basamak", "T2", "--sinif", sinif, *(["--tdd"] if sinif == "kod" else []),
             "--kabul", "çalışır", "--yazma", "src/**"]
        if komut is not False:
            a += ["--test-komutu", komut or self.komut]
        for g in alanlar or ():
            a += ["--test-alani", g]
        r = self.cli(*a)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def goster(self, g):
        r = self.cli("kart", "goster", g)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def kos_t(self, g, asama, *ek):
        return self.cli("kart", "test-kos", g, "--asama", asama, *ek)

    def is_bitti(self, g):
        r = self.cli("kart", "durum", g, "is-bitti", "--ozet", "bitti", "--cikti", "src/a.py", **ISCI_KAPISIZ)
        self.assertEqual(r.returncode, 0, r.stderr)

    def onay(self, g):
        return self.cli("kart", "denetim", g, "--karar", "onay", "--gerekce", "tamam", **DENETCI)

    def ret(self, g):
        return self.cli("kart", "denetim", g, "--karar", "ret", "--neden", "kapsam-eksik", "--gerekce", "eksik", "--talimat", "düzelt", **DENETCI)

    def kirmizi_kilitle(self):
        """Kod kartı + kilitli kırmızı (bayrak yok → test başarısız)."""
        g = self.kod_karti()
        self.bayrak(False)
        r = self.kos_t(g, "kirmizi")
        self.assertEqual(r.returncode, 0, r.stderr)
        return g

    # ---------------------------------------------------------- 1) kart alanları
    def test_kart_alanlari_saklanir(self):
        g = self.kod_karti(alanlar=("testler/*.py", "ek/**/*.py"))
        k = self.goster(g)
        self.assertEqual(k["sinif"], "kod")
        self.assertEqual(k["test_komutu"], self.komut)
        self.assertEqual(k["test_alani"], ["testler/*.py", "ek/**/*.py"])
        self.assertIsNone(k["test_kilidi"])
        self.assertEqual(k["test_kosulari"], [])

    def test_kod_kartinda_test_komutu_eksik_reddedilir(self):
        r = self.cli("kart", "yeni", "--baslik", "x", "--basamak", "T2", "--sinif", "kod", "--tdd", "--kabul", "k",
                     "--yazma", "src/**", "--test-alani", "testler/*.py")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("test_komutu", r.stderr)

    def test_kod_kartinda_test_komutu_bos_metin_reddedilir(self):
        r = self.cli("kart", "yeni", "--baslik", "x", "--basamak", "T2", "--sinif", "kod", "--tdd", "--kabul", "k",
                     "--yazma", "src/**", "--test-komutu", "   ", "--test-alani", "testler/*.py")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("test_komutu", r.stderr)

    def test_kod_kartinda_test_alani_eksik_reddedilir(self):
        r = self.cli("kart", "yeni", "--baslik", "x", "--basamak", "T2", "--sinif", "kod", "--tdd", "--kabul", "k",
                     "--yazma", "src/**", "--test-komutu", self.komut)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("test_alani", r.stderr)

    def test_toplu_kod_karti_alanlar_eksik_reddedilir(self):
        taban = {"baslik": "x", "basamak": "T2", "sinif": "kod", "tdd": True, "kabul_kriterleri": ["k"], "yazma_alani": ["src/**"]}
        for ek, beklenen in (({"test_alani": ["testler/*.py"]}, "test_komutu"),
                             ({"test_komutu": self.komut}, "test_alani"),
                             ({"test_komutu": self.komut, "test_alani": []}, "test_alani")):
            yol = os.path.join(self.proje, "toplu.json")
            with open(yol, "w", encoding="utf-8") as f:
                json.dump([dict(taban, **ek)], f)
            r = self.cli("kart", "toplu", yol)
            self.assertNotEqual(r.returncode, 0, ek)
            self.assertIn(beklenen, r.stderr, ek)

    def test_toplu_kod_karti_alanlarla_olusur(self):
        yol = os.path.join(self.proje, "toplu.json")
        with open(yol, "w", encoding="utf-8") as f:
            json.dump([{"baslik": "x", "basamak": "T2", "sinif": "kod", "tdd": True, "kabul_kriterleri": ["k"], "yazma_alani": ["src/**"],
                        "test_komutu": self.komut, "test_alani": ["testler/*.py"]}], f)
        r = self.cli("kart", "toplu", yol)
        self.assertEqual(r.returncode, 0, r.stderr)
        g = json.loads(r.stdout)[0]["id"]
        k = self.goster(g)
        self.assertEqual(k["test_komutu"], self.komut)
        self.assertEqual(k["test_alani"], ["testler/*.py"])
        self.assertIsNone(k["test_kilidi"])
        self.assertEqual(k["test_kosulari"], [])

    def test_kod_olmayan_kartta_alan_gerekmez_eski_davranis(self):
        r = self.cli("kart", "yeni", "--baslik", "x", "--basamak", "T1", "--sinif", "belge", "--kabul", "k", "--yazma", "docs/**")
        self.assertEqual(r.returncode, 0, r.stderr)
        r2 = self.cli("kart", "yeni", "--baslik", "y", "--basamak", "T1", "--kabul", "k", "--yazma", "docs/**")
        self.assertEqual(r2.returncode, 0, r2.stderr)

    # ---------------------------------------------------------- 2) test-kos
    def test_test_kos_kod_olmayan_kartta_hata(self):
        r = self.cli("kart", "yeni", "--baslik", "x", "--basamak", "T1", "--sinif", "belge", "--kabul", "k", "--yazma", "docs/**")
        g = r.stdout.strip()
        r = self.kos_t(g, "kirmizi")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotEqual(r.returncode, 4)

    def test_test_dosyasi_yoksa_hata(self):
        g = self.kod_karti(alanlar=("yok/*.py",))
        r = self.kos_t(g, "kirmizi")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("test dosyası yok", r.stderr)
        self.assertIsNone(self.goster(g)["test_kilidi"])

    def test_kirmizi_basarisiz_test_kilit_yazar(self):
        g = self.kod_karti()
        self.bayrak(False)
        r = self.kos_t(g, "kirmizi")
        self.assertEqual(r.returncode, 0, r.stderr)
        k = self.goster(g)
        kilit = k["test_kilidi"]
        self.assertIsNotNone(kilit)
        self.assertIn("zaman", kilit)
        self.assertEqual(sorted(kilit["dosyalar"]), ["testler/test_a.py", "testler/uyku.py"])
        for ozet in kilit["dosyalar"].values():
            self.assertRegex(ozet, r"^[0-9a-f]{64}$")
        self.assertEqual(len(k["test_kosulari"]), 1)
        kayit = k["test_kosulari"][0]
        self.assertEqual(kayit["asama"], "kirmizi")
        self.assertNotEqual(kayit["cikis_kodu"], 0)
        self.assertTrue(kayit["gecti"])
        for alan in ("zaman", "sira", "hash_tutarli", "sure_s", "cikti_kuyrugu"):
            self.assertIn(alan, kayit)
        self.assertIn("kosuldu", kayit["cikti_kuyrugu"])

    def test_kirmizi_kod_yokken_test_geciyorsa_basarisiz(self):
        g = self.kod_karti()
        self.bayrak(True)
        r = self.kos_t(g, "kirmizi")
        self.assertEqual(r.returncode, 4)
        k = self.goster(g)
        self.assertIsNone(k["test_kilidi"])
        self.assertEqual(len(k["test_kosulari"]), 1)
        self.assertEqual(k["test_kosulari"][0]["cikis_kodu"], 0)
        self.assertFalse(k["test_kosulari"][0]["gecti"])

    def test_kilitliyken_tekrar_kirmizi_hata(self):
        g = self.kirmizi_kilitle()
        once = self.goster(g)["test_kilidi"]
        r = self.kos_t(g, "kirmizi")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("kilitli", r.stderr)
        self.assertEqual(self.goster(g)["test_kilidi"], once)

    def test_yesil_kilit_yokken_hata(self):
        g = self.kod_karti()
        self.bayrak(True)
        r = self.kos_t(g, "yesil")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotEqual(r.returncode, 4)
        self.assertIn("kilit", r.stderr)

    def test_yesil_gecer_cikis_sifir(self):
        g = self.kirmizi_kilitle()
        self.bayrak(True)
        r = self.kos_t(g, "yesil")
        self.assertEqual(r.returncode, 0, r.stderr)
        kayit = self.goster(g)["test_kosulari"][-1]
        self.assertEqual(kayit["asama"], "yesil")
        self.assertEqual(kayit["cikis_kodu"], 0)
        self.assertTrue(kayit["hash_tutarli"])
        self.assertTrue(kayit["gecti"])

    def test_yesil_test_hala_basarisiz_cikis_dort(self):
        g = self.kirmizi_kilitle()
        r = self.kos_t(g, "yesil")  # bayrak yok → komut 1 döner
        self.assertEqual(r.returncode, 4)
        kayit = self.goster(g)["test_kosulari"][-1]
        self.assertNotEqual(kayit["cikis_kodu"], 0)
        self.assertTrue(kayit["hash_tutarli"])
        self.assertFalse(kayit["gecti"])

    def test_yesil_dosya_degisti_hash_tutarsiz(self):
        g = self.kirmizi_kilitle()
        self.bayrak(True)
        self.yaz("testler/test_a.py", BETIK + "# gevşetildi\n")
        r = self.kos_t(g, "yesil")
        self.assertEqual(r.returncode, 4)
        kayit = self.goster(g)["test_kosulari"][-1]
        self.assertEqual(kayit["cikis_kodu"], 0)
        self.assertFalse(kayit["hash_tutarli"])
        self.assertFalse(kayit["gecti"])

    def test_yesil_dosya_eklendi_hash_tutarsiz(self):
        g = self.kirmizi_kilitle()
        self.bayrak(True)
        self.yaz("testler/test_yeni.py", "pass\n")
        r = self.kos_t(g, "yesil")
        self.assertEqual(r.returncode, 4)
        kayit = self.goster(g)["test_kosulari"][-1]
        self.assertFalse(kayit["hash_tutarli"])
        self.assertFalse(kayit["gecti"])

    def test_yesil_dosya_silindi_hash_tutarsiz(self):
        g = self.kirmizi_kilitle()
        self.bayrak(True)
        self.sil("testler/uyku.py")
        r = self.kos_t(g, "yesil")
        self.assertEqual(r.returncode, 4)
        kayit = self.goster(g)["test_kosulari"][-1]
        self.assertFalse(kayit["hash_tutarli"])
        self.assertFalse(kayit["gecti"])

    def test_kosular_birikir_sira_artar(self):
        g = self.kirmizi_kilitle()
        self.kos_t(g, "yesil")
        self.bayrak(True)
        self.kos_t(g, "yesil")
        kosular = self.goster(g)["test_kosulari"]
        self.assertEqual(len(kosular), 3)
        siralar = [x["sira"] for x in kosular]
        self.assertEqual(siralar, sorted(set(siralar)))
        self.assertEqual([x["asama"] for x in kosular], ["kirmizi", "yesil", "yesil"])

    def test_cikti_kuyrugu_en_cok_2000_karakter(self):
        self.yaz("testler/test_a.py", UZUN_BETIK)
        g = self.kod_karti()
        self.bayrak(False)
        self.assertEqual(self.kos_t(g, "kirmizi").returncode, 0)
        kuyruk = self.goster(g)["test_kosulari"][0]["cikti_kuyrugu"]
        self.assertLessEqual(len(kuyruk), 2000)
        self.assertIn("SON_IZ", kuyruk)  # kuyruk: çıktının SONU

    def test_zaman_asimi_cikis_eksi_bir(self):
        g = self.kod_karti(komut=f'"{sys.executable}" testler/uyku.py')
        r = self.kos_t(g, "kirmizi", "--zaman-asimi", "1")
        self.assertEqual(r.returncode, 4)
        k = self.goster(g)
        kayit = k["test_kosulari"][0]
        self.assertEqual(kayit["cikis_kodu"], -1)
        self.assertFalse(kayit["gecti"])
        self.assertIsNone(k["test_kilidi"])

    def test_asama_gecersizse_hata(self):
        g = self.kod_karti()
        r = self.kos_t(g, "mavi")
        self.assertNotEqual(r.returncode, 0)

    # ---------------------------------------------------------- 3) test-kilit-ac
    def test_kilit_ac_yalniz_ana_ajan(self):
        g = self.kirmizi_kilitle()
        for kim in (ISCI, DENETCI):
            r = self.cli("kart", "test-kilit-ac", g, "--neden", "deneme", **kim)
            self.assertNotEqual(r.returncode, 0, kim)
        self.assertIsNotNone(self.goster(g)["test_kilidi"])

    def test_kilit_ac_ana_ajan_kilidi_kaldirir_ve_kaydeder(self):
        g = self.kirmizi_kilitle()
        once = len(self.goster(g)["gecmis"])
        r = self.cli("kart", "test-kilit-ac", g, "--neden", "test yanlış yazılmıştı", **ANA)
        self.assertEqual(r.returncode, 0, r.stderr)
        k = self.goster(g)
        self.assertIsNone(k["test_kilidi"])
        self.assertGreater(len(k["gecmis"]), once)
        self.assertIn("test yanlış yazılmıştı", json.dumps(k["gecmis"][-1], ensure_ascii=False))
        # kilit açıldıktan sonra kırmızı yeniden koşulabilir
        self.assertEqual(self.kos_t(g, "kirmizi").returncode, 0)

    def test_kilit_ac_neden_zorunlu(self):
        g = self.kirmizi_kilitle()
        r = self.cli("kart", "test-kilit-ac", g, **ANA)
        self.assertNotEqual(r.returncode, 0)

    # ---------------------------------------------------------- 4) denetim kapısı
    def test_onay_yesil_yokken_reddedilir(self):
        g = self.kirmizi_kilitle()
        self.is_bitti(g)
        r = self.onay(g)
        self.assertEqual(r.returncode, 3)
        self.assertIn("yeşil", r.stderr)
        self.assertEqual(self.goster(g)["denetimler"], [])

    def test_onay_hic_test_kosusu_yokken_reddedilir(self):
        g = self.kod_karti()
        self.is_bitti(g)
        r = self.onay(g)
        self.assertEqual(r.returncode, 3)
        self.assertIn("yeşil", r.stderr)

    def test_onay_yesil_is_bitti_oncesiyse_bayat_reddedilir(self):
        g = self.kirmizi_kilitle()
        self.bayrak(True)
        self.assertEqual(self.kos_t(g, "yesil").returncode, 0)
        self.is_bitti(g)  # yeşil koşu, son is-bitti'den ÖNCE kaldı
        r = self.onay(g)
        self.assertEqual(r.returncode, 3)
        self.assertIn("yeşil", r.stderr)
        self.assertEqual(self.goster(g)["denetimler"], [])

    def test_onay_son_yesil_basarisizsa_reddedilir(self):
        g = self.kirmizi_kilitle()
        self.is_bitti(g)
        self.assertEqual(self.kos_t(g, "yesil").returncode, 4)  # bayrak yok
        r = self.onay(g)
        self.assertEqual(r.returncode, 3)
        self.assertIn("yeşil", r.stderr)

    def test_onay_en_son_kayit_kirmizi_ise_reddedilir_yesil_yetmez(self):
        g = self.kirmizi_kilitle()
        self.is_bitti(g)
        self.bayrak(True)
        self.assertEqual(self.kos_t(g, "yesil").returncode, 0)
        # kilit açılıp yeniden kırmızı koşulursa en son kayıt kırmızıdır
        self.assertEqual(self.cli("kart", "test-kilit-ac", g, "--neden", "yeniden", **ANA).returncode, 0)
        self.bayrak(False)
        self.assertEqual(self.kos_t(g, "kirmizi").returncode, 0)
        r = self.onay(g)
        self.assertEqual(r.returncode, 3)
        self.assertIn("yeşil", r.stderr)

    def test_onay_yesil_sonrasi_test_dosyasi_degisirse_reddedilir(self):
        g = self.kirmizi_kilitle()
        self.is_bitti(g)
        self.bayrak(True)
        self.assertEqual(self.kos_t(g, "yesil").returncode, 0)
        self.yaz("testler/test_a.py", BETIK + "# yeşilden sonra oynandı\n")
        r = self.onay(g)
        self.assertEqual(r.returncode, 3)
        self.assertIn("yeşil", r.stderr)
        self.assertEqual(self.goster(g)["denetimler"], [])

    def test_onay_yesil_sonrasi_dosya_eklenirse_reddedilir(self):
        g = self.kirmizi_kilitle()
        self.is_bitti(g)
        self.bayrak(True)
        self.assertEqual(self.kos_t(g, "yesil").returncode, 0)
        self.yaz("testler/test_ek.py", "pass\n")
        self.assertEqual(self.onay(g).returncode, 3)

    def test_onay_yesil_sonrasi_dosya_silinirse_reddedilir(self):
        g = self.kirmizi_kilitle()
        self.is_bitti(g)
        self.bayrak(True)
        self.assertEqual(self.kos_t(g, "yesil").returncode, 0)
        self.sil("testler/uyku.py")
        self.assertEqual(self.onay(g).returncode, 3)

    def test_onay_taze_yesil_ile_kabul_edilir(self):
        g = self.kirmizi_kilitle()
        self.is_bitti(g)
        self.bayrak(True)
        self.assertEqual(self.kos_t(g, "yesil").returncode, 0)
        r = self.onay(g)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.goster(g)["denetimler"]), 1)
        self.assertEqual(self.goster(g)["denetimler"][0]["karar"], "onay")
        t = self.cli("kart", "teslim", g, "--ozet", "tamam", **ANA)
        self.assertEqual(t.returncode, 0, t.stderr)

    def test_ret_her_zaman_serbest(self):
        g = self.kirmizi_kilitle()
        self.is_bitti(g)
        r = self.ret(g)  # yeşil yok, yine de kabul
        self.assertEqual(r.returncode, 0, r.stderr)
        k = self.goster(g)
        self.assertEqual(k["denetimler"][-1]["karar"], "ret")

    def test_ret_bayat_yesil_ve_degismis_dosyada_da_serbest(self):
        g = self.kirmizi_kilitle()
        self.bayrak(True)
        self.assertEqual(self.kos_t(g, "yesil").returncode, 0)
        self.is_bitti(g)
        self.yaz("testler/test_a.py", BETIK + "# oynandı\n")
        self.assertEqual(self.ret(g).returncode, 0)

    def test_kod_olmayan_kartta_onay_eski_davranis(self):
        r = self.cli("kart", "yeni", "--baslik", "x", "--basamak", "T1", "--sinif", "belge", "--kabul", "k", "--yazma", "docs/**")
        g = r.stdout.strip()
        self.is_bitti(g)
        r = self.onay(g)
        self.assertEqual(r.returncode, 0, r.stderr)
        t = self.cli("kart", "teslim", g, "--ozet", "tamam", **ANA)
        self.assertEqual(t.returncode, 0, t.stderr)


if __name__ == "__main__":
    unittest.main()
