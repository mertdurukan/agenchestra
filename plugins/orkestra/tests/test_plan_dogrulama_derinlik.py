"""ADR-0181: kanıt derinliği, kapsam iddiası, tanım kapsamlı arama ve kanıt izi.

Test adları T1-T3 seçicileriyle eşleşir: `-k "derinlik or kapsam"`, `-k tanim`, `-k iz`.
"""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_plan_dogrulama as TPD  # noqa: E402
from test_plan_dogrulama import madde, PD, TAMAM, YOK  # noqa: E402

TANIMLI = (
    "import functools\n"
    "\n"
    "def disarida():\n"
    "    return 'modul'\n"
    "\n"
    "class Secici:\n"
    "    @functools.lru_cache\n"
    "    def sec(self, x):\n"
    "        if x:\n"
    "            return 'modul'\n"
    "        return 'saglayici'\n"
    "\n"
    "    def diger(self):\n"
    "        return 'modul'\n"
)


class _Ortak(unittest.TestCase):
    """PlanDogrulamaBirim'in kurulumunu kullanır, testlerini yeniden koşmaz."""
    tearDown = TPD.PlanDogrulamaBirim.tearDown
    yaz = TPD.PlanDogrulamaBirim.yaz
    hesap = TPD.PlanDogrulamaBirim.hesap

    def setUp(self):
        TPD.PlanDogrulamaBirim.setUp(self)
        with open(os.path.join(self.d, "secici.py"), "w", encoding="utf-8", newline="\n") as f:
            f.write(TANIMLI)

    def iddia(self, s, no=1):
        return next(c for c in s["iddialar"] if c["no"] == no)


class DerinlikVeKapsam(_Ortak):
    # ------------------------------------------------------------ derinlik
    def test_derinlik_dosya_kaniti_yalniz_alinti_sayilir(self):
        s = self.hesap('- **C1** Dönüş 1.\n  - Kanıt: dosya kaynak.py:2 "return 1"')
        c = self.iddia(s)
        self.assertEqual(c["hesap"], TAMAM)
        self.assertEqual(c["derinlik"], PD.VARLIK)
        say = PD.sayim(s["iddialar"])
        self.assertEqual((say["tamam"], say["yuklem"], say["alinti"], say["alintili"]), (1, 0, 1, [1]))

    def test_derinlik_tam_sayili_ara_yuklemdir_esik_degildir(self):
        s = self.hesap('- **C1** Bir kez geçer.\n  - Kanıt: ara "DEGER" kaynak.py => 1')
        self.assertEqual(self.iddia(s)["derinlik"], PD.YUKLEM)
        s = self.hesap("- **C1** En az iki test.\n  - Kanıt: say testler/test_*.py => >=2")
        self.assertEqual(self.iddia(s)["derinlik"], PD.VARLIK)

    def test_derinlik_karar_blogu_iki_sayi_ve_adlari_yazar(self):
        iddialar = ('- **C1** Dönüş 1.\n  - Kanıt: dosya kaynak.py:2 "return 1"\n'
                    '- **C2** Bir kez geçer.\n  - Kanıt: ara "DEGER" kaynak.py => 1')
        yol = self.yaz(iddialar, madde(1, "C1, C2"))
        PD.yaz(yol)
        metin = open(yol, encoding="utf-8").read()
        self.assertIn("✅ 2: yüklemle 1, yalnız alıntı/varlık 1; ❌ 0", metin)
        self.assertIn("**Yorumu sınanmayan ✅ (yalnız alıntı/varlık):** C1", metin)
        self.assertIn("yorumu sınamaz", metin)  # yeni sınır metni

    # ------------------------------------------------------------ kapsam
    def test_kapsam_iddiasi_yalniz_alintiyla_reddedilir(self):
        s = self.hesap('- **C1** `sec` yalnız modüle bakar.\n  - Kanıt: dosya secici.py:10 "return \'modul\'"\n  - Risk: r')
        c = self.iddia(s)
        self.assertEqual(c["hesap"], YOK)
        self.assertEqual(c["kapsam"], "yalnız")
        self.assertIn("yüklem kanıtı ister", c["neden"])

    def test_kapsam_iddiasi_yuklemle_onaylanir(self):
        s = self.hesap('- **C1** Hiç geçmez.\n  - Kanıt: ara "YOKTUR" kaynak.py => 0')
        self.assertEqual(self.iddia(s)["hesap"], TAMAM)

    def test_kapsam_sozcugu_kod_ve_tirnak_icinde_sayilmaz(self):
        s = self.hesap('- **C1** `tüm_kayitlar` adı "hiçbiri" metnini taşır.\n  - Kanıt: dosya kaynak.py:2 "return 1"')
        self.assertEqual(self.iddia(s)["hesap"], TAMAM)
        self.assertEqual(self.iddia(s)["kapsam"], "")

    def test_kapsam_turkce_buyuk_harf_ve_ek_yakalanir(self):
        rx = PD.kapsam_derleyici(PD.ayar().get("kapsam_kaliplari"))
        self.assertEqual(PD.kapsam_sozcugu("Tümü modüle bakar", rx), "tümü")
        self.assertEqual(PD.kapsam_sozcugu("YALNIZCA modül", rx), "yalnızca")
        self.assertEqual(PD.kapsam_sozcugu("Modül seçimi değişir", rx), "")

    def test_kapsam_ayar_bossa_denetim_kapali(self):
        self.assertIsNone(PD.kapsam_derleyici([]))
        self.assertEqual(PD.kapsam_sozcugu("yalnız", None), "")


