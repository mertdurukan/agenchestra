"""ADR-0095 (I-285): soğuk önbellek kapısı mesajı engellemez, systemMessage ile bilgi verir (hook düzeyi)."""
import datetime as D
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(KOK, "scripts", "hook.py")


class SogukOnbellekHook(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.proje, ".claude", "orkestra"))
        z = (D.datetime.now(D.timezone.utc) - D.timedelta(minutes=90)).isoformat().replace("+00:00", "Z")
        self.tp = os.path.join(self.proje, "t.jsonl")
        with open(self.tp, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "assistant", "isSidechain": False, "timestamp": z,
                                "message": {"model": "claude-opus-5-5", "usage": {
                                    "input_tokens": 10, "cache_read_input_tokens": 299_990,
                                    "cache_creation_input_tokens": 0}}}) + "\n")

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)

    def calistir(self):
        inp = {"cwd": self.proje, "session_id": "o1", "transcript_path": self.tp, "prompt": "Onayla, uygula"}
        env = {k: v for k, v in os.environ.items() if k != "ORKESTRA_PERSPEKTIF"}
        return subprocess.run([sys.executable, HOOK, "UserPromptSubmit"], input=json.dumps(inp),
                              capture_output=True, text=True, encoding="utf-8", env=env, timeout=60)

    def test_soguk_onbellek_engellemez_system_message_verir(self):
        r = self.calistir()
        self.assertEqual(r.returncode, 0, r.stderr)
        cikti = json.loads(r.stdout)
        self.assertNotEqual(cikti.get("decision"), "block")
        self.assertIn("önbellek bilgisi", cikti.get("systemMessage", ""))
        self.assertIn("300k", cikti["systemMessage"])


if __name__ == "__main__":
    unittest.main()
