"""test_paralel: dosya başına alt süreç, N işçili havuz, zaman aşımı, FAILED satırı korunumu, çıkış kodları, --en-yavas."""
import contextlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
sys.path.insert(0, SCRIPTS)
import ork_lib as L  # noqa: E402

KOSUCU = os.path.join(SCRIPTS, "test_paralel.py")

GECEN = "def test_a():\n    assert 1 + 1 == 2\n\ndef test_b():\n    assert 'x'.upper() == 'X'\n"
DUSEN = "def test_dusen_ozel():\n    assert 1 == 2\n"
UYKU = "import time\n\ndef test_uyku():\n    time.sleep(1)\n"
ASIRI = "import time\n\ndef test_asiri_yavas():\n    time.sleep(60)\n"


def kos(args, zaman=120):
    t = time.time()
    p = subprocess.run([sys.executable, KOSUCU, *args], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=zaman)
    return p.returncode, (p.stdout or "") + (p.stderr or ""), time.time() - t


class Temel(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = self._tmp.name
        self.addCleanup(self._tmp.cleanup)

    def yaz(self, ad, icerik):
        yol = os.path.join(self.d, ad)
        with open(yol, "w", encoding="utf-8") as f:
            f.write(icerik)
        return yol


class Cikis(Temel):
    def test_hepsi_gecerse_sifir(self):
        self.yaz("test_bir.py", GECEN)
        self.yaz("test_iki.py", GECEN)
        kod, cikti, _ = kos([self.d])
        self.assertEqual(kod, 0, cikti)
        self.assertEqual(L.pytest_dusenler(cikti), [])

    def test_biri_dusunce_bir_ve_failed_satiri_korunur(self):
        self.yaz("test_bir.py", GECEN)
        self.yaz("test_dus.py", DUSEN)
        kod, cikti, _ = kos([self.d])
        self.assertEqual(kod, 1, cikti)
        self.assertRegex(cikti, r"(?m)^FAILED \S*test_dus\.py::test_dusen_ozel")
        dus = L.pytest_dusenler(cikti)
        self.assertEqual(len(dus), 1, dus)
        self.assertTrue(dus[0].endswith("test_dus.py::test_dusen_ozel"), dus)

    def test_dosya_listesi_argumani(self):
        a = self.yaz("test_a.py", GECEN)
        b = self.yaz("test_b.py", DUSEN)
        kod, cikti, _ = kos([a, b])
        self.assertEqual(kod, 1, cikti)
        self.assertEqual(len(L.pytest_dusenler(cikti)), 1)
        kod2, cikti2, _ = kos([a])
        self.assertEqual(kod2, 0, cikti2)

    def test_dizin_yalniz_test_dosyalarini_kosar(self):
        self.yaz("test_ok.py", GECEN)
        self.yaz("yardimci.py", DUSEN)  # test_*.py değil: koşulmamalı
        kod, cikti, _ = kos([self.d])
        self.assertEqual(kod, 0, cikti)

    def test_cikti_dosya_siralidir(self):
        self.yaz("test_a_yavas.py", "import time\n\ndef test_x():\n    time.sleep(1.5)\n    assert 1 == 2\n")
        self.yaz("test_b_hizli.py", "def test_y():\n    assert 1 == 3\n")
        kod, cikti, _ = kos(["-n", "2", self.d])
        self.assertEqual(kod, 1, cikti)
        self.assertLess(cikti.index("test_a_yavas.py"), cikti.index("test_b_hizli.py"))

    def test_toplama_hatasi_dusus_sayilir(self):
        self.yaz("test_bozuk.py", "def test_x(:\n")
        kod, cikti, _ = kos([self.d])
        self.assertEqual(kod, 1, cikti)

    def test_olmayan_yol_sifir_donmez(self):
        kod, cikti, _ = kos([os.path.join(self.d, "yok_dizin")])
        self.assertNotEqual(kod, 0, cikti)

    def test_bos_dizin_sifir_donmez(self):
        kod, cikti, _ = kos([self.d])
        self.assertNotEqual(kod, 0, "koşulacak test yokken sahte başarı olmamalı: " + cikti)


class ZamanAsimi(Temel):
    def test_zaman_asimi_bir_doner_digerleri_kosar(self):
        self.yaz("test_a_gecen.py", GECEN)
        self.yaz("test_b_asiri.py", ASIRI)
        self.yaz("test_c_gecen.py", GECEN)
        # Eşik, hızlı dosyaların yük altında bile bitebileceği kadar geniş; yavaş dosya (300 sn uyku)
        # eşikten bağımsız olarak her koşulda aşar. Süre sınırı eşiğe değil uykuya göre: öldürülmediyse >= 300.
        kod, cikti, sure = kos(["--zaman-asimi", "20", "-n", "3", self.d])
        self.assertEqual(kod, 1, cikti)
        self.assertIn("zaman aşımı", cikti)
        self.assertLess(sure, 120, "zaman aşımı alt süreci öldürmeli")
        satir = [s for s in cikti.splitlines() if "zaman aşımı" in s]
        self.assertTrue(any("test_b_asiri.py" in s for s in satir), satir)
        self.assertFalse(any("test_a_gecen.py" in s for s in satir), satir)
        self.assertGreaterEqual(len(re.findall(r"2 passed", cikti)), 2, cikti)

    def test_zaman_asimi_yoksa_yavas_dosya_gecer(self):
        self.yaz("test_u.py", UYKU)
        kod, cikti, _ = kos(["--zaman-asimi", "30", self.d])
        self.assertEqual(kod, 0, cikti)
        self.assertNotIn("zaman aşımı", cikti)


class Paralellik(Temel):
    def test_n1_ve_n4_ayni_sonuc(self):
        self.yaz("test_g.py", GECEN)
        self.yaz("test_d.py", DUSEN)
        self.yaz("test_u.py", UYKU)
        k1, c1, _ = kos(["-n", "1", self.d])
        k4, c4, _ = kos(["-n", "4", self.d])
        self.assertEqual(k1, 1)
        self.assertEqual(k1, k4)
        self.assertEqual(L.pytest_dusenler(c1), L.pytest_dusenler(c4))
        self.assertEqual(len(L.pytest_dusenler(c4)), 1)

    def test_n4_dort_dosya_n1_suresinin_yuzde_60_alti(self):
        for i in range(4):
            self.yaz(f"test_u{i}.py", UYKU)
        k1, c1, sure_n1 = kos(["-n", "1", self.d])
        self.assertEqual(k1, 0, c1)
        k4, c4, sure_n4 = kos(["-n", "4", self.d])
        self.assertEqual(k4, 0, c4)
        print(f"[olcum] sure_n1={sure_n1:.2f} sure_n4={sure_n4:.2f}")
        self.assertLess(sure_n4, 0.6 * sure_n1,
                        f"-n 4 süresi -n 1'in %60'ından kısa olmalı: sure_n4={sure_n4:.2f} sure_n1={sure_n1:.2f}")

    def test_n1_seri_calisir(self):
        for i in range(2):
            self.yaz(f"test_u{i}.py", UYKU)
        kod, cikti, sure = kos(["-n", "1", self.d])
        self.assertEqual(kod, 0, cikti)
        self.assertGreaterEqual(sure, 2.0, f"-n 1 seri olmalı, süre={sure:.2f}")

    def test_gecersiz_n_reddedilir(self):
        self.yaz("test_g.py", GECEN)
        for deger in ("0", "-2", "abc"):
            kod, cikti, _ = kos(["-n", deger, self.d])
            self.assertNotEqual(kod, 0, f"-n {deger}: {cikti}")


class EnYavas(Temel):
    def test_en_yavas_k_dosyayi_sureyle_basar(self):
        self.yaz("test_hizli.py", GECEN)
        self.yaz("test_orta.py", "import time\n\ndef test_o():\n    time.sleep(1)\n")
        self.yaz("test_yavas.py", "import time\n\ndef test_y():\n    time.sleep(2.5)\n")
        kod, cikti, _ = kos(["--en-yavas", "2", self.d])
        self.assertEqual(kod, 0, cikti)
        self.assertIn("en yavaş", cikti.lower(), cikti)
        bolum = cikti[cikti.lower().rfind("en yavaş"):]
        self.assertIn("test_yavas.py", bolum)
        self.assertIn("test_orta.py", bolum)
        self.assertNotIn("test_hizli.py", bolum)
        self.assertLess(bolum.index("test_yavas.py"), bolum.index("test_orta.py"))
        self.assertRegex(bolum, r"\d+(?:[.,]\d+)?\s*s")

    def test_en_yavas_verilmezse_bolum_yok(self):
        self.yaz("test_g.py", GECEN)
        kod, cikti, _ = kos([self.d])
        self.assertEqual(kod, 0, cikti)
        self.assertNotIn("en yavaş", cikti.lower())


class BaslatmaSirasi(unittest.TestCase):
    def test_yavas_once_bilinmeyen_en_once_esitlikte_sira(self):
        import test_paralel as T
        ab = os.path.abspath
        sureler = {ab("a.py"): 1.0, ab("b.py"): 9.0, ab("c.py"): 1.0}
        self.assertEqual(T.baslatma_sirasi(["a.py", "b.py", "c.py", "yeni.py"], sureler), ["yeni.py", "b.py", "a.py", "c.py"])
        self.assertEqual(T.baslatma_sirasi(["a.py", "b.py"], {}), ["a.py", "b.py"])


class Parcalama(unittest.TestCase):
    """Önceki süresi eşiği aşan dosya test düğümlerine bölünür; kısa ya da süresi bilinmeyen dosya bölünmez."""

    def test_esik_alti_ve_bilinmeyen_bolunmez(self):
        import test_paralel as T
        self.assertIsNone(T.parcalara_bol("a.py", None, 8))
        self.assertIsNone(T.parcalara_bol("a.py", T.PARCALA_ESIK_SN - 1, 8))
        self.assertIsNone(T.parcalara_bol("a.py", 500.0, 1))

    def test_dugumler_eksiksiz_ve_ayrik_dagilir(self):
        import test_paralel as T
        dugumler = [f"x.py::T::t{i}" for i in range(10)]
        with mock.patch.object(T, "dugumleri_topla", return_value=dugumler):
            g = T.parcalara_bol("x.py", 90.0, 8)  # 90 sn / 30 sn hedef = 3 parça
        self.assertEqual(len(g), 3)
        self.assertEqual(sorted(sum(g, [])), sorted(dugumler))

    def test_parca_sayisi_dugum_sayisini_asmaz(self):
        import test_paralel as T
        with mock.patch.object(T, "dugumleri_topla", return_value=["x.py::t0"]):
            self.assertIsNone(T.parcalara_bol("x.py", 500.0, 8))

    def test_bolunmus_dosya_tum_testleri_kosar(self):
        d = tempfile.mkdtemp(prefix="ork_parca_")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        with open(os.path.join(d, "test_b.py"), "w", encoding="utf-8") as f:
            f.write("def test_a():\n    pass\n\ndef test_b():\n    pass\n\ndef test_c():\n    assert False\n")
        import test_paralel as T
        dosya = os.path.join(d, "test_b.py")
        with mock.patch.object(T, "sureleri_oku", return_value={os.path.abspath(dosya): 100.0}), \
                mock.patch.object(T, "sureleri_yaz"), contextlib.redirect_stdout(io.StringIO()) as buf:
            kod = T.main(["-n", "3", dosya])
        cikti = buf.getvalue()
        self.assertEqual(kod, 1, cikti)
        self.assertRegex(cikti, r"(?m)^FAILED \S*test_b\.py::test_c")
        self.assertIn("1 dosya, 1 düşen", cikti)


if __name__ == "__main__":
    unittest.main()