class TanimKapsamliArama(_Ortak):
    def test_tanim_icinde_sayar_disini_saymaz(self):
        s = self.hesap('- **C1** `sec` iki dal döner.\n  - Kanıt: ara "return" secici.py::Secici.sec => 2')
        self.assertEqual(self.iddia(s)["hesap"], TAMAM)
        s = self.hesap('- **C1** Modül dönüşü.\n  - Kanıt: ara "\'modul\'" secici.py::Secici.sec => 1')
        self.assertEqual(self.iddia(s)["hesap"], TAMAM)  # dosyada 3 kez, tanımda 1 kez

    def test_tanim_dekoratoru_kapsar(self):
        s = self.hesap('- **C1** Önbellekli.\n  - Kanıt: ara "lru_cache" secici.py::Secici.sec => 1')
        self.assertEqual(self.iddia(s)["hesap"], TAMAM)

    def test_tanim_yoksa_ya_da_py_degilse_reddedilir(self):
        s = self.hesap('- **C1** x.\n  - Kanıt: ara "return" secici.py::Secici.yok => 0\n  - Risk: r')
        self.assertEqual(self.iddia(s)["hesap"], YOK)
        self.assertIn("tanım bulunamadı", self.iddia(s)["neden"])
        with open(os.path.join(self.d, "not.md"), "w", encoding="utf-8") as f:
            f.write("x\n")
        s = self.hesap('- **C1** x.\n  - Kanıt: ara "x" not.md::bolum => 1\n  - Risk: r')
        self.assertEqual(self.iddia(s)["hesap"], YOK)

    def test_tanim_kapsamli_yuklem_kapsam_iddiasini_gecirir(self):
        s = self.hesap('- **C1** `sec` hiçbir yerde sağlayıcıya bakmaz.\n'
                       '  - Kanıt: ara "provider" secici.py::Secici.sec => 0')
        self.assertEqual(self.iddia(s)["hesap"], TAMAM)


class KanitIzi(_Ortak):
    def kur(self, iddialar, maddeler=None):
        yol = self.yaz(iddialar, maddeler or madde(1, "C1"))
        with open(os.path.join(self.d, "is.json"), "w", encoding="utf-8") as f:
            json.dump({"dogrulama": PD.DOGRULAMA_ADI}, f)
        PD.yaz(yol)
        return yol

    def degistir(self, ad, eski, yeni):
        p = os.path.join(self.d, ad)
        metin = open(p, encoding="utf-8").read()
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(metin.replace(eski, yeni))

    def onkosul(self):
        with mock.patch.dict(os.environ, {"ORKESTRA_DOGRULAMA_KAPISI": "1"}):
            return PD.todo_onkosulu(self.d)

    def test_iz_yazilir_ve_degismezse_guncel(self):
        yol = self.kur('- **C1** Dönüş 1.\n  - Kanıt: dosya kaynak.py:2 "return 1"')
        self.assertRegex(open(yol, encoding="utf-8").read(), r"\*\*Kanıt izi:\*\* C1=[0-9a-f]{8}")
        b = PD.blok_oku(yol)
        self.assertTrue(b["guncel"])
        self.assertEqual(b["degisen"], [])
        self.assertEqual(self.onkosul(), "")

    def test_iz_kanit_penceresi_degisince_bayat_ve_iddia_adiyla(self):
        yol = self.kur('- **C1** Dönüş 1.\n  - Kanıt: dosya kaynak.py:2 "return 1"')
        self.degistir("kaynak.py", "return 1", "return 2")
        b = PD.blok_oku(yol)
        self.assertFalse(b["guncel"])
        self.assertEqual(b["degisen"], [1])
        self.assertIn("kanıt değişti (C1)", self.onkosul())

    def test_iz_ilgisiz_satir_degisince_bayat_degil(self):
        with open(os.path.join(self.d, "uzun.py"), "w", encoding="utf-8", newline="\n") as f:
            f.write("".join(f"x{i} = {i}\n" for i in range(30)))
        yol = self.kur('- **C1** x2 iki.\n  - Kanıt: dosya uzun.py:3 "x2 = 2"')
        self.degistir("uzun.py", "x25 = 25", "x25 = 99")
        self.assertTrue(PD.blok_oku(yol)["guncel"])

    def test_iz_ara_yalniz_sonuc_degisince_bayat(self):
        yol = self.kur('- **C1** Bir kez.\n  - Kanıt: ara "DEGER" kaynak.py => 1')
        self.degistir("kaynak.py", "def a():", "def a():  # yorum")
        self.assertTrue(PD.blok_oku(yol)["guncel"])
        self.degistir("kaynak.py", "DEGER = 42", "DEGER = 42\nDEGER2 = 1")
        self.assertEqual(PD.blok_oku(yol)["degisen"], [1])

    def test_iz_satiri_olmayan_eski_blok_eskisi_gibi(self):
        yol = self.kur('- **C1** Dönüş 1.\n  - Kanıt: dosya kaynak.py:2 "return 1"')
        metin = open(yol, encoding="utf-8").read()
        import re
        metin = re.sub(r"\*\*Kanıt izi:\*\*[^\n]*\n\n", "", metin)
        with open(yol, "w", encoding="utf-8", newline="\n") as f:
            f.write(metin)
        self.degistir("kaynak.py", "return 1", "return 2")
        b = PD.blok_oku(yol)
        self.assertTrue(b["guncel"])
        self.assertEqual(b["degisen"], [])

    def test_iz_komut_kaniti_izde_yok(self):
        c = {"kanitlar": [{"tur": "komut", "deger": "`echo 1` => 1", "satir": 0}]}
        self.assertIsNone(PD.iddia_izi(c, [self.d]))


if __name__ == "__main__":
    unittest.main()
