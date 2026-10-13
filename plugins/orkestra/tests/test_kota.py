"""kota.py testleri: resmi durum satırı JSON biçimi (code.claude.com/docs/en/statusline) -> kota.jsonl."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

KOTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "kota.py")

# Resmi belgedeki örnek (rate_limits bölümü): five_hour / seven_day, used_percentage + resets_at (Unix sn)
ORNEK = {"model": {"id": "claude-opus-4-1", "display_name": "Opus"}, "session_id": "abc12345-xyz",
         "rate_limits": {"five_hour": {"used_percentage": 23.5, "resets_at": 4102444800},
                         "seven_day": {"used_percentage": 41.2, "resets_at": 4102444800},
                         "spend_limit": {"used_percentage": 62.8, "resets_at": 1740787200}}}


def calistir(girdi, home):
    env = dict(os.environ, USERPROFILE=home, HOME=home, PYTHONUTF8="1")
    ham = girdi if isinstance(girdi, (bytes, bytearray)) else json.dumps(girdi).encode("utf-8")
    return subprocess.run([sys.executable, KOTA], input=ham, capture_output=True, env=env, timeout=30)


class KotaTest(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.home = self.t.name
        self.jsonl = os.path.join(self.home, ".claude", "orkestra-panel", "kota.jsonl")
        self.cagri = os.path.join(self.home, ".claude", "orkestra-panel", "kota_cagri.json")

    def tearDown(self):
        self.t.cleanup()

    def test_kota_alanli_json_satir_yazar(self):
        r = calistir(ORNEK, self.home)
        self.assertEqual(r.returncode, 0)
        with open(self.jsonl, encoding="utf-8") as f:
            satirlar = [json.loads(s) for s in f.read().splitlines()]
        self.assertEqual(len(satirlar), 1)
        self.assertEqual(satirlar[0]["bes_saat"], {"yuzde": 23.5, "sifirlanma": 4102444800})
        self.assertEqual(satirlar[0]["haftalik"]["yuzde"], 41.2)
        self.assertEqual(satirlar[0]["oturum"], "abc12345")
        out = r.stdout.decode("utf-8")
        self.assertIn("Opus", out)
        self.assertIn("5 sa", out)
        self.assertIn("hafta %41", out)

    def test_kota_alani_yokken_durum_satiri_uretir(self):
        r = calistir({"model": {"display_name": "Sonnet"}}, self.home)
        self.assertEqual(r.returncode, 0)
        self.assertIn("Sonnet", r.stdout.decode("utf-8"))
        self.assertFalse(os.path.exists(self.jsonl))
        with open(self.cagri, encoding="utf-8") as f:
            iz = json.load(f)
        self.assertFalse(iz["rate_limits_var"])

    def test_bozuk_girdi_cokmez(self):
        for ham in (b"{bozuk json", b"", b"[1,2]", b'{"rate_limits": "x", "model": 5}',
                    b'{"rate_limits": {"five_hour": {"used_percentage": "abc"}}}', b"\xff\xfe"):
            r = calistir(ham, self.home)
            self.assertEqual(r.returncode, 0, ham)
            self.assertTrue(r.stdout.decode("utf-8").strip(), ham)
        self.assertFalse(os.path.exists(self.jsonl))

    def test_cagri_izi_yalniz_degisince_yazilir(self):
        girdi = {"model": {"display_name": "Sonnet"}}
        calistir(girdi, self.home)
        with open(self.cagri, encoding="utf-8") as f:
            ilk = f.read()
        calistir(girdi, self.home)  # aynı durum, 5 dk dolmadı: yeniden yazılmaz
        with open(self.cagri, encoding="utf-8") as f:
            self.assertEqual(f.read(), ilk)
        calistir(ORNEK, self.home)  # rate_limits_var değişti: yazılır
        with open(self.cagri, encoding="utf-8") as f:
            self.assertTrue(json.load(f)["rate_limits_var"])


if __name__ == "__main__":
    unittest.main()
