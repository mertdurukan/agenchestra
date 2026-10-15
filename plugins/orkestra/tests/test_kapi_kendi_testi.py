"""Test kapısı kartın kendi testine baksın (G-015): `kart test-kos` kararı çıkış kodu yerine düşen test kimliklerinden.

`py -3.13 -m pytest plugins/orkestra/tests/test_kapi_kendi_testi.py -q`

Geçici proje + ayrı geçici test kökü. Test komutu gerçek pytest değil, küçük sahte bir betik: kökteki `cikti.txt`
içeriğini basar ve `kod.txt`'deki çıkış koduyla biter (hızlı, belirleyici). Kart A'nın test_alani `testler/test_a.py`;
ikinci kod kartı B'nin test_alani `testler/test_b.py` (durumu isleniyor/denetimde/teslim olarak ayarlanır).
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_cekirdek as C  # noqa: E402

BETIK = (
    "import sys\n"
    "print(open('cikti.txt', encoding='utf-8').read())\n"
    "sys.exit(int(open('kod.txt').read().strip()))\n"
)
ISCI = dict(ajan_id="w1", ajan_tipi="orkestra:isci-t2")

A_DUSER = "FAILED testler/test_a.py::T::t1 - AssertionError: assert 1 == 2"
B_DUSER = "FAILED testler/test_b.py::T::t9 - AssertionError: assert 1 == 2"
Z_DUSER = "FAILED testler/test_z.py::T::t5 - AssertionError: assert 1 == 2"
OZET1 = "=========== 1 failed, 4 passed in 0.10s ==========="
TOPLAMA = (
    "==================== ERRORS ====================\n"
    "_____ ERROR collecting testler/test_b.py _____\n"
    "E   SyntaxError: invalid syntax\n"
    "=========== short test summary info ===========\n"
    "ERROR testler/test_b.py\n"
    "!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!\n"
    "=========== 1 error in 0.05s ==========="
)
UNITTEST_A = (
    "F\n======================================================================\n"
    "FAIL: test_t1 (testler.test_a.T.test_t1)\n"
    "----------------------------------------------------------------------\n"
    "Traceback (most recent call last):\nAssertionError: 1 != 2\n\n"
    "----------------------------------------------------------------------\n"
    "Ran 1 test in 0.001s\n\nFAILED (failures=1)"
)
UNITTEST_B = UNITTEST_A.replace("test_a", "test_b").replace("test_t1", "test_t9")


def _yaz(kok, goreli, icerik):
    yol = os.path.join(kok, *goreli.split("/"))
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8", newline="\n") as f:
        f.write(icerik)
    return yol


class Taban(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_kendi_proje_")
        self.dis = tempfile.mkdtemp(prefix="ork_kendi_dis_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        r = C.kos([C.CLI, "baslat"], self.proje)
        self.assertEqual(r.returncode, 0, r.stderr)
        _yaz(self.dis, "betik.py", BETIK)
        _yaz(self.dis, "testler/test_a.py", "# a\n")
        _yaz(self.dis, "testler/test_b.py", "# b\n")
        self.komut = f'"{sys.executable}" betik.py'
        self.a = self.kod_karti("testler/test_a.py")

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)
        shutil.rmtree(self.dis, ignore_errors=True)

    def cli(self, *args, **kim):
        a = [C.CLI] + list(args)
        if kim:
            a += ["--ajan-id", kim["ajan_id"], "--ajan-tipi", kim["ajan_tipi"]]
        return C.kos(a, self.proje)

    def kod_karti(self, alan):
        r = self.cli("kart", "yeni", "--soru", "Kısa test sorusu?", "--baslik", "kart " + alan, "--basamak", "T2", "--sinif", "kod", "--tdd",
                     "--kabul", "çalışır", "--yazma", "src/**", "--test-komutu", self.komut,
                     "--test-alani", alan, "--test-koku", self.dis)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def kart(self, gid):
        with open(os.path.join(self.sd, "gorevler", gid + ".json"), encoding="utf-8") as f:
            return json.load(f)

    def durum_ayarla(self, gid, durum):
        yol = os.path.join(self.sd, "gorevler", gid + ".json")
        k = self.kart(gid)
        k["durum"] = durum
        with open(yol, "w", encoding="utf-8", newline="\n") as f:
            json.dump(k, f, ensure_ascii=False, indent=2)

    def ikinci_kart(self, durum="isleniyor"):
        b = self.kod_karti("testler/test_b.py")
        self.durum_ayarla(b, durum)
        return b

    def cikti(self, metin, kod):
        _yaz(self.dis, "cikti.txt", metin)
        _yaz(self.dis, "kod.txt", str(kod))

    def kos(self, asama, gid=None):
        return self.cli("kart", "test-kos", gid or self.a, "--asama", asama, **ISCI)

    def son(self, gid=None):
        return self.kart(gid or self.a)["test_kosulari"][-1]

    def kilitli(self, gid=None):
        return bool(self.kart(gid or self.a).get("test_kilidi"))

    def yesile_hazirla(self):
        """A'nın kendi testi düşerek kırmızı geçer ve kilitlenir."""
        self.cikti(A_DUSER + "\n" + OZET1, 1)
        r = self.kos("kirmizi")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.kilitli())

    def listede(self, alan, parca):
        return any(parca in json.dumps(x, ensure_ascii=False) for x in (alan or []))


