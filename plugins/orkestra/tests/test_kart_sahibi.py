"""I-145 P3: kartın güncel sahibi (son_oturum) işleme olayında yazılır; oluşturan oturum değişmez; arşivli sahip ayrışır."""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ic_kos  # noqa: E402

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import ozet  # noqa: E402

CLI = os.path.join(KOK, "scripts", "orkestra.py")
ANA = ["--ajan-id", "ana", "--ajan-tipi", "ana"]


def kos(args, cwd, oturum):
    env = dict(os.environ, CLAUDE_CODE_SESSION_ID=oturum, PYTHONUTF8="1")
    env.pop("CLAUDE_PROJECT_DIR", None)
    return ic_kos.kos(args, cwd=cwd, env=env)


class KartSahibi(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_sahip_")
        self.assertEqual(kos([CLI, "baslat"], self.proje, "oturum-a").returncode, 0)

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)

    def goster(self, g):
        r = kos([CLI, "kart", "goster", g], self.proje, "oturum-a")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def test_son_oturum_islemede_yazilir_olusturan_degismez(self):
        r = kos([CLI, "kart", "yeni", "--soru", "Kısa test sorusu?", "--baslik", "b", "--basamak", "T1", "--sinif", "belge",
                 "--kabul", "yazıldı", "--yazma", "docs/**"], self.proje, "oturum-a")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        g = r.stdout.strip()
        self.assertNotIn("son_oturum", self.goster(g))
        r = kos([CLI, "kart", "durum", g, "isleniyor", *ANA], self.proje, "oturum-b")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        k = self.goster(g)
        self.assertEqual(k["oturum"], "oturum-a")
        self.assertEqual(k["son_oturum"], "oturum-b")

    def test_kart_sahibi_arsivli_ve_bilinmeyen(self):
        masa = {"oturum-a": {"arsiv": True}, "oturum-b": {"arsiv": False}}
        self.assertEqual(ozet.kart_sahibi({"oturum": "oturum-a"}, masa), ("oturum-a", True))
        self.assertEqual(ozet.kart_sahibi({"oturum": "oturum-a", "son_oturum": "oturum-b"}, masa), ("oturum-b", False))
        self.assertEqual(ozet.kart_sahibi({"oturum": "bilinmeyen"}, masa), ("bilinmeyen", False))
        self.assertEqual(ozet.kart_sahibi({"oturum": "-"}, masa), (None, False))
        self.assertEqual(ozet.kart_sahibi({}, {}), (None, False))


if __name__ == "__main__":
    unittest.main()
