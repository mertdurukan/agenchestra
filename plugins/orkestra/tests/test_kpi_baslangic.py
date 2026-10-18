"""`orkestra kpi --baslangic YYYY-AA-GG`: yalnız o tarihten sonra oluşan kartlar sayılır; hatalı tarih 2 ile çıkar."""
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


class KpiBaslangic(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_kpib_")
        self.addCleanup(shutil.rmtree, self.proje, ignore_errors=True)
        self.assertEqual(self.cli("baslat").returncode, 0)
        r = self.cli("kart", "yeni", "--soru", "Kısa test sorusu?", "--baslik", "iş", "--basamak", "T2",
                     "--kabul", "yapıldı", "--sinif", "belge", "--yazma", "docs/**")
        self.assertEqual(r.returncode, 0, r.stderr)

    def cli(self, *args):
        env = dict(os.environ, PYTHONUTF8="1", CLAUDE_CODE_SESSION_ID="kpib-oturum", CLAUDE_PROJECT_DIR=self.proje)
        return ic_kos.kos([CLI, *args, "--ajan-id", "ana", "--ajan-tipi", "ana"], cwd=self.proje, env=env)

    def test_gelecek_baslangic_kart_saymaz_gecmis_sayar(self):
        gelecek = json.loads(self.cli("kpi", "--json", "--baslangic", "2999-01-01").stdout)
        gecmis = json.loads(self.cli("kpi", "--json", "--baslangic", "2000-01-01").stdout)
        self.assertEqual(max(gelecek["ornek"].values() or [0]), 0)
        self.assertGreaterEqual(max(gecmis["ornek"].values() or [0]), 1)

    def test_hatali_tarih(self):
        r = self.cli("kpi", "--baslangic", "dun")
        self.assertEqual(r.returncode, 2)
        self.assertIn("YYYY-AA-GG", r.stderr)


if __name__ == "__main__":
    unittest.main()
