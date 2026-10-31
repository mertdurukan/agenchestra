"""Paralel koşu çekirdeği (P-041, ADR-0100): çekirdek sayısı türetme, pytest komutunu paralele çevirme,
seriye düşme ve genel paralel çalıştırıcı."""
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
sys.path.insert(0, SCRIPTS)
import ork_lib as L  # noqa: E402
import paralel_calistir  # noqa: E402
import paralel_kos as P  # noqa: E402

ORTAM = ("ORKESTRA_PARALEL_N", "ORKESTRA_PARALEL", "CI", "GITHUB_ACTIONS", "TF_BUILD")


class Temel(unittest.TestCase):
    def setUp(self):
        self.eski = {k: os.environ.pop(k, None) for k in ORTAM}
        self.proje = tempfile.mkdtemp()

    def tearDown(self):
        for k, v in self.eski.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v


class CekirdekSayisi(Temel):
    def test_cpu_kazanir_bellek_boldur(self):
        self.assertEqual(P.cekirdek_sayisi(self.proje, cekirdek=8, bellek_mb=64000), 8)

    def test_bellek_siniri_cpu_yu_asagi_ceker(self):
        # (4000 - 768 rezerv) // 300 = 10
        self.assertEqual(P.cekirdek_sayisi(self.proje, cekirdek=16, bellek_mb=4000), 10)

    def test_bellek_cok_dusukse_taban_en_az_isci(self):
        self.assertEqual(P.cekirdek_sayisi(self.proje, cekirdek=16, bellek_mb=100), 4)
        self.assertEqual(P.cekirdek_sayisi(self.proje, cekirdek=2, bellek_mb=100), 2)  # CPU tabandan azsa CPU

    def test_bellek_okunamazsa_cpu(self):
        with mock.patch.object(P, "kullanilabilir_bellek_mb", return_value=None):
            self.assertEqual(P.cekirdek_sayisi(self.proje, cekirdek=12), 12)

    def test_ust_sinir(self):
        self.assertEqual(P.cekirdek_sayisi(self.proje, cekirdek=128, bellek_mb=10**6), 32)

    def test_env_ezer_ve_bir_seri(self):
        os.environ["ORKESTRA_PARALEL_N"] = "3"
        self.assertEqual(P.cekirdek_sayisi(self.proje, cekirdek=16, bellek_mb=64000), 3)
        os.environ["ORKESTRA_PARALEL_N"] = "1"
        self.assertEqual(P.cekirdek_sayisi(self.proje, cekirdek=16, bellek_mb=64000), 1)

    def test_gecersiz_env_yok_sayilir(self):
        for v in ("0", "-2", "abc"):
            os.environ["ORKESTRA_PARALEL_N"] = v
            self.assertEqual(P.cekirdek_sayisi(self.proje, cekirdek=4, bellek_mb=64000), 4, v)

    def test_ci_ust_siniri(self):
        os.environ["CI"] = "true"
        self.assertEqual(P.cekirdek_sayisi(self.proje, cekirdek=16, bellek_mb=64000), 8)

    def test_proje_ayari_ezer_bozuk_dosya_varsayilana_duser(self):
        d = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(d)
        with open(os.path.join(d, "paralel_kosu.json"), "w", encoding="utf-8") as f:
            f.write('{"ust_sinir": 2}')
        self.assertEqual(P.cekirdek_sayisi(self.proje, cekirdek=16, bellek_mb=64000), 2)
        with open(os.path.join(d, "paralel_kosu.json"), "w", encoding="utf-8") as f:
            f.write("{bozuk")
        self.assertEqual(P.cekirdek_sayisi(self.proje, cekirdek=16, bellek_mb=64000), 16)

    def test_gercek_makinede_pozitif(self):
        self.assertGreaterEqual(P.cekirdek_sayisi(self.proje), 1)

    def test_test_paralel_varsayilani_otomatik(self):
        with open(os.path.join(SCRIPTS, "test_paralel.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("default=paralel_kos.cekirdek_sayisi()", src)
        self.assertNotIn("// 2)", src)


class KomutDonusumu(Temel):
    def setUp(self):
        super().setUp()
        os.makedirs(os.path.join(self.proje, "tests"))

    def cevir(self, komut):
        return L.test_komutu_paralel(komut, self.proje)

    def test_genis_pytest_cevrilir(self):
        for k in ("pytest tests", "python -m pytest tests", "py -3.13 -m pytest tests", "pytest -q tests", "pytest"):
            y = self.cevir(k)
            self.assertIn("test_paralel.py", y, k)
            self.assertNotIn(" -n ", y, k)  # sayıyı koşucu türetir

    def test_cok_dosya_cevrilir_tek_dosya_kalir(self):
        self.assertIn("test_paralel.py", self.cevir("pytest tests/a.py tests/b.py"))
        k = "pytest tests/a.py"
        self.assertEqual(self.cevir(k), k)

    def test_desteklenmeyen_bayrak_dugum_ve_baska_kosucu_aynen(self):
        for k in ("pytest -k x tests", "pytest -x tests", "pytest --lf tests", "pytest tests/a.py::t tests/b.py",
                  "python -m unittest discover", "npm test", "pytest tests && echo ok", "pytest tests | tail",
                  "ENV=1 pytest tests"):
            self.assertEqual(self.cevir(k), k, k)

    def test_kapatma(self):
        os.environ["ORKESTRA_PARALEL"] = "0"
        k = "pytest tests"
        self.assertEqual(self.cevir(k), k)


class SeriyeDusme(Temel):
    def test_kosucu_kullanim_hatasi_verirse_seri_komut_kosar(self):
        cagrilar = []

        def sahte(komut, cwd, zaman):
            cagrilar.append(komut)
            return (2, "yol bulunamadı", 0.1) if "test_paralel.py" in komut else (0, "seri ok", 0.2)

        os.makedirs(os.path.join(self.proje, "tests"))
        with mock.patch.object(L, "kabuk_kos", side_effect=sahte):
            kod, cikti, _ = L.paralel_kos("pytest tests", self.proje, 10)
        self.assertEqual((kod, cikti), (0, "seri ok"))
        self.assertEqual(len(cagrilar), 2)

    def test_paralel_dusen_sonucu_yutulmaz(self):
        os.makedirs(os.path.join(self.proje, "tests"))
        with mock.patch.object(L, "kabuk_kos", return_value=(1, "===== a.py (1.0 s) =====\nFAILED a.py::t", 1.0)) as m:
            kod, cikti, _ = L.paralel_kos("pytest tests", self.proje, 10)
        self.assertEqual(kod, 1)
        self.assertIn("FAILED a.py::t", cikti)
        self.assertEqual(m.call_count, 1)  # düşme seriye düşme sebebi değil

    def test_cevrilmeyen_komut_dogrudan_kabuk_kos(self):
        with mock.patch.object(L, "kabuk_kos", return_value=(0, "x", 0.0)) as m:
            L.paralel_kos("python -m unittest discover", self.proje, 10)
        m.assert_called_once()


class GenelCalistirici(unittest.TestCase):
    UYU = 'python -c "import time;time.sleep(0.7)"'

    def test_dort_komut_paralel_kosar(self):
        t = time.time()
        r = paralel_calistir.calistir([self.UYU] * 4, genislik=4)
        sure = time.time() - t
        self.assertEqual([x[1] for x in r], [0, 0, 0, 0])
        self.assertLess(sure, 2.4)  # seri en az 2,8 sn

    def test_cikti_komut_sirasinda_ve_hata_cikis_kodu(self):
        dus = 'python -c "import sys;sys.exit(3)"'
        r = paralel_calistir.calistir(['python -c "print(1)"', dus, 'python -c "print(2)"'], genislik=3)
        self.assertEqual(r[1][0], dus)
        self.assertEqual([x[1] for x in r], [0, 3, 0])
        self.assertEqual(paralel_calistir.main([dus]), 1)
        self.assertEqual(paralel_calistir.main(['python -c "print(1)"']), 0)

    def test_ilk_hatada_dur_baslamamis_isi_iptal_eder(self):
        r = paralel_calistir.calistir(['python -c "import sys;sys.exit(1)"', self.UYU, self.UYU],
                                      genislik=1, ilk_hatada_dur=True)
        self.assertEqual(r[0][1], 1)
        self.assertIsNone(r[1][1])
        self.assertIsNone(r[2][1])

    def test_zaman_asimi_kilitlenmeyi_keser(self):
        t = time.time()
        r = paralel_calistir.calistir(['python -c "import time;time.sleep(30)"'], genislik=1, zaman_asimi=1)
        self.assertEqual(r[0][1], -1)
        self.assertLess(time.time() - t, 20)

    def test_gecersiz_genislik_kullanim_hatasi(self):
        self.assertEqual(paralel_calistir.main(["-n", "0", 'python -c "print(1)"']), 2)


if __name__ == "__main__":
    unittest.main()