# ------------------------------------------------------------------ kriter 1: kırmızı, yalnız başka dosya düşüyor
class KirmiziYalnizDis(Taban):
    def test_yalniz_baska_dosya_dusuyorsa_kirmizi_gecmez(self):
        self.ikinci_kart()
        self.cikti(B_DUSER + "\n" + OZET1, 1)
        r = self.kos("kirmizi")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertFalse(self.kilitli())
        self.assertFalse(self.son()["gecti"])

    def test_mesaj_test_alanindan_dusen_olmadigini_soyler(self):
        self.ikinci_kart()
        self.cikti(B_DUSER + "\n" + OZET1, 1)
        r = self.kos("kirmizi")
        self.assertIn("test_alani", r.stdout + r.stderr)

    def test_sahipsiz_dis_dusus_da_kirmizi_gecmez(self):
        self.cikti(Z_DUSER + "\n" + OZET1, 1)
        r = self.kos("kirmizi")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertFalse(self.kilitli())

    def test_kayitta_yabanci_dusen_sahibiyle_yazilir(self):
        b = self.ikinci_kart()
        self.cikti(B_DUSER + "\n" + OZET1, 1)
        self.kos("kirmizi")
        s = self.son()
        self.assertTrue(self.listede(s.get("yabanci_dusenler"), "test_b.py::T::t9"), s)
        self.assertTrue(self.listede(s.get("yabanci_dusenler"), b), s)
        self.assertFalse(s.get("dusenler"))


# ------------------------------------------------------------------ kriter 2: kırmızı, toplama hatası
class KirmiziToplamaHatasi(Taban):
    def test_pytest_cikis_2_toplama_hatasi_gecmez(self):
        self.cikti(TOPLAMA, 2)
        r = self.kos("kirmizi")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertFalse(self.kilitli())

    def test_cikis_1_olsa_da_during_collection_gecmez(self):
        self.cikti(TOPLAMA.replace("ERROR testler/test_b.py\n", A_DUSER + "\nERROR testler/test_b.py\n"), 1)
        r = self.kos("kirmizi")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertFalse(self.kilitli())

    def test_cikis_2_dusen_test_olsa_da_gecmez(self):
        self.cikti(A_DUSER + "\n!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!", 2)
        r = self.kos("kirmizi")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertFalse(self.kilitli())


