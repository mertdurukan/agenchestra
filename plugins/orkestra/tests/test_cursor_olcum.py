"""Issue #14 PR-2: araclar/cursor_olcum.py çözümlemesi ve cursor_olcum_gunluk.py. Cursor gerektirmez."""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

KOK = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(KOK / "araclar"))
import cursor_olcum as C  # noqa: E402

GUNLUKCU = str(KOK / "plugins" / "orkestra" / "scripts" / "cursor_olcum_gunluk.py")


def kayit(olay, yuk, t=0.0, sure=1.0):
    return {"t": t, "olay": olay, "yuk": yuk, "sure_ms": sure, "ortam": {"CURSOR_VERSION": "x"}}


class CozumlemeTest(unittest.TestCase):
    def test_olay_sayimi_ve_gorulmeyenler(self):
        ks = [kayit("preToolUse", {"tool_use_id": "a"}), kayit("postToolUse", {"tool_use_id": "a"}, t=1.5)]
        o = C.analiz(ks)
        self.assertEqual(o["olay_sayisi"], {"postToolUse": 1, "preToolUse": 1})
        self.assertIn("subagentStart", o["olaylar_gorulmeyen"])
        self.assertFalse(o["agent_id_goruldu"])
        self.assertEqual(o["pre_post_arac_ms"]["n"], 1)
        self.assertAlmostEqual(o["pre_post_arac_ms"]["p50"], 1500, delta=1)

    def test_agent_id_ve_token_alani(self):
        ks = [kayit("subagentStart", {"subagent_id": "s1", "usage": {"input_tokens": 3}})]
        o = C.analiz(ks)
        self.assertFalse(o["agent_id_goruldu"])
        self.assertIn("usage.input_tokens", o["token_benzeri_alanlar"]["subagentStart"])

    def test_cift_tetik(self):
        ks = [kayit("preToolUse", {"tool_use_id": "a"}), kayit("preToolUse", {"tool_use_id": "a"}, t=1)]
        self.assertEqual(C.analiz(ks)["cift_tetik"], {"preToolUse|a": 2})

    def test_alt_ajan_cakismasi(self):
        ks = [kayit("subagentStart", {"subagent_id": "s1"}, t=1),
              kayit("subagentStart", {"subagent_id": "s2"}, t=2),
              kayit("subagentStop", {"subagent_id": "s1"}, t=5),
              kayit("subagentStop", {"subagent_id": "s2"}, t=6)]
        o = C.analiz(ks)
        self.assertEqual(o["alt_ajan_araliklari"], 2)
        self.assertTrue(o["alt_ajanlar_ust_uste"])

    def test_alt_ajan_siraliysa_cakismaz(self):
        ks = [kayit("subagentStart", {}, t=1), kayit("subagentStop", {}, t=2),
              kayit("subagentStart", {}, t=3), kayit("subagentStop", {}, t=4)]
        self.assertFalse(C.analiz(ks)["alt_ajanlar_ust_uste"])

    def test_yuzdelik(self):
        self.assertEqual(C.yuzdelik([1, 2, 3, 4, 100], 0.5), 3)
        self.assertIsNone(C.yuzdelik([], 0.5))

    def test_bozuk_satir_atlanir(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        p = os.path.join(d, "g.jsonl")
        with open(p, "w", encoding="utf-8") as f:
            f.write('{"t":1,"olay":"stop","yuk":{}}\nbozuk\n\n')
        self.assertEqual(len(C.oku(p)), 1)


class KurulumTest(unittest.TestCase):
    def test_kur_yedekler_ve_kaldir_geri_koyar(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        hedef = os.path.join(d, "hooks.json")
        with open(hedef, "w", encoding="utf-8") as f:
            f.write('{"eski":1}')
        self.assertIn("kuruldu", C.kur(hedef))
        self.assertTrue(os.path.exists(hedef + C.YEDEK_SONEK))
        veri = json.loads(Path(hedef).read_text(encoding="utf-8"))
        self.assertIn("preToolUse", veri["hooks"])
        self.assertTrue(veri["hooks"]["preToolUse"][0]["command"].startswith("python "))
        self.assertIn("geri konuldu", C.kaldir(hedef))
        self.assertEqual(Path(hedef).read_text(encoding="utf-8"), '{"eski":1}')

    def test_kur_yoksa_kaldir_siler(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        hedef = os.path.join(d, "h.json")
        C.kur(hedef)
        self.assertIn("silindi", C.kaldir(hedef))
        self.assertFalse(os.path.exists(hedef))


class GunlukcuTest(unittest.TestCase):
    def calistir(self, olay, yuk, env):
        return subprocess.run([sys.executable, GUNLUKCU, olay], input=json.dumps(yuk).encode(),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, check=False)

    def test_izin_olayi_allow_ve_eposta_yok(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        yol = os.path.join(d, "o.jsonl")
        p = self.calistir("preToolUse", {"user_email": "a@b", "tool_name": "Shell", "x": "y" * 500},
                          dict(os.environ, ORKESTRA_OLCUM_GUNLUK=yol))
        self.assertEqual(p.returncode, 0)
        self.assertEqual(json.loads(p.stdout), {"permission": "allow"})
        kayit = json.loads(Path(yol).read_text(encoding="utf-8"))
        self.assertNotIn("user_email", kayit["yuk"])
        self.assertLess(len(kayit["yuk"]["x"]), 200)
        self.assertIn("sure_ms", kayit)

    def test_izinsiz_olay_bos_cikti_ve_bozuk_girdi(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        yol = os.path.join(d, "o.jsonl")
        env = dict(os.environ, ORKESTRA_OLCUM_GUNLUK=yol, CURSOR_VERSION="3.0")
        p = self.calistir("postToolUse", {"tool_use_id": "t"}, env)
        self.assertEqual(json.loads(p.stdout), {})
        p = subprocess.run([sys.executable, GUNLUKCU, "stop"], input=b"bu json degil",
                           stdout=subprocess.PIPE, env=env, check=False)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(len(C.oku(yol)), 2)


if __name__ == "__main__":
    unittest.main()
