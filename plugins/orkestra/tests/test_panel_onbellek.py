"""Panel verisi: analitik._onbellek (son 7 gün sınıf dökümü + 5 dk katman sayacı) ve app.js'teki iki yüzey."""
import datetime
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

AD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AD, "..", "scripts"))
import analitik as A  # noqa: E402
import ork_lib as L  # noqa: E402

M = "claude-sonnet-5-5"


def satir(dt, mid, okuma, yazma, y5=0):
    return json.dumps({"type": "assistant", "timestamp": dt.isoformat().replace("+00:00", "Z"), "message": {
        "id": mid, "model": M, "usage": {"input_tokens": 5, "cache_read_input_tokens": okuma,
                                         "cache_creation_input_tokens": yazma, "output_tokens": 9,
                                         "cache_creation": {"ephemeral_5m_input_tokens": y5, "ephemeral_1h_input_tokens": yazma - y5}}}})


class OnbellekVerisi(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.proje = os.path.join(self.t.name, "proje")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(self.sd)
        self.oturum = os.path.join(self.t.name, "oturumlar")
        os.makedirs(self.oturum)
        self.yama = mock.patch.object(L, "proje_oturum_dizini", lambda p: self.oturum)
        self.yama.start()

    def tearDown(self):
        self.yama.stop()
        self.t.cleanup()

    def yaz(self, *satirlar):
        with open(os.path.join(self.oturum, "s1.jsonl"), "w", encoding="utf-8") as f:
            f.write("\n".join(satirlar) + "\n")

    def test_katman_sayaci_ve_sinif_dokumu(self):
        simdi = datetime.datetime.now(datetime.timezone.utc)
        self.yaz(satir(simdi - datetime.timedelta(minutes=30), "a", 200_000, 1_000),
                 satir(simdi - datetime.timedelta(minutes=20), "b", 0, 120_000, y5=120_000))
        o = A._onbellek(self.sd, self.proje)
        self.assertEqual(o["katman_5dk_son_24s"], 1)
        self.assertEqual(o["siniflar"]["katman_5dk"]["olay"], 1)
        self.assertEqual(o["olay_sayisi"], 1)
        self.assertTrue(os.path.exists(os.path.join(self.sd, "onbellek_kacak.json")))

    def test_katmansiz_veride_sayac_sifir(self):
        simdi = datetime.datetime.now(datetime.timezone.utc)
        self.yaz(satir(simdi - datetime.timedelta(minutes=30), "a", 200_000, 1_000),
                 satir(simdi - datetime.timedelta(minutes=20), "b", 200_000, 2_000))
        o = A._onbellek(self.sd, self.proje)
        self.assertEqual((o["katman_5dk_son_24s"], o["olay_sayisi"]), (0, 0))

    def test_degisen_dosya_yeniden_okunur(self):
        simdi = datetime.datetime.now(datetime.timezone.utc)
        self.yaz(satir(simdi - datetime.timedelta(minutes=30), "a", 200_000, 1_000))
        self.assertEqual(A._onbellek(self.sd, self.proje)["olay_sayisi"], 0)
        self.yaz(satir(simdi - datetime.timedelta(minutes=30), "a", 200_000, 1_000),
                 satir(simdi - datetime.timedelta(minutes=20), "b", 0, 120_000, y5=120_000))
        self.assertEqual(A._onbellek(self.sd, self.proje)["olay_sayisi"], 1)

    def test_okunamayan_kaynak_paneli_dusurmez(self):
        with mock.patch.dict(sys.modules, {"onbellek_kacak": None}):
            self.assertIsNone(A._onbellek(self.sd, self.proje))


class ArayuzYuzeyleri(unittest.TestCase):
    def test_app_js_gelen_kutusu_ve_maliyet_karti(self):
        with open(os.path.join(AD, "..", "assets", "app.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn("katman_5dk_son_24s > 0", js)
        self.assertIn("o.tur === 'katman5'", js)
        self.assertIn("${onbellekKarti(an.onbellek)}", js)


if __name__ == "__main__":
    unittest.main()
