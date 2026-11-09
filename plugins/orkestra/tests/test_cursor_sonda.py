"""ADR-0172: Cursor dinamik sondasının değerlendirmesi. Gerçek Cursor koşusu yapılmaz; kanıt dosyaları sahte verilir."""
import json
import os
import sys
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import cursor_sonda as S  # noqa: E402


def yuk(sid, ad="Shell"):
    return json.dumps({"tool_name": ad, "session_id": sid, "conversation_id": sid})


def ayik(komut):
    return json.dumps({"olay": "preToolUse", "yeni_komut": komut})


IYI_CIKTI = "C:/x/standartlar/kok_neden.md\n"
YAZILMIS = 'python "C:/x/scripts/orkestra.py" standart yol kok_neden'


class Degerlendir(unittest.TestCase):
    def d(self, cikti, yukler, ayiklama, kimlik="abc-123"):
        return {a: d for a, d, _ in S.degerlendir(cikti, yukler, ayiklama, kimlik)}

    def test_hepsi_gecer(self):
        o = self.d(IYI_CIKTI, [yuk("abc-123")], [ayik(YAZILMIS)])
        self.assertEqual(set(o.values()), {"gecti"})

    def test_adaptor_yazmadiysa_basarisiz(self):
        o = self.d(IYI_CIKTI, [yuk("abc-123")], [ayik(None)])
        self.assertEqual(o["komut_yeniden_yazildi"], "basarisiz")

    def test_kimlik_farkliysa_basarisiz(self):
        o = self.d(IYI_CIKTI, [yuk("baska")], [ayik(YAZILMIS)])
        self.assertEqual(o["oturum_kimligi_esit"], "basarisiz")

    def test_komut_cikti_vermediyse(self):
        o = self.d("ORK_KIMLIK=abc-123\n", [yuk("abc-123")], [ayik(YAZILMIS)])
        self.assertEqual(o["komut_calisti"], "basarisiz")

    def test_shell_cagrisi_yoksa_belirsiz(self):
        o = self.d("", [yuk("abc-123", ad="Read")], [])
        self.assertEqual(o["komut_yeniden_yazildi"], "belirsiz")
        self.assertEqual(o["komut_calisti"], "belirsiz")
        self.assertEqual(o["oturum_kimligi_esit"], "belirsiz")

    def test_kimlik_bossa_belirsiz(self):
        o = self.d(IYI_CIKTI, [yuk("abc-123")], [ayik(YAZILMIS)], kimlik="")
        self.assertEqual(o["oturum_kimligi_esit"], "belirsiz")


class Ortam(unittest.TestCase):
    def test_temiz_ortam_claude_degiskenlerini_ve_bin_yolunu_cikarir(self):
        bin_yolu = os.path.join(S.KOK, "bin")
        env = {"CLAUDE_CODE_SESSION_ID": "x", "ORKESTRA_OTURUM": "y", "ANTHROPIC_API_KEY": "z", "KALAN": "1",
               "SHELL": "/usr/bin/bash", "MSYSTEM": "MINGW64", "BASH_ENV": "b", "SHLVL": "1",
               # Surucu harfi yok: POSIX'te os.pathsep ':' olduğundan 'C:/x' ikiye bölünürdü (CI ubuntu/macos).
               "PATH": os.pathsep.join([bin_yolu, "/arac/bin", "/home/u/.claude/plugins/orkestra/bin"])}
        with mock.patch.dict(os.environ, env, clear=True):
            o = S._temiz_ortam({"EK": "2"})
        self.assertNotIn("CLAUDE_CODE_SESSION_ID", o)
        self.assertNotIn("ORKESTRA_OTURUM", o)
        self.assertNotIn("ANTHROPIC_API_KEY", o)
        for bash_izi in ("SHELL", "MSYSTEM", "BASH_ENV", "SHLVL"):
            self.assertNotIn(bash_izi, o)
        self.assertEqual(o["KALAN"], "1")
        self.assertEqual(o["EK"], "2")
        self.assertEqual(o["PATH"], "/arac/bin")

    def test_agent_yoksa_atlanir(self):
        with mock.patch.object(S.shutil, "which", return_value=None):
            self.assertEqual(S.calistir()["durum"], "atlandi")


if __name__ == "__main__":
    unittest.main()