# ------------------------------------------------------------------ kriter 3: kırmızı, kendi test düşüyor
class KirmiziKendiDusuyor(Taban):
    def test_test_alanindan_dusen_varsa_gecer_ve_kilit_olusur(self):
        # Bu davranış mevcut "çıkış kodu != 0" kuralıyla zaten geçer; dusenler alanı yeni (aşağıdaki testte).
        self.cikti(A_DUSER + "\n" + OZET1, 1)
        r = self.kos("kirmizi")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.kilitli())
        self.assertTrue(self.son()["gecti"])

    def test_dusenler_kayda_yazilir(self):
        self.cikti(A_DUSER + "\n" + OZET1, 1)
        self.kos("kirmizi")
        s = self.son()
        self.assertTrue(self.listede(s.get("dusenler"), "test_a.py::T::t1"), s)
        self.assertFalse(s.get("yabanci_dusenler"))
        self.assertFalse(s.get("ayristirilamadi"))

    def test_hem_kendi_hem_dis_dusuyorsa_gecer(self):
        b = self.ikinci_kart()
        self.cikti(A_DUSER + "\n" + B_DUSER + "\n" + OZET1, 1)
        r = self.kos("kirmizi")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.kilitli())
        s = self.son()
        self.assertTrue(self.listede(s.get("dusenler"), "test_a.py::T::t1"), s)
        self.assertTrue(self.listede(s.get("yabanci_dusenler"), "test_b.py::T::t9"), s)
        self.assertTrue(self.listede(s.get("yabanci_dusenler"), b), s)

    def test_hicbir_test_dusmuyor_cikis_0_kirmizi_gecmez(self):
        self.cikti("5 passed in 0.1s", 0)
        r = self.kos("kirmizi")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertFalse(self.kilitli())


# ------------------------------------------------------------------ kriter 4: yeşil, yalnız başka açık kartın düşüşü
class YesilYabanciDusen(Taban):
    def test_baska_acik_kartin_dusenleri_yesili_bozmaz(self):
        b = self.ikinci_kart("isleniyor")
        self.yesile_hazirla()
        self.cikti(B_DUSER + "\n" + OZET1, 1)
        r = self.kos("yesil")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        s = self.son()
        self.assertTrue(s["gecti"])
        self.assertTrue(self.listede(s.get("yabanci_dusenler"), "test_b.py::T::t9"), s)
        self.assertTrue(self.listede(s.get("yabanci_dusenler"), b), s)
        self.assertFalse(s.get("dusenler"))

    def test_denetimdeki_kart_da_acik_sayilir(self):
        self.ikinci_kart("denetimde")
        self.yesile_hazirla()
        self.cikti(B_DUSER + "\n" + OZET1, 1)
        r = self.kos("yesil")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_cikis_0_dis_dusus_yok_yesil_gecer(self):
        self.yesile_hazirla()
        self.cikti("5 passed in 0.1s", 0)
        r = self.kos("yesil")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.son()["gecti"])


# ------------------------------------------------------------------ kriter 5: yeşil, sahipsiz düşüş
class YesilSahipsizDusen(Taban):
    def test_sahipsiz_dis_dusus_yesili_bozar(self):
        self.yesile_hazirla()
        self.cikti(Z_DUSER + "\n" + OZET1, 1)
        r = self.kos("yesil")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertFalse(self.son()["gecti"])

    def test_sahipli_ve_sahipsiz_karisik_yesili_bozar(self):
        self.ikinci_kart()
        self.yesile_hazirla()
        self.cikti(B_DUSER + "\n" + Z_DUSER + "\n" + OZET1, 1)
        r = self.kos("yesil")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)

    def test_teslim_edilmis_kartin_testi_sahipsiz_sayilir(self):
        self.ikinci_kart("teslim")
        self.yesile_hazirla()
        self.cikti(B_DUSER + "\n" + OZET1, 1)
        r = self.kos("yesil")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)

    def test_iptal_kartin_testi_sahipsiz_sayilir(self):
        self.ikinci_kart("iptal")
        self.yesile_hazirla()
        self.cikti(B_DUSER + "\n" + OZET1, 1)
        r = self.kos("yesil")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)

    def test_kendi_testi_dusuyorsa_yesil_gecmez(self):
        self.ikinci_kart()
        self.yesile_hazirla()
        self.cikti(A_DUSER + "\n" + B_DUSER + "\n" + OZET1, 1)
        r = self.kos("yesil")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertTrue(self.listede(self.son().get("dusenler"), "test_a.py::T::t1"))

    def test_cikis_0_ama_kendi_testi_dusuyor_gecmez(self):
        # Tutarsız çıktı (çıkış 0 + kendi testi düşmüş): kapı düşen kimliğe güvenir ve geçmez.
        self.yesile_hazirla()
        self.cikti(A_DUSER, 0)
        r = self.kos("yesil")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)


