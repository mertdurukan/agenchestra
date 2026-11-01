"""scripts/is_kaydi.todo_denetle_satiri önbelleği (I-328 P3): TTL, isler.json imzası, geri alma."""
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import is_kaydi  # noqa: E402


class TodoDenetleOnbellek(unittest.TestCase):
    def setUp(self):
        self.sd = tempfile.mkdtemp(prefix="ork_tdo_")
        self.kok = tempfile.mkdtemp(prefix="ork_tdo_kok_")
        with open(os.path.join(self.sd, "isler.json"), "w", encoding="utf-8") as f:
            f.write("{}")
        self.sayac = 0

    def tearDown(self):
        shutil.rmtree(self.sd, ignore_errors=True)
        shutil.rmtree(self.kok, ignore_errors=True)

    def tara(self, *a, **k):
        self.sayac += 1
        return [{"yol": "x", "tur": "bagsiz"}]

    def satir(self):
        with mock.patch.object(is_kaydi, "todo_denetle", side_effect=self.tara):
            return is_kaydi.todo_denetle_satiri(self.sd, self.kok)

    def test_ikinci_cagri_taramaz_ve_ayni_satir(self):
        s1 = self.satir()
        s2 = self.satir()
        self.assertEqual(self.sayac, 1)
        self.assertEqual(s1, s2)
        self.assertIn("1 todo dosyası", s1)

    def test_ikinci_cagri_hizli(self):
        self.satir()
        t = time.perf_counter()
        self.satir()
        self.assertLess(time.perf_counter() - t, 0.3)

    def test_isler_json_degisince_yeniden_tarar(self):
        self.satir()
        with open(os.path.join(self.sd, "isler.json"), "w", encoding="utf-8") as f:
            f.write('{"a": 1}')
        self.satir()
        self.assertEqual(self.sayac, 2)

    def test_ttl_dolunca_yeniden_tarar(self):
        self.satir()
        with mock.patch.object(is_kaydi.time, "time", return_value=time.time() + 601):
            self.satir()
        self.assertEqual(self.sayac, 2)

    def test_ttl_sifir_onbellegi_kapatir(self):
        with mock.patch.dict(os.environ, {"ORKESTRA_TODO_DENETLE_TTL": "0"}):
            self.satir()
            self.satir()
        self.assertEqual(self.sayac, 2)

    def test_farkli_kok_ayri_onbellek(self):
        self.satir()
        with mock.patch.object(is_kaydi, "todo_denetle", side_effect=self.tara):
            is_kaydi.todo_denetle_satiri(self.sd, self.kok + "_baska")
        self.assertEqual(self.sayac, 2)

    def test_sorun_yoksa_bos_metin_onbellege_alinir(self):
        with mock.patch.object(is_kaydi, "todo_denetle", return_value=[]) as m:
            self.assertEqual(is_kaydi.todo_denetle_satiri(self.sd, self.kok), "")
            self.assertEqual(is_kaydi.todo_denetle_satiri(self.sd, self.kok), "")
        self.assertEqual(m.call_count, 1)


if __name__ == "__main__":
    unittest.main()
