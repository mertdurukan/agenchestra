"""ADR-0011: sohbetteki açık atama kimlik klasörüne yazılır; bağlama ve hata iletisine değer girmez."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import kimlik as K  # noqa: E402
import sir_yakala as S  # noqa: E402

SIR = "d3ger-GIZLI-4242"


class Yakala(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()
        self.eski = {k: os.environ.get(k) for k in ("ORKESTRA_KIMLIK_DIZINI", "ORKESTRA_KIMLIK_PROJE", "ORKESTRA_SIR_YAKALA")}
        os.environ["ORKESTRA_KIMLIK_DIZINI"] = os.path.join(self.t, "cred")
        os.environ["ORKESTRA_KIMLIK_PROJE"] = "Proje"
        os.environ.pop("ORKESTRA_SIR_YAKALA", None)

    def tearDown(self):
        for k, v in self.eski.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)

    def test_atama_servise_yazilir(self):
        s = S.kaydet(f"bak\nLANGFUSE_SECRET_KEY={SIR}\nbitti")
        self.assertEqual(s, ["kimlik kaydedildi: langfuse.LANGFUSE_SECRET_KEY"])
        self.assertEqual(K.al("langfuse", "LANGFUSE_SECRET_KEY"), SIR)
        self.assertNotIn(SIR, "\n".join(s))

    def test_acik_servis_ve_tirnak(self):
        S.kaydet(f"mail: SMTP_PASSWORD=\"{SIR}\"")
        self.assertEqual(K.al("mail", "SMTP_PASSWORD"), SIR)

    def test_guncelleme_bildirilir(self):
        S.kaydet(f"DB_PASSWORD=eski")
        self.assertEqual(S.kaydet(f"DB_PASSWORD={SIR}"), ["kimlik güncellendi: db.DB_PASSWORD"])

    def test_tanimayan_bicim_yazmaz(self):
        for m in (f"şifre {SIR}", f"DB_HOST={SIR}", f"x=y", f"api key: {SIR}"):
            self.assertEqual(S.kaydet(m), [], m)
        self.assertFalse(os.path.exists(K.kok()))

    def test_kapatma(self):
        os.environ["ORKESTRA_SIR_YAKALA"] = "0"
        self.assertEqual(S.kaydet(f"DB_PASSWORD={SIR}"), [])
        self.assertFalse(os.path.exists(K.kok()))

    def test_hook_baglamda_deger_yok(self):
        proje = os.path.join(self.t, "proje")
        os.makedirs(os.path.join(proje, ".claude", "orkestra"))
        girdi = json.dumps({"cwd": proje, "session_id": "s1", "prompt": f"POSTHOG_API_KEY={SIR}"})
        p = subprocess.run([sys.executable, os.path.join(KOK, "scripts", "hook.py"), "UserPromptSubmit"], input=girdi,
                           capture_output=True, text=True, encoding="utf-8", env=dict(os.environ, PYTHONUTF8="1"))
        self.assertNotIn(SIR, p.stdout + p.stderr)
        self.assertIn("kimlik kaydedildi: posthog.POSTHOG_API_KEY", p.stdout)
        self.assertEqual(K.al("posthog", "POSTHOG_API_KEY"), SIR)


if __name__ == "__main__":
    unittest.main()