# ------------------------------------------------------------------ kriter 6: yeşil, toplama hatası
class YesilToplamaHatasi(Taban):
    def test_toplama_hatasi_yesili_bozar(self):
        self.ikinci_kart()
        self.yesile_hazirla()
        self.cikti(TOPLAMA, 2)
        r = self.kos("yesil")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertFalse(self.son()["gecti"])

    def test_cikis_1_during_collection_yesili_bozar(self):
        self.ikinci_kart()
        self.yesile_hazirla()
        self.cikti(B_DUSER + "\n" + TOPLAMA, 1)
        r = self.kos("yesil")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)


# ------------------------------------------------------------------ kriter 7: ayrıştırılamayan çıktı
class Ayristirilamayan(Taban):
    METIN = "garip bir arac sonucu: tamam degil"

    def test_kirmizi_cikis_1_eski_davranisla_gecer_ve_isaretlenir(self):
        self.cikti(self.METIN, 1)
        r = self.kos("kirmizi")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.kilitli())
        self.assertIs(self.son().get("ayristirilamadi"), True)

    def test_kirmizi_cikis_0_eski_davranisla_gecmez(self):
        self.cikti(self.METIN, 0)
        r = self.kos("kirmizi")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertFalse(self.kilitli())
        self.assertIs(self.son().get("ayristirilamadi"), True)

    def test_yesil_cikis_0_gecer_ve_isaretlenir(self):
        self.cikti(self.METIN, 1)
        self.assertEqual(self.kos("kirmizi").returncode, 0)
        self.cikti(self.METIN, 0)
        r = self.kos("yesil")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIs(self.son().get("ayristirilamadi"), True)

    def test_yesil_cikis_1_gecmez(self):
        self.cikti(self.METIN, 1)
        self.assertEqual(self.kos("kirmizi").returncode, 0)
        r = self.kos("yesil")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertIs(self.son().get("ayristirilamadi"), True)

    def test_ayristirilan_cikti_isaretlenmez(self):
        self.cikti(A_DUSER + "\n" + OZET1, 1)
        self.kos("kirmizi")
        self.assertFalse(self.son().get("ayristirilamadi"))


# ------------------------------------------------------------------ kriter 8: unittest çıktısı
class UnittestBicimi(Taban):
    def test_unittest_kendi_testi_dusuyor_kirmizi_gecer(self):
        self.cikti(UNITTEST_A, 1)
        r = self.kos("kirmizi")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        s = self.son()
        self.assertTrue(self.listede(s.get("dusenler"), "test_t1"), s)
        self.assertFalse(s.get("ayristirilamadi"))

    def test_unittest_yalniz_baska_dosya_dusuyor_kirmizi_gecmez(self):
        self.ikinci_kart()
        self.cikti(UNITTEST_B, 1)
        r = self.kos("kirmizi")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertFalse(self.kilitli())
        self.assertTrue(self.listede(self.son().get("yabanci_dusenler"), "test_t9"))

    def test_unittest_yesil_yabanci_acik_kart_gecer(self):
        self.ikinci_kart()
        self.yesile_hazirla()
        self.cikti(UNITTEST_B, 1)
        r = self.kos("yesil")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.listede(self.son().get("yabanci_dusenler"), "test_t9"))

    def test_unittest_yesil_sahipsiz_gecmez(self):
        self.yesile_hazirla()
        self.cikti(UNITTEST_B, 1)  # test_b.py'nin açık sahibi yok
        r = self.kos("yesil")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)


