"""hook.py PostToolUse(start_session): K-007 detach hatırlatması; orkestra kapalı projede sessiz."""
import json
import os
import shutil
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(KOK, "scripts", "orkestra.py")
HOOK = os.path.join(KOK, "scripts", "hook.py")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ic_kos  # noqa: E402  (CLI'yi süreç içinde koşar)

OTURUM = "hook-detach-oturum"
YAN = "local_0123abcd-4567-89ab-cdef-0123456789ab"


class HookDetach(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_hookdetach_")
        self.ev = tempfile.mkdtemp(prefix="ork_ev_")
        r = self.kos([CLI, "baslat"])
        self.assertEqual(r.returncode, 0, r.stderr)

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)
        shutil.rmtree(self.ev, ignore_errors=True)

    def kos(self, args, stdin=None, cwd=None):
        env = dict(os.environ, CLAUDE_CODE_SESSION_ID=OTURUM, PYTHONUTF8="1", HOME=self.ev, USERPROFILE=self.ev)
        env.pop("CLAUDE_PROJECT_DIR", None)
        return ic_kos.kos(args, cwd=cwd or self.proje, env=env, input=stdin)

    def baslat(self, sonuc, cwd=None):
        g = {"session_id": OTURUM, "cwd": cwd or self.proje, "hook_event_name": "PostToolUse",
             "tool_name": "mcp__ccd_session__start_session", "tool_input": {"title": "Yan iş"}, "tool_response": sonuc}
        r = self.kos([HOOK, "PostToolUse"], stdin=json.dumps(g), cwd=cwd)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else {}

    def test_id_varsa_hazir_cagri(self):
        ho = self.baslat([{"type": "text", "text": f"Started session {YAN} (name: yan)"}])["hookSpecificOutput"]
        self.assertEqual(ho["hookEventName"], "PostToolUse")
        self.assertIn("K-007", ho["additionalContext"])
        self.assertIn(f'detach_session(session_id="{YAN}")', ho["additionalContext"])

    def test_id_yoksa_genel_uyari(self):
        m = self.baslat({"proposal_id": "p1", "status": "offered"})["hookSpecificOutput"]["additionalContext"]
        self.assertIn("oturum id'si yok", m)
        self.assertIn("<local_… id>", m)

    def test_orkestra_kapali_projede_sessiz(self):
        bos = tempfile.mkdtemp(prefix="ork_kapali_")
        try:
            cikti = self.baslat(f"Started session {YAN}", cwd=bos)
            self.assertNotIn("K-007", json.dumps(cikti, ensure_ascii=False))
        finally:
            shutil.rmtree(bos, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
