"""`orkestra is belge` / `is baglanti`, belge şablonları ve K-003 bağlantı satırları. Geçici proje dizininde koşar."""
import datetime
import os
import re
import sys
import time
import unittest

import test_cekirdek as TC

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import is_kaydi as K  # noqa: E402


class IsBelge(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown
    cli = TC.Cekirdek.cli

    def ac(self, alt="is1"):
        klasor = os.path.join(self.proje, alt)
        r = self.cli("is", "ac", "Deneme işi", "--klasor", klasor)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip(), klasor

    def test_is_ac_plan_sablonu_zengin(self):
        _, klasor = self.ac()
        with open(os.path.join(klasor, "plan.md"), encoding="utf-8") as f:
            plan = f.read()
        self.assertTrue(plan.startswith("# Deneme işi\n"))
        basliklar = re.findall(r"^## (.+)$", plan, re.M)
        self.assertEqual(basliklar, ["Amaç", "Kararlar", "Kapsam", "Riskler", "Doğrulanamayanlar"])
        self.assertNotIn("{", plan)

    def test_belge_ozet_olusturur_ve_baglanti_basar(self):
        i, klasor = self.ac()
        r = self.cli("is", "belge", i, "ozet")
        self.assertEqual(r.returncode, 0, r.stderr)
        gun = datetime.datetime.now().strftime("%Y%m%d")
        yol = os.path.join(klasor, f"calisma_ozeti_{gun}.md")
        self.assertTrue(os.path.exists(yol))
        satirlar = r.stdout.splitlines()
        self.assertTrue(satirlar[0].startswith("oluşturuldu: "), satirlar[0])
        self.assertEqual(satirlar[1], "plan dosyası: [plan_gorunum.md](is1/plan_gorunum.md)")
        self.assertEqual(satirlar[2], "to-do dosyası: [todo_gorunum.md](is1/todo_gorunum.md)")
        self.assertEqual(satirlar[3], f"çalışma özeti: [calisma_ozeti_{gun}.md](is1/calisma_ozeti_{gun}.md)")
        with open(yol, encoding="utf-8") as f:
            metin = f.read()
        self.assertIn("**Ölçüm saati:**", metin)
        self.assertIn(datetime.datetime.now().strftime("%d.%m.%Y"), metin)
        self.assertNotIn("{tarih}", metin)
        self.assertNotIn("{baslik}", metin)

    def test_belge_var_olani_ezmez(self):
        i, klasor = self.ac()
        self.cli("is", "belge", i, "bulgu")
        yol = os.path.join(klasor, "bulgu.md")
        with open(yol, "w", encoding="utf-8") as f:
            f.write("elle yazılmış içerik\n")
        r = self.cli("is", "belge", i, "bulgu")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.startswith("var, değiştirilmedi: "), r.stdout)
        with open(yol, encoding="utf-8") as f:
            self.assertEqual(f.read(), "elle yazılmış içerik\n")
        self.assertIn("bulgu: [bulgu.md](is1/bulgu.md)", r.stdout)

    def test_belge_plan_var_olan_plani_ezmez(self):
        i, klasor = self.ac()
        with open(os.path.join(klasor, "plan.md"), "w", encoding="utf-8") as f:
            f.write("# özgün plan\n")
        r = self.cli("is", "belge", i, "plan")
        self.assertTrue(r.stdout.startswith("var, değiştirilmedi: "), r.stdout)
        with open(os.path.join(klasor, "plan.md"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "# özgün plan\n")

    def test_belge_bilinmeyen_tur_ve_olmayan_is(self):
        i, _ = self.ac()
        self.assertNotEqual(self.cli("is", "belge", i, "gizli").returncode, 0)
        self.assertNotEqual(self.cli("is", "belge", "I-999", "ozet").returncode, 0)

    def test_baglanti_plan_todo_ve_yakin_belgeler(self):
        i, klasor = self.ac()
        r = self.cli("is", "baglanti", i)
        self.assertEqual(r.stdout.splitlines(), ["plan dosyası: [plan_gorunum.md](is1/plan_gorunum.md)",
                                                 "to-do dosyası: [todo_gorunum.md](is1/todo_gorunum.md)"])
        yeni = os.path.join(klasor, "rapor.md")
        eski = os.path.join(klasor, "bulgu.md")
        for yol in (yeni, eski, os.path.join(klasor, "devir.md"), os.path.join(klasor, "kod.py")):
            with open(yol, "w", encoding="utf-8") as f:
                f.write("x\n")
        gecen = time.time() - 5 * 3600
        os.utime(eski, (gecen, gecen))
        s = self.cli("is", "baglanti", i).stdout.splitlines()
        self.assertEqual(s[2:], ["rapor: [rapor.md](is1/rapor.md)"])  # eski bulgu, devir.md ve kod.py yok
        s = self.cli("is", "baglanti", i, "--tumu").stdout.splitlines()
        self.assertEqual(s[2:], ["bulgu: [bulgu.md](is1/bulgu.md)", "rapor: [rapor.md](is1/rapor.md)"])
        s = self.cli("is", "baglanti", i, "--son", "400").stdout.splitlines()
        self.assertEqual(len(s), 4)

    def test_baglanti_ek_dosya_ve_tekrar_yok(self):
        i, klasor = self.ac()
        ek = os.path.join(klasor, "notlar_ozet.md")
        with open(ek, "w", encoding="utf-8") as f:
            f.write("x\n")
        s = self.cli("is", "baglanti", i, "--ek", ek, "--ek", os.path.join(klasor, "plan.md")).stdout.splitlines()
        self.assertEqual(s, ["plan dosyası: [plan_gorunum.md](is1/plan_gorunum.md)", "to-do dosyası: [todo_gorunum.md](is1/todo_gorunum.md)",
                             "çalışma özeti: [notlar_ozet.md](is1/notlar_ozet.md)"])

    def test_devam_baglanti_satirlari_icerir(self):
        i, _ = self.ac()
        r = self.cli("is", "devam", i)
        self.assertIn("plan dosyası: [plan_gorunum.md](is1/plan_gorunum.md)", r.stdout)
        self.assertIn("to-do dosyası: [todo_gorunum.md](is1/todo_gorunum.md)", r.stdout)


class BaglantiSatiri(unittest.TestCase):
    def test_goreli_yol_cwd_den_bagimsiz_ve_eğik_çizgili(self):
        kok = os.path.join(os.path.abspath(os.sep), "proje")
        yol = os.path.join(kok, "Claude_Orkestrasyon", "021-x", "plan.md")
        eski = os.getcwd()
        try:
            os.chdir(os.path.abspath(os.sep))
            self.assertEqual(K.baglanti_satiri("plan dosyası", yol, kok),
                             "plan dosyası: [plan.md](Claude_Orkestrasyon/021-x/plan.md)")
        finally:
            os.chdir(eski)

    def test_bosluklu_yol_acili_parantezle(self):
        kok = os.path.join(os.path.abspath(os.sep), "proje")
        s = K.baglanti_satiri("rapor", os.path.join(kok, "bir klasör", "rapor.md"), kok)
        self.assertEqual(s, "rapor: [rapor.md](<bir klasör/rapor.md>)")

    def test_kok_disi_yol_mutlak_kalir(self):
        kok = os.path.join(os.path.abspath(os.sep), "proje")
        dis = os.path.join(os.path.abspath(os.sep), "baska", "rapor.md")
        s = K.baglanti_satiri("rapor", dis, kok)
        self.assertIn("baska/rapor.md", s)
        self.assertNotIn("..", s)


class Sablonlar(unittest.TestCase):
    def test_her_tur_icin_sablon_var_ve_yer_tutucular_dolar(self):
        simdi = datetime.datetime(2026, 10, 16, 11, 30)
        for tur, (dosya, _hedef, _etiket) in K.BELGE_TURLERI.items():
            metin = K.sablon_metni(dosya, "Başlık {x}", simdi)
            self.assertTrue(metin.startswith("# Başlık {x}"), tur)
            for yer in ("{tarih}", "{saat}", "{baslik}"):
                self.assertNotIn(yer, metin, f"{tur}: {yer}")
            self.assertTrue(metin.endswith("\n"), tur)

    def test_sablonlar_k005_duzeninde(self):
        """Bir satırda iki kalın etiket yok; kalın etiket satırı değerle birleşik değil (etiket ayrı paragraf)."""
        for tur, (dosya, _h, _e) in K.BELGE_TURLERI.items():
            for no, satir in enumerate(K.sablon_metni(dosya, "T").splitlines(), 1):
                self.assertLessEqual(len(re.findall(r"\*\*[^*]+\*\*", satir)), 1, f"{dosya}:{no}")
                if re.match(r"^\*\*[^*]+:\*\*", satir):
                    self.assertTrue(satir.endswith(":**"), f"{dosya}:{no} etiket değerle aynı satırda")

    def test_plan_dosyasi_yoksa_yerlesik_yedek(self):
        eski = K.SABLON_DIZINI
        K.SABLON_DIZINI = os.path.join(eski, "yok")
        try:
            self.assertEqual(K.sablon_metni("plan.md", "T"), "# T\n\n## Amaç\n\n## Kararlar\n")
            with self.assertRaises(FileNotFoundError):
                K.sablon_metni("rapor.md", "T")
        finally:
            K.SABLON_DIZINI = eski


if __name__ == "__main__":
    unittest.main()
