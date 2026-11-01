"""P9 (I-026): SessionStart hızlı yol — doktor yalnız gerektiğinde, arka planda, proje açık olmasa da başlar."""
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import cfg  # noqa: E402
import hook  # noqa: E402


class HizliYolTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ev = os.path.join(self.tmp.name, "ev")
        p = mock.patch.dict(os.environ, {"ORKESTRA_HOME": self.ev})
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop("ORKESTRA_DOKTOR_OTOMATIK", None)  # conftest '0' koyar; bu testler başlatıcıyı sınar

    def isaretli(self, surum="1.0"):
        cfg.makine_yaz({"python": "p"})
        cfg.makine_isaretle({"zaman": "z", "surum": surum, "ozet": {}, "zorunlu_hata": []})

    def test_config_yoksa(self):
        self.assertEqual(cfg.doktor_gerekli(), "config yok")

    def test_parmak_izi_degisince(self):
        self.isaretli()
        with mock.patch.object(cfg, "parmak_izi", return_value="baska"):
            self.assertEqual(cfg.doktor_gerekli(), "parmak izi")

    def test_doktor_hic_kosmamissa(self):
        cfg.makine_yaz({"python": "p"})
        self.assertEqual(cfg.doktor_gerekli(), "doktor yok")

    def test_surum_degisince_ve_bilinmiyorsa_sayilmaz(self):
        self.isaretli("1.0")
        with mock.patch.object(cfg, "hizli_surum", return_value="2.0"):
            self.assertEqual(cfg.doktor_gerekli(), "sürüm")
        with mock.patch.object(cfg, "hizli_surum", return_value="1.0"):
            self.assertIsNone(cfg.doktor_gerekli())
        with mock.patch.object(cfg, "hizli_surum", return_value=None):  # sürüm bilinmiyor: tetikleme yok
            self.assertIsNone(cfg.doktor_gerekli())

    def test_hizli_yol_git_cagirmaz(self):
        with mock.patch.object(cfg.subprocess, "run", side_effect=AssertionError("git çağrıldı")):
            cfg.hizli_surum()
            self.isaretli()
            cfg.doktor_gerekli()

    def test_baslat_aralik_siniri(self):
        with mock.patch.object(cfg.subprocess, "Popen") as po:
            self.assertTrue(cfg.doktor_baslat("proje"))
            self.assertFalse(cfg.doktor_baslat("proje"))  # DOKTOR_ARA içinde ikinci kez başlamaz
            self.assertEqual(po.call_count, 1)
            args = po.call_args[0][0]
            self.assertIn("--duzelt", args)
            self.assertNotIn("--evet", args)  # B sınıfı arka planda asla
            self.assertEqual(args[-2:], ["--proje", "proje"])

    def test_otomatik_anahtari_kapaliysa_baslatmaz(self):
        with mock.patch.dict(os.environ, {"ORKESTRA_DOKTOR_OTOMATIK": "0"}), mock.patch.object(cfg.subprocess, "Popen") as po:
            self.assertFalse(cfg.doktor_baslat("proje"))
            po.assert_not_called()
        self.assertFalse(os.path.exists(self.ev))  # anahtar kapalıyken ev dizinine de dokunulmaz

    def test_baslat_ev_yazilamazsa_baslatmaz(self):
        with mock.patch.object(cfg.subprocess, "Popen") as po, mock.patch.object(cfg.os, "makedirs", side_effect=OSError):
            self.assertFalse(cfg.doktor_baslat())
            po.assert_not_called()

    def test_hook_proje_olmadan_baslatir_ve_hatada_dusmez(self):
        with mock.patch.object(cfg, "doktor_baslat") as b:
            hook._doktor_hizli_yol({"cwd": None})
            b.assert_called_once_with(None)
        with mock.patch.object(cfg, "doktor_gerekli", side_effect=RuntimeError("x")):
            hook._doktor_hizli_yol({})  # çökmez

    def test_hook_gerek_yoksa_baslatmaz(self):
        self.isaretli("1.0")
        with mock.patch.object(cfg, "hizli_surum", return_value="1.0"), mock.patch.object(cfg, "doktor_baslat") as b:
            hook._doktor_hizli_yol({"cwd": self.tmp.name})
            b.assert_not_called()

    def test_hizli_yol_ek_sure_esik_altinda(self):
        self.isaretli("1.0")
        with mock.patch.object(cfg, "hizli_surum", return_value="1.0"):
            n = 200
            t = time.perf_counter()
            for _ in range(n):
                hook._doktor_hizli_yol({"cwd": self.tmp.name})
            ms = (time.perf_counter() - t) / n * 1000
        self.assertLess(ms, 20, f"hızlı yol {ms:.2f} ms")

    def test_arka_plan_doktor_gercekten_config_yazar(self):
        proje = os.path.join(self.tmp.name, "p")
        os.makedirs(proje)
        self.assertTrue(cfg.doktor_baslat(proje))
        bitis = time.time() + 90
        while time.time() < bitis and not cfg.makine_taze_mi():
            time.sleep(0.5)
        self.assertTrue(cfg.makine_taze_mi(), "arka plan doktor makine.json yazmadı")
        bitis = time.time() + 240  # yavaş CI (Windows/py3.9) doktoru 90 sn'yi aşabilir; ikinci bekleme kendi süresini alır
        while time.time() < bitis and not isinstance(cfg.makine_oku().get("son_doktor"), dict):
            time.sleep(0.5)
        self.assertIsInstance(cfg.makine_oku().get("son_doktor"), dict, "doktor çalışma işaretini yazmadı")


if __name__ == "__main__":
    unittest.main()
