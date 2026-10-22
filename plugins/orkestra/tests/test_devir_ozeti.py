"""Otomatik compact devri (ADR-0036): özet üretimi, sır maskeleme, SessionStart yükleme, PreCompact kancası uçtan uca."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(KOK, "scripts", "hook.py")
sys.path.insert(0, os.path.join(KOK, "scripts"))
import devir_ozeti as DO  # noqa: E402

OTURUM = "devir-oturum"


def _transkript(yol, mesajlar):
    with open(yol, "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "attachment"}) + "\n")
        for m in mesajlar:
            f.write(json.dumps({"type": "user", "message": {"role": "user", "content": m}}) + "\n")
        f.write(json.dumps({"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "x"}]}}) + "\n")
        f.write(json.dumps({"type": "user", "isMeta": True, "message": {"content": "meta"}}) + "\n")


class Ozet(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.sd = os.path.join(self.d, ".claude", "orkestra")
        os.makedirs(self.sd)
        self.tr = os.path.join(self.d, "t.jsonl")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_son_mesajlar_gercek_kullanici_mesajlari(self):
        _transkript(self.tr, [f"mesaj {i}" for i in range(10)] + ["<system-reminder>x</system-reminder>"])
        m = DO.son_kullanici_mesajlari(self.tr)
        self.assertEqual(len(m), DO.SON_MESAJ)
        self.assertEqual(m[-1], "mesaj 9")

    def test_sir_maskelenir(self):
        _transkript(self.tr, ["password=GizliDeger123 ile bağlan"])
        metin = DO.uret({"cwd": self.d, "transcript_path": self.tr}, None)
        self.assertNotIn("GizliDeger123", metin)
        self.assertIn("<gizli>", metin)

    def test_todo_ve_is_satiri(self):
        is_klasor = os.path.join(self.d, "is")
        os.makedirs(is_klasor)
        with open(os.path.join(is_klasor, "todo.md"), "w", encoding="utf-8") as f:
            f.write("# Yapılacaklar\n- [x] bitti\n- [ ] P9: açık madde\n")
        metin = DO.uret({"cwd": self.d}, {"id": "I-9", "baslik": "Deneme", "klasor": is_klasor})
        self.assertIn("I-9", metin)
        self.assertIn("P9: açık madde", metin)
        self.assertNotIn("bitti", metin)

    def test_yaz_ve_baglam_dongusu(self):
        _transkript(self.tr, ["merhaba"])
        inp = {"cwd": self.d, "session_id": OTURUM, "transcript_path": self.tr, "trigger": "manual"}
        self.assertTrue(DO.yaz(self.sd, inp, None))
        self.assertIn("merhaba", DO.baglam(self.sd, dict(inp, source="compact")))
        self.assertEqual(DO.baglam(self.sd, dict(inp, source="startup")), "")
        log = open(DO._yol(self.sd, OTURUM, "log"), encoding="utf-8").read()
        self.assertIn("PreCompact", log)
        self.assertIn("SessionStart", log)

    def test_ozet_yoksa_bos_ve_log(self):
        self.assertEqual(DO.baglam(self.sd, {"session_id": "yok", "source": "compact"}), "")
        self.assertIn("SessionStart-ozet-yok", open(DO._yol(self.sd, "yok", "log"), encoding="utf-8").read())


class Kanca(unittest.TestCase):
    def test_precompact_ve_sessionstart_uctan_uca(self):
        d = tempfile.mkdtemp()
        try:
            sd = os.path.join(d, ".claude", "orkestra")
            os.makedirs(sd)
            tr = os.path.join(d, "t.jsonl")
            _transkript(tr, ["kanca deneme mesajı"])
            env = dict(os.environ, CLAUDE_PROJECT_DIR=d, PYTHONUTF8="1")

            def kos(olay, **alan):
                girdi = dict({"cwd": d, "session_id": OTURUM, "transcript_path": tr}, **alan)
                return subprocess.run([sys.executable, HOOK, olay], input=json.dumps(girdi), capture_output=True,
                                      text=True, encoding="utf-8", env=env, timeout=60)

            r = kos("PreCompact", trigger="auto")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(os.path.isfile(DO._yol(sd, OTURUM, "md")))
            r = kos("SessionStart", source="compact")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("kanca deneme mesajı", json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"])
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
