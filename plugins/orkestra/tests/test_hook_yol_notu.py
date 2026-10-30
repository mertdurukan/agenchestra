"""I-273 / ADR-0103: hook.user_prompt_submit yol notu — kaynak notunun hemen ardında, ORKESTRA_YOL_NOTU=0 ile yok,
gölge modda gunluk.jsonl'a yol_notu yazılır, soru_sinif hatası hook'u düşürmez."""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import hook  # noqa: E402
import niyet  # noqa: E402
import soru_sinif  # noqa: E402

OTURUM = "yol1234567890-oturum"
GERCEK = "bunu kurmak ne kadar önemli ne kazandıırr? ne kaybettirir? best in class yaklşaım ne"


class TestHookYolNotu(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_yolhook_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        self.tr = os.path.join(self.proje, "tr.jsonl")
        open(self.tr, "w").close()
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for k in ("CLAUDE_PROJECT_DIR", "ORKESTRA_RUYA", "ORKESTRA_PERSPEKTIF", "ORKESTRA_YOL_NOTU"):
            os.environ.pop(k, None)
        niyet_yolu = os.path.join(self.proje, "niyet", "niyet.jsonl")
        self._p = [mock.patch.object(niyet, "NIYET_YOLU", niyet_yolu),
                   mock.patch.object(niyet, "GENEL_DIZIN", os.path.dirname(niyet_yolu)),
                   mock.patch.object(niyet, "_gecici", return_value=False)]
        for p in self._p:
            p.start()
        ayar = soru_sinif.ayar_oku(self.sd)
        self.yol, self.kaynak = ayar["yol_sozlesmesi"], ayar["kaynak_sozlesmesi"]

    def tearDown(self):
        for p in self._p:
            p.stop()
        self._env.stop()
        shutil.rmtree(self.proje, ignore_errors=True)

    def istek(self, metin):
        g = {"session_id": OTURUM, "cwd": self.proje, "transcript_path": self.tr, "prompt": metin}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                hook.user_prompt_submit(g)
            except SystemExit as e:
                self.assertIn(e.code, (0, None))
        c = buf.getvalue().strip()
        return json.loads(c)["hookSpecificOutput"]["additionalContext"] if c else ""

    def gunluk(self):
        yol = os.path.join(self.sd, "gunluk.jsonl")
        if not os.path.exists(yol):
            return []
        with open(yol, encoding="utf-8") as f:
            return [json.loads(s) for s in f if s.strip()]

    def test_yol_notu_kaynak_notunun_hemen_ardinda(self):
        satirlar = self.istek(GERCEK).split("\n")
        self.assertIn(self.kaynak, satirlar)
        self.assertEqual(satirlar.index(self.yol), satirlar.index(self.kaynak) + 1)

    def test_yol_notu_bilgi_sorusunda_not_ve_kaynaktan_sonra(self):
        satirlar = self.istek("yol taraması neden gerekir, nedir bu yaklaşım?").split("\n")
        self.assertLess(satirlar.index(self.kaynak), satirlar.index(self.yol))
        self.assertTrue(satirlar[0].startswith("BİLGİ SORUSU"))

    def test_yol_notu_ortam_degiskeniyle_yok(self):
        os.environ["ORKESTRA_YOL_NOTU"] = "0"
        ctx = self.istek(GERCEK)
        self.assertNotIn(self.yol, ctx)
        self.assertIn(self.kaynak, ctx)
        self.assertEqual([k for k in self.gunluk() if k.get("tur") == "yol_notu"], [])

    def test_yol_notu_selamda_yok(self):
        self.assertNotIn(self.yol, self.istek("merhaba"))

    def test_yol_notu_golge_modda_gunluge_yazilir(self):
        self.istek(GERCEK)
        kayit = [k for k in self.gunluk() if k.get("tur") == "yol_notu"]
        self.assertEqual(len(kayit), 1)
        self.assertEqual(kayit[0]["mod"], "golge")
        self.assertEqual(kayit[0]["oturum"], OTURUM)

    def test_yol_notu_sistem_iletisinde_yok(self):
        self.assertNotIn(self.yol, self.istek("<task-notification>" + GERCEK + "</task-notification>"))

    def test_yol_notu_hata_atarsa_hook_cikti_verir(self):
        with mock.patch.object(soru_sinif, "yol_metni", side_effect=RuntimeError("patladi")):
            ctx = self.istek(GERCEK)
        self.assertIn(self.kaynak, ctx)
        self.assertNotIn(self.yol, ctx)


if __name__ == "__main__":
    unittest.main()