# ------------------------------------------------------------------ denetim RET: subTest, yanlış toplama, gizli düşüş
SUB_A = "SUBFAILED(i=1) testler/test_a.py::T::t1 - AssertionError: assert 1 == 2"
TOPLAMA_ARAC = "!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!"
TOPLAMA_BASLIK = "_____ ERROR collecting testler/test_a.py _____\nE   SyntaxError: invalid syntax"
TOPLAMA_ERROR = "ERROR testler/test_a.py"


class SubTestDususu(Taban):
    def test_yesil_kendi_testi_subfailed_ile_dusuyor_acik_kart_da_dusuyor_gecmez(self):
        self.ikinci_kart()
        self.yesile_hazirla()
        self.cikti(SUB_A + "\n" + B_DUSER + "\n" + OZET1, 1)
        r = self.kos("yesil")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        s = self.son()
        self.assertFalse(s["gecti"])
        self.assertTrue(self.listede(s.get("dusenler"), "test_a.py::T::t1"), s)

    def test_kirmizi_kendi_testi_yalniz_subfailed_ile_dusuyor_gecer(self):
        self.cikti(SUB_A + "\n" + OZET1, 1)
        r = self.kos("kirmizi")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.kilitli())
        s = self.son()
        self.assertTrue(self.listede(s.get("dusenler"), "test_a.py::T::t1"), s)
        self.assertFalse(s.get("ayristirilamadi"))

    def test_subfailed_dis_dosya_yabanci_sayilir(self):
        b = self.ikinci_kart()
        self.cikti("SUBFAILED(i=1) testler/test_b.py::T::t9 - assert\n" + OZET1, 1)
        r = self.kos("kirmizi")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertTrue(self.listede(self.son().get("yabanci_dusenler"), b), self.son())


class ToplamaTespitiDogrulugu(Taban):
    def test_kaynak_satirindaki_metin_toplama_hatasi_sayilmaz(self):
        # Gerçek toplama hatası yok: test kendi assert mesajında bu metni içeriyor.
        cikti = (
            A_DUSER + "\n"
            "    def t1(self):\n"
            ">       assert 'x' == 'Interrupted: 1 error during collection'\n"
            "E       AssertionError: assert 'x' == 'Interrupted: 1 error during collection'\n"
            + OZET1
        )
        self.cikti(cikti, 1)
        r = self.kos("kirmizi")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.kilitli())
        self.assertTrue(self.listede(self.son().get("dusenler"), "test_a.py::T::t1"), self.son())

    def test_kirmizi_yalniz_interrupted_satiri_gecmez(self):
        self.cikti(TOPLAMA_ARAC, 1)
        r = self.kos("kirmizi")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertFalse(self.kilitli())

    def test_kirmizi_yalniz_error_collecting_basligi_gecmez(self):
        self.cikti(TOPLAMA_BASLIK, 1)
        r = self.kos("kirmizi")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertFalse(self.kilitli())

    def test_kirmizi_yalniz_error_dosya_satiri_gecmez(self):
        self.cikti(TOPLAMA_ERROR + " - SyntaxError", 1)
        r = self.kos("kirmizi")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertFalse(self.kilitli())

    def test_yesil_yalniz_interrupted_satiri_gecmez(self):
        self.yesile_hazirla()
        self.cikti(TOPLAMA_ARAC, 1)
        self.assertEqual(self.kos("yesil").returncode, 4)

    def test_yesil_yalniz_error_collecting_basligi_gecmez(self):
        self.yesile_hazirla()
        self.cikti(TOPLAMA_BASLIK, 1)
        self.assertEqual(self.kos("yesil").returncode, 4)

    def test_yesil_yalniz_error_dosya_satiri_gecmez(self):
        self.yesile_hazirla()
        self.cikti(TOPLAMA_ERROR + " - SyntaxError", 1)
        self.assertEqual(self.kos("yesil").returncode, 4)

    def test_yesil_cikis_0_olsa_da_toplama_hatasi_gecmez(self):
        self.yesile_hazirla()
        self.cikti(TOPLAMA_ARAC, 0)
        self.assertEqual(self.kos("yesil").returncode, 4)


