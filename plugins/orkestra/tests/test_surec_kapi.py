"""SURECLER 'on-kontrol' ve 'test-kapisi' içerir; kapı etiketleri kendi adıyla çözülür ve işçi ajan tipinde 'is'e düşmez."""
import json
import os
import sys
import tempfile
import unittest

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
sys.path.insert(0, SCRIPTS)
import ork_lib as L  # noqa: E402
import hook  # noqa: E402

KAPILAR = ("on-kontrol", "test-kapisi")
ONCEKI = ("is", "denetim", "arsiv", "perspektif", "skill-avi", "arastirma", "orkestrasyon", "test-yaz", "bilinmiyor")


def yaz_transkript(yol, mesajlar):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8") as f:
        for m in mesajlar:
            f.write(json.dumps({"type": "user", "message": {"content": m}}) + "\n")


class Surecler(unittest.TestCase):
    def test_kapilar_surecler_icinde(self):
        for s in KAPILAR:
            self.assertIn(s, L.SURECLER)

    def test_mevcut_degerler_ve_sirasi_korunur(self):
        mevcut = [s for s in L.SURECLER if s in ONCEKI]
        self.assertEqual(mevcut, list(ONCEKI))
        self.assertEqual(len(set(L.SURECLER)), len(L.SURECLER))

    def test_etiket_metinden_cozer(self):
        for s in KAPILAR:
            self.assertEqual(L.etiketler(f"#GOREV:G-030 #SUREC:{s}\nGörev: x"), ("G-030", s))

    def test_transkriptten_cozer(self):
        for s in KAPILAR:
            with tempfile.TemporaryDirectory() as d:
                yol = os.path.join(d, "t.jsonl")
                yaz_transkript(yol, [f"#GOREV:G-030 #SUREC:{s}\nGörev"])
                o = L.transkript_oku(yol)
            self.assertEqual(L.etiketler(o["ilk_kullanici"]), ("G-030", s))

    def test_benzer_adlar_hala_bilinmiyor(self):
        for s in ("on-kontrolx", "test-kapisix", "on", "kapi", "test-kapi"):
            self.assertEqual(L.etiketler(f"#GOREV:G-1 #SUREC:{s}")[1], "bilinmiyor", s)


class HookSureci(unittest.TestCase):
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

    def kos(self, aid, atip, etiket):
        yol = os.path.join(self.pdir, self.oid, "subagents", f"agent-{aid}.jsonl")
        yaz_transkript(yol, [etiket])
        with open(yol, "a", encoding="utf-8") as f:
            f.write(json.dumps({"type": "assistant", "timestamp": "2026-10-14T10:00:00Z", "message": {
                "model": "claude-sonnet-5-5", "content": [{"type": "text", "text": "x"}],
                "usage": {"input_tokens": 10, "output_tokens": 5}}}) + "\n")
        girdi = {"agent_id": aid, "transcript_path": self.ana, "session_id": self.oid, "agent_type": atip,
                 "cwd": self.proje, "last_assistant_message": "bitti"}
        eski = os.environ.pop("CLAUDE_PROJECT_DIR", None)
        try:
            with self.assertRaises(SystemExit):
                hook.subagent_stop(girdi)
        finally:
            if eski is not None:
                os.environ["CLAUDE_PROJECT_DIR"] = eski
        with open(os.path.join(self.sd, "maliyet.jsonl"), encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]

    def test_isci_tipinde_kapi_etiketi_is_olmaz(self):
        for i, s in enumerate(KAPILAR):
            satirlar = self.kos(f"k{i}", "orkestra:isci", f"#GOREV:G-030 #SUREC:{s}\nGörev")
            satirlar = [r for r in satirlar if r["agent_id"] == f"k{i}"] if satirlar and "agent_id" in satirlar[0] else satirlar
            self.assertTrue(satirlar)
            self.assertTrue(all(r["surec"] == s for r in satirlar), (s, [r["surec"] for r in satirlar]))
            with open(os.path.join(self.sd, "oturumlar", f"ajan_k{i}.json"), encoding="utf-8") as f:
                self.assertEqual(json.load(f)["surec"], s)

    def test_etiketsiz_isci_hala_is(self):
        satirlar = self.kos("e1", "orkestra:isci", "#GOREV:G-030\nGörev")
        self.assertTrue(satirlar)
        self.assertTrue(all(r["surec"] == "is" for r in satirlar))


if __name__ == "__main__":
    unittest.main()
