"""Sohbete git: Claude masaüstü kayıt kökü birden çok adaydan bulunur, bayat önbellek görünür olur (I-320)."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import cfg  # noqa: E402
import niyet  # noqa: E402

CLI = "5752cd3f-a1ff-48bd-b026-5dea5b997f30"


def kayit(kok, ad, oturum_id, cli):
    d = os.path.join(kok, "claude-code-sessions", "u1", "u2")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, ad + ".json"), "w", encoding="utf-8") as f:
        json.dump({"sessionId": oturum_id, "cliSessionId": cli, "title": "t", "isArchived": True}, f)


class MasaustuKokTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = self.tmp.name
        self.roaming = os.path.join(t, "Roaming")
        self.local = os.path.join(t, "Local")
        os.makedirs(os.path.join(self.roaming, "Claude"))  # eski kök: boş (yalnız işaretçi)
        self.yeni = os.path.join(self.local, "Claude-Data", "kurulum1")
        os.makedirs(self.yeni)
        self.onb = os.path.join(t, "genel")
        self.env = mock.patch.dict(os.environ, {"APPDATA": self.roaming, "LOCALAPPDATA": self.local})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.gd = mock.patch.object(niyet, "GENEL_DIZIN", self.onb)
        self.gd.start()
        self.addCleanup(self.gd.stop)
        os.makedirs(self.onb)

    def test_kokler_claude_data_dahil(self):
        kokler = cfg.claude_veri_kokleri()
        self.assertIn(self.yeni, kokler)
        self.assertIn(os.path.join(self.roaming, "Claude"), kokler)

    def test_kayit_yeni_kokte_bulunur(self):
        kayit(self.yeni, "local_ae3f", "local_ae3f", CLI)
        m = niyet.masaustu_oturumlari()
        self.assertEqual(m[CLI]["link"], "claude://claude.ai/epitaxy/local_ae3f")
        self.assertFalse(niyet.MASAUSTU_DURUM["bayat"])

    def test_kok_yoksa_onbellek_bayat_isaretlenir_ve_ac_uyarir(self):
        kayit(self.yeni, "local_ae3f", "local_ae3f", CLI)
        niyet.masaustu_oturumlari()  # önbelleği doldurur
        for kok in cfg.claude_veri_kokleri():
            for kayit_dizini in [os.path.join(kok, "claude-code-sessions")]:
                if os.path.isdir(kayit_dizini):
                    import shutil
                    shutil.rmtree(kayit_dizini)
        m = niyet.masaustu_oturumlari()
        self.assertIn(CLI, m)
        self.assertTrue(niyet.MASAUSTU_DURUM["bayat"])
        with mock.patch("perspektif.claude_exe", return_value=None):
            yanit = niyet.ac("11111111-1111-1111-1111-111111111111")
        self.assertFalse(yanit["tamam"])  # exe yok: hata yolu da sessiz değil
        with mock.patch("perspektif.claude_exe", return_value="x.exe"), mock.patch("subprocess.Popen"):
            yanit = niyet.ac("11111111-1111-1111-1111-111111111111")
        self.assertIn("uyari", yanit)


if __name__ == "__main__":
    unittest.main()