class GizliDusus(Taban):
    def test_yesil_ozet_sayisi_ayristirilandan_fazlaysa_gecmez(self):
        b = self.ikinci_kart()
        self.yesile_hazirla()
        self.cikti(B_DUSER + "\n=========== 2 failed, 10 passed in 0.20s ===========", 1)
        r = self.kos("yesil")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        s = self.son()
        self.assertFalse(s["gecti"])
        self.assertTrue(self.listede(s.get("yabanci_dusenler"), b), s)  # ayrıştırma çalıştı; ret nedeni gizli düşüş

    def test_yesil_failed_ve_errors_toplami_ayristirilandan_fazlaysa_gecmez(self):
        self.ikinci_kart()
        self.yesile_hazirla()
        self.cikti(B_DUSER + "\n=========== 1 failed, 1 error, 10 passed in 0.20s ===========", 1)
        self.assertEqual(self.kos("yesil").returncode, 4)

    def test_yesil_ozet_sayisi_ayristirilanla_eslesirse_gecer(self):
        self.ikinci_kart()
        self.yesile_hazirla()
        self.cikti(B_DUSER + "\n=========== 1 failed, 10 passed in 0.20s ===========", 1)
        self.assertEqual(self.kos("yesil").returncode, 0)


class CokSatirliDusus(Taban):
    """Gizli düşüş kıyası düşüş SATIRI sayısıyla (tekilleştirilmemiş) yapılır; bir test birden çok satırla düşebilir."""

    def test_yesil_dis_test_uc_subfailed_satiriyla_dusuyor_gecer(self):
        b = self.ikinci_kart()
        self.yesile_hazirla()
        satirlar = "\n".join(f"SUBFAILED(i={i}) testler/test_b.py::T::t - assert" for i in range(3))
        self.cikti(satirlar + "\n=========== 3 failed, 1 passed in 0.20s ===========", 1)
        r = self.kos("yesil")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        s = self.son()
        self.assertTrue(s["gecti"])
        self.assertTrue(self.listede(s.get("yabanci_dusenler"), "test_b.py::T::t"), s)
        self.assertTrue(self.listede(s.get("yabanci_dusenler"), b), s)
        self.assertFalse(s.get("dusenler"))

    def test_yesil_ayni_kimlik_failed_ve_error_satiriyla_gecer(self):
        b = self.ikinci_kart()
        self.yesile_hazirla()
        self.cikti("FAILED testler/test_b.py::T::t - assert 1 == 2\n"
                   "ERROR testler/test_b.py::T::t - teardown hatasi\n"
                   "=========== 1 failed, 1 error, 3 passed in 0.20s ===========", 1)
        r = self.kos("yesil")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        s = self.son()
        self.assertTrue(self.listede(s.get("yabanci_dusenler"), b), s)
        self.assertFalse(s.get("dusenler"))

    def test_yesil_satir_sayisi_ozetten_azsa_hala_gizli_dusus(self):
        # Üç SUBFAILED satırı var ama özet 4 diyor: bir düşüş görünmüyor.
        self.ikinci_kart()
        self.yesile_hazirla()
        satirlar = "\n".join(f"SUBFAILED(i={i}) testler/test_b.py::T::t - assert" for i in range(3))
        self.cikti(satirlar + "\n=========== 4 failed, 1 passed in 0.20s ===========", 1)
        self.assertEqual(self.kos("yesil").returncode, 4)


if __name__ == "__main__":
    unittest.main()
