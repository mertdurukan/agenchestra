"""`orkestra kart liste --durum`: virgüllü durum süzgeci; süzgeç yoksa açık + beklemede kartlar listelenir."""
import json
import os
import shutil
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(KOK, "scripts", "orkestra.py")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ic_kos  # noqa: E402


class KartListeDurum(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_kld_")
        self.addCleanup(shutil.rmtree, self.proje, ignore_errors=True)
        self.assertEqual(self.cli("baslat").returncode, 0)
        r = self.cli("kart", "yeni", "--soru", "Kısa test sorusu?", "--baslik", "iş", "--basamak", "T2",
                     "--kabul", "yapıldı", "--sinif", "belge", "--yazma", "docs/**")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.gid = r.stdout.strip()

    def cli(self, *args):
        env = dict(os.environ, PYTHONUTF8="1", CLAUDE_PROJECT_DIR=self.proje, CLAUDE_CODE_SESSION_ID="kld-oturum")
        return ic_kos.kos([CLI, *args, "--ajan-id", "ana", "--ajan-tipi", "ana"], cwd=self.proje, env=env) \
            if hasattr(ic_kos, "kos") else None

    def idler(self, *args):
        r = self.cli("kart", "liste", "--json", *args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return [k["id"] for k in json.loads(r.stdout)]

    def test_durum_suzgeci(self):
        self.assertIn(self.gid, self.idler("--durum", "planlandi,beklemede"))
        self.assertEqual(self.idler("--durum", "teslim"), [])

    def test_varsayilan_oturumun_kartini_gosterir(self):
        self.assertIn(self.gid, self.idler())


if __name__ == "__main__":
    unittest.main()
