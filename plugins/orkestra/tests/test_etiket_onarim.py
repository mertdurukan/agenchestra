"""Etiket onarımı: sarmalayıcılı ilk mesaj + etiketli ikinci mesaj, workflows alt klasörü, '-' önbelleğe yazılmaz, yeniden-etiketle."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
sys.path.insert(0, SCRIPTS)
import hook  # noqa: E402

ORK = os.path.join(SCRIPTS, "orkestra.py")
SARMAL = "[Workflow harness — user request] sarmalayıcı metin"
ETIKETLI = "#GOREV:G-040 #SUREC:is\nGörev: bir şey"


def yaz_transkript(yol, mesajlar):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8") as f:
        for m in mesajlar:
            f.write(json.dumps({"type": "user", "message": {"content": m}}) + "\n")


class Temel(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.proje = os.path.join(self.t.name, "proje")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        self.pdir = os.path.join(self.t.name, "projects")
        self.oid = "oturum-1"
        self.ana = os.path.join(self.pdir, self.oid + ".jsonl")
        os.makedirs(self.pdir)
        open(self.ana, "w").close()

    def tearDown(self):
        self.t.cleanup()


class AjanGorevi(Temel):
    def girdi(self, aid="aaa"):
        return {"agent_id": aid, "transcript_path": self.ana, "session_id": self.oid, "agent_type": "x"}

    def test_ikinci_mesaj_etiketi(self):
        yaz_transkript(os.path.join(self.pdir, self.oid, "subagents", "agent-aaa.jsonl"), [SARMAL, ETIKETLI])
        self.assertEqual(hook.ajan_gorevi(self.sd, self.girdi()), ("G-040", "is"))

    def test_etiket_yoksa_eski_davranis(self):
        yaz_transkript(os.path.join(self.pdir, self.oid, "subagents", "agent-aaa.jsonl"), ["merhaba"])
        self.assertEqual(hook.ajan_gorevi(self.sd, self.girdi())[0], "-")

    def test_workflows_altinda_bulunur(self):
        yaz_transkript(os.path.join(self.pdir, self.oid, "subagents", "workflows", "wf_1", "agent-aaa.jsonl"), [SARMAL, ETIKETLI])
        self.assertEqual(hook.ajan_gorevi(self.sd, self.girdi())[0], "G-040")

    def test_tire_onbellege_yazilmaz(self):
        yol = os.path.join(self.pdir, self.oid, "subagents", "workflows", "wf_1", "agent-aaa.jsonl")
        yaz_transkript(yol, [SARMAL])
        self.assertEqual(hook.ajan_gorevi(self.sd, self.girdi())[0], "-")
        self.assertFalse(os.path.exists(os.path.join(self.sd, "oturumlar", "ajan_aaa.json")))
        yaz_transkript(yol, [SARMAL, ETIKETLI])  # sonraki çağrı yeniden dener
        self.assertEqual(hook.ajan_gorevi(self.sd, self.girdi())[0], "G-040")
        self.assertTrue(os.path.exists(os.path.join(self.sd, "oturumlar", "ajan_aaa.json")))

    def test_eski_tire_onbellegi_yok_sayilir(self):
        with open(os.path.join(self.sd, "oturumlar", "ajan_aaa.json"), "w") as f:
            json.dump({"gorev": "-", "surec": "bilinmiyor"}, f)
        yaz_transkript(os.path.join(self.pdir, self.oid, "subagents", "agent-aaa.jsonl"), [SARMAL, ETIKETLI])
        self.assertEqual(hook.ajan_gorevi(self.sd, self.girdi())[0], "G-040")


class SubagentStop(Temel):
    def girdi(self, aid="bbb"):
        return {"agent_id": aid, "transcript_path": self.ana, "session_id": self.oid, "agent_type": "orkestra:isci",
                "cwd": self.proje, "last_assistant_message": "bitti"}

    def kos(self, girdi):
        eski = os.environ.pop("CLAUDE_PROJECT_DIR", None)
        try:
            with self.assertRaises(SystemExit):
                hook.subagent_stop(girdi)
        finally:
            if eski is not None:
                os.environ["CLAUDE_PROJECT_DIR"] = eski

    def satirlar(self):
        with open(os.path.join(self.sd, "maliyet.jsonl"), encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]

    def asistan(self):
        return {"type": "assistant", "timestamp": "2026-10-13T10:00:00Z", "message": {
            "model": "claude-sonnet-5-5", "content": [{"type": "text", "text": "x"}],
            "usage": {"input_tokens": 10, "output_tokens": 5}}}

    def test_sarmalayici_ve_workflows_gorevi_yazar(self):
        yol = os.path.join(self.pdir, self.oid, "subagents", "workflows", "wf_1", "agent-bbb.jsonl")
        yaz_transkript(yol, [SARMAL, ETIKETLI])
        with open(yol, "a", encoding="utf-8") as f:
            f.write(json.dumps(self.asistan()) + "\n")
        self.kos(self.girdi())
        s = self.satirlar()
        self.assertTrue(s)
        self.assertTrue(all(r["gorev"] == "G-040" and r["surec"] == "is" for r in s))
        with open(os.path.join(self.sd, "oturumlar", "ajan_bbb.json")) as f:
            self.assertEqual(json.load(f)["gorev"], "G-040")

    def test_tire_onbellege_yazilmaz(self):
        yol = os.path.join(self.pdir, self.oid, "subagents", "agent-ccc.jsonl")
        yaz_transkript(yol, [SARMAL, "etiket yok"])
        with open(yol, "a", encoding="utf-8") as f:
            f.write(json.dumps(self.asistan()) + "\n")
        self.kos(self.girdi("ccc"))
        self.assertTrue(all(r["gorev"] == "-" for r in self.satirlar()))
        self.assertFalse(os.path.exists(os.path.join(self.sd, "oturumlar", "ajan_ccc.json")))


class YenidenEtiketle(Temel):
    def setUp(self):
        super().setUp()
        yaz_transkript(os.path.join(self.pdir, self.oid, "subagents", "workflows", "wf_1", "agent-aaa.jsonl"), [SARMAL, ETIKETLI])
        self.mal = os.path.join(self.sd, "maliyet.jsonl")
        self.kayitlar = [
            {"oturum": self.oid, "gorev": "-", "agent_id": "aaa", "model": "m", "maliyet_usd": 1.5, "ozel": "x"},
            {"oturum": self.oid, "gorev": "-", "agent_id": "yok", "model": "m", "maliyet_usd": 2},
            {"oturum": self.oid, "gorev": "-", "agent_id": None, "model": "m"},
            {"oturum": self.oid, "gorev": "G-001", "agent_id": "aaa", "model": "m"},
        ]
        with open(self.mal, "w", encoding="utf-8") as f:
            for r in self.kayitlar:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        with open(os.path.join(self.sd, "oturumlar", "ajan_aaa.json"), "w") as f:
            json.dump({"gorev": "-", "surec": "bilinmiyor", "ajan": "x"}, f)

    def kos(self, *ek):
        env = dict(os.environ, PYTHONUTF8="1")
        env.pop("CLAUDE_PROJECT_DIR", None)
        return subprocess.run([sys.executable, ORK, "maliyet", "yeniden-etiketle", "--transkript-dizini", self.pdir, *ek],
                              capture_output=True, text=True, encoding="utf-8", cwd=self.proje, env=env, timeout=60)

    def oku(self):
        with open(self.mal, encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]

    def test_kuru_degistirmez(self):
        once = open(self.mal, encoding="utf-8").read()
        r = self.kos()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("1 kayıt", r.stdout)
        self.assertIn("G-040: 1", r.stdout)
        self.assertEqual(open(self.mal, encoding="utf-8").read(), once)

    def test_uygula(self):
        r = self.kos("--uygula")
        self.assertEqual(r.returncode, 0, r.stderr)
        s = self.oku()
        self.assertEqual(s[0], dict(self.kayitlar[0], gorev="G-040"))  # başka alana dokunulmaz
        self.assertEqual(s[1:], self.kayitlar[1:])
        with open(os.path.join(self.sd, "oturumlar", "ajan_aaa.json")) as f:
            self.assertEqual(json.load(f)["gorev"], "G-040")


if __name__ == "__main__":
    unittest.main()
