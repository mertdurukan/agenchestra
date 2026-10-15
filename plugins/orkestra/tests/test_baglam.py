"""baglam: yoldan/coz kuralları, eşleme yokken '', Stop/SubagentStop kayıtları, oturum bağlamı yapışkanlığı, niyet --baglam yedeği."""
import argparse
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
sys.path.insert(0, SCRIPTS)
import baglam as B  # noqa: E402
import hook  # noqa: E402
import niyet  # noqa: E402
import ork_lib as L  # noqa: E402

DIS = "C:/dis/ornek-depo"
ESLEME = {"surum": 1, "projeler": ["RNV", "Claude_Orkestrasyon"], "surec_deseni": r"^\d{2}_", "gorev_deseni": r"^\d{3}-",
          "haric": ["98_calisma"], "dis_kokler": {DIS: "Claude_Orkestrasyon"}}


class Yoldan(unittest.TestCase):
    def test_ornekler(self):
        for yol, bek in [
            ("RNV/05_sohbet_ajani/002-x/a.md", "RNV/05_sohbet_ajani/002-x"),
            ("RNV/01_agentic_degerlendirme/a.md", "RNV/01_agentic_degerlendirme"),
            ("RNV/Business Core/a.md", "RNV"),
            ("RNV/98_calisma/x/a.py", "RNV"),
            ("Claude_Orkestrasyon/003-y/a.md", "Claude_Orkestrasyon/003-y"),
            ("CLAUDE.md", ""), ("README.md", ""), (".claude/orkestra/x", ""), ("baska/a.md", ""),
            ("RNV\\01_agentic_degerlendirme\\a.md", "RNV/01_agentic_degerlendirme"),
        ]:
            self.assertEqual(B.yoldan(ESLEME, None, yol), bek, yol)

    def test_mutlak_proje_ve_dis_kok(self):
        p = "C:/proje/ornek"
        self.assertEqual(B.yoldan(ESLEME, p, "C:\\proje\\ornek\\RNV\\05_sohbet_ajani\\002-x\\a.md"), "RNV/05_sohbet_ajani/002-x")
        self.assertEqual(B.yoldan(ESLEME, p, "c:/proje/ornek/rnv/01_a/b.md"), "RNV/01_a")
        self.assertEqual(B.yoldan(ESLEME, p, "C:/proje/ornek/CLAUDE.md"), "")
        self.assertEqual(B.yoldan(ESLEME, p, "C:/proje/ornek/.claude/orkestra/x"), "")
        self.assertEqual(B.yoldan(ESLEME, p, DIS + "/plugins/orkestra/scripts/hook.py"), "Claude_Orkestrasyon")
        self.assertEqual(B.yoldan(ESLEME, p, "c:\\dis\\ornek-depo\\x.py"), "Claude_Orkestrasyon")
        self.assertEqual(B.yoldan(ESLEME, p, "D:/baska/a.md"), "")

    def test_esleme_yok(self):
        self.assertEqual(B.yoldan(None, None, "RNV/01_a/b.md"), "")
        self.assertEqual(B.coz(None, None, ["RNV/01_a/b.md"], []), "")

    def test_esleme_oku(self):
        with tempfile.TemporaryDirectory() as sd:
            self.assertIsNone(B.esleme_oku(sd))
            with open(os.path.join(sd, "baglam.json"), "w") as f:
                f.write("{bozuk")
            self.assertIsNone(B.esleme_oku(sd))
            with open(os.path.join(sd, "baglam.json"), "w") as f:
                json.dump(ESLEME, f)
            self.assertEqual(B.esleme_oku(sd)["projeler"], ["RNV", "Claude_Orkestrasyon"])

    def test_modulde_projeye_ozgu_ad_yok(self):
        with open(os.path.join(SCRIPTS, "baglam.py"), encoding="utf-8") as f:
            kaynak = f.read()
        for ad in ("RNV", "McD", "Desktop", "Orkestrasyon"):
            self.assertNotIn(ad, kaynak)


class Coz(unittest.TestCase):
    def test_yazilan_okunandan_agir(self):
        self.assertEqual(B.coz(ESLEME, None, ["RNV/01_a/x.md"], ["RNV/02_b/y.md", "RNV/02_b/z.md"]), "RNV/01_a")

    def test_okunan_cok_ise_kazanir(self):
        okunan = ["RNV/02_b/1.md", "RNV/02_b/2.md", "RNV/02_b/3.md", "RNV/02_b/4.md"]
        self.assertEqual(B.coz(ESLEME, None, ["RNV/01_a/x.md"], okunan), "RNV/02_b")

    def test_esitlikte_derin(self):
        self.assertEqual(B.coz(ESLEME, None, ["RNV/a.md", "RNV/01_a/b.md"], []), "RNV/01_a")

    def test_esitlikte_en_son(self):
        self.assertEqual(B.coz(ESLEME, None, ["RNV/01_a/x.md", "RNV/02_b/y.md"], []), "RNV/02_b")

    def test_bos_oy_almaz(self):
        self.assertEqual(B.coz(ESLEME, None, ["CLAUDE.md"], ["x/y.md"]), "")
        self.assertEqual(B.coz(ESLEME, None, ["CLAUDE.md", "RNV/01_a/b.md"], []), "RNV/01_a")


class Temel(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.proje = os.path.join(self.t.name, "proje")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        self.ana = os.path.join(self.t.name, "ana.jsonl")
        self.oid = "oturum-1"
        self._niyet = niyet.NIYET_YOLU
        self._gecici = niyet._gecici
        niyet._gecici = lambda yol: False  # geçici dizin süzmesini kapat (test kaydı yazılabilsin)
        niyet.NIYET_YOLU = os.path.join(self.t.name, "niyet.jsonl")
        self._eski_env = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = self.proje
        self.sayac = 0

    def tearDown(self):
        niyet.NIYET_YOLU = self._niyet
        niyet._gecici = self._gecici
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        if self._eski_env is not None:
            os.environ["CLAUDE_PROJECT_DIR"] = self._eski_env
        self.t.cleanup()

    def esleme_yaz(self):
        with open(os.path.join(self.sd, "baglam.json"), "w", encoding="utf-8") as f:
            json.dump(ESLEME, f)

    def mesaj(self, arac=None):
        self.sayac += 1
        icerik = [{"type": "text", "text": "x"}]
        if arac:
            icerik = [{"type": "tool_use", "id": f"t{self.sayac}", "name": arac[0], "input": arac[1]}]
        return {"type": "assistant", "timestamp": "2026-10-13T10:00:00Z", "message": {
            "id": f"m{self.sayac}", "model": "claude-sonnet-5-5", "content": icerik,
            "usage": {"input_tokens": 10, "output_tokens": 5}}}

    def transkript(self, yol, araclar, ilk="merhaba"):
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with open(yol, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "user", "message": {"content": ilk}}) + "\n")
            for a in araclar:
                f.write(json.dumps(self.mesaj(a)) + "\n")

    def ekle(self, arac):
        with open(self.ana, "a", encoding="utf-8") as f:
            f.write(json.dumps(self.mesaj(arac)) + "\n")

    def hook_kos(self, fn, girdi):
        g = {"session_id": self.oid, "cwd": self.proje, "transcript_path": self.ana, "last_assistant_message": "bitti"}
        g.update(girdi)
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            fn(g)

    def stop(self):
        self.hook_kos(hook.stop, {})

    def maliyet(self):
        with open(os.path.join(self.sd, "maliyet.jsonl"), encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]

    def defter(self):
        return L.defter_kayitlari(self.sd)

    def oturum(self):
        with open(os.path.join(self.sd, "oturumlar", f"{self.oid}.json"), encoding="utf-8") as f:
            return json.load(f)

    def yaz(self, *parca):
        return ("Write", {"file_path": os.path.join(self.proje, *parca)})


class TranskriptOku(Temel):
    def test_okunan_ve_dokunulan(self):
        self.transkript(self.ana, [("Read", {"file_path": "a.md"}), ("Read", {"file_path": "a.md"}),
                                   ("Write", {"file_path": "b.md"}), ("Edit", {"file_path": "c.md"}), ("Bash", {"command": "ls"})])
        o = L.transkript_oku(self.ana)
        self.assertEqual(o["okunan"], ["a.md"])
        self.assertEqual(o["dokunulan"], ["b.md", "c.md"])

    def test_anahtar_her_zaman_var(self):
        self.assertEqual(L.transkript_oku(os.path.join(self.t.name, "yok.jsonl"))["okunan"], [])


class StopHook(Temel):
    def test_esleme_yokken_bos_ama_anahtar_var(self):
        self.transkript(self.ana, [self.yaz("RNV", "01_a", "x.md")])
        self.stop()
        satirlar = self.maliyet()
        self.assertTrue(satirlar)
        for s in satirlar:
            self.assertEqual(s["baglam"], "")
            self.assertEqual(s["surec"], "orkestrasyon")
        d = self.defter()
        self.assertEqual([x["baglam"] for x in d], [""])
        self.assertEqual(d[-1]["surec"], "orkestrasyon")

    def test_maliyet_ve_defter_baglam(self):
        self.esleme_yaz()
        self.transkript(self.ana, [self.yaz("RNV", "05_sohbet_ajani", "002-x", "a.md")])
        self.stop()
        for s in self.maliyet():
            self.assertEqual(s["baglam"], "RNV/05_sohbet_ajani/002-x")
            self.assertEqual(s["surec"], "orkestrasyon")
        d = self.defter()
        self.assertEqual(d[-1]["baglam"], "RNV/05_sohbet_ajani/002-x")
        self.assertEqual(d[-1]["surec"], "orkestrasyon")
        o = self.oturum()
        self.assertEqual(o["baglam"], "RNV/05_sohbet_ajani/002-x")
        self.assertGreater(o["ofset"], 0)

    def test_dosyasiz_turda_korunur_ve_ofset_ilerler(self):
        self.esleme_yaz()
        self.transkript(self.ana, [self.yaz("RNV", "01_a", "x.md")])
        self.stop()
        ofset1 = self.oturum()["ofset"]
        self.ekle(("Bash", {"command": "ls"}))
        self.stop()
        self.assertEqual(self.oturum()["baglam"], "RNV/01_a")
        self.assertGreater(self.oturum()["ofset"], ofset1)
        self.assertEqual(self.maliyet()[-1]["baglam"], "RNV/01_a")

    def test_yeni_tur_baglami_gunceller(self):
        self.esleme_yaz()
        self.transkript(self.ana, [self.yaz("RNV", "01_a", "x.md")])
        self.stop()
        self.ekle(self.yaz("RNV", "02_b", "y.md"))
        self.stop()
        self.assertEqual(self.oturum()["baglam"], "RNV/02_b")

    def test_niyet_yedegi(self):
        self.esleme_yaz()
        niyet.olay(self.oid, os.path.join(self.t.name, "baska"), "niyet", ne="a", neden="b", baglam="RNV/03_z")
        self.assertEqual(niyet.son_baglam(self.oid), "RNV/03_z")
        self.transkript(self.ana, [("Bash", {"command": "ls"})])
        self.stop()
        self.assertEqual(self.maliyet()[-1]["baglam"], "RNV/03_z")
        self.assertEqual(self.oturum()["baglam"], "RNV/03_z")

    def test_niyet_yedegi_dosya_varsa_kullanilmaz(self):
        self.esleme_yaz()
        niyet.olay(self.oid, os.path.join(self.t.name, "baska"), "niyet", ne="a", neden="b", baglam="RNV/03_z")
        self.transkript(self.ana, [self.yaz("RNV", "01_a", "x.md")])
        self.stop()
        self.assertEqual(self.maliyet()[-1]["baglam"], "RNV/01_a")

    def test_niyet_baglam_metni(self):
        self.assertIn("--baglam", niyet.baglam_metni(self.oid))


class AltAjan(Temel):
    def alt(self, araclar, aid="bbb", ilk="merhaba"):
        yol = os.path.join(self.t.name, self.oid, "subagents", f"agent-{aid}.jsonl")
        self.transkript(yol, araclar, ilk)
        self.hook_kos(hook.subagent_stop, {"agent_id": aid, "agent_type": "orkestra:isci-t2", "agent_transcript_path": yol})

    def test_kendi_transkriptinden(self):
        self.esleme_yaz()
        self.alt([self.yaz("Claude_Orkestrasyon", "003-y", "a.md")])
        s = self.maliyet()[-1]
        self.assertEqual(s["baglam"], "Claude_Orkestrasyon/003-y")
        self.assertEqual(s["surec"], "is")
        self.assertEqual(self.defter()[-1]["baglam"], "Claude_Orkestrasyon/003-y")

    def test_bos_ise_ana_oturum(self):
        self.esleme_yaz()
        with open(os.path.join(self.sd, "oturumlar", f"{self.oid}.json"), "w") as f:
            json.dump({"ofset": 0, "baglam": "RNV/01_a"}, f)
        self.alt([("Bash", {"command": "ls"})])
        self.assertEqual(self.maliyet()[-1]["baglam"], "RNV/01_a")
        self.assertEqual(self.defter()[-1]["baglam"], "RNV/01_a")

    def test_esleme_yokken_bos(self):
        self.alt([self.yaz("RNV", "01_a", "a.md")])
        self.assertEqual(self.maliyet()[-1]["baglam"], "")
        self.assertEqual(self.defter()[-1]["baglam"], "")

    def test_ajan_onbellegine_yazilir(self):
        self.esleme_yaz()
        self.alt([self.yaz("RNV", "01_a", "a.md")], aid="ccc", ilk="#GOREV:G-9 #SUREC:is\nx")
        with open(os.path.join(self.sd, "oturumlar", "ajan_ccc.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["baglam"], "RNV/01_a")


class NiyetCli(Temel):
    def test_baglam_kaydedilir(self):
        ap = argparse.ArgumentParser()
        niyet.ekle_ayristirici(ap.add_subparsers())
        a = ap.parse_args(["niyet", "--ne", "x", "--neden", "y", "--baglam", "RNV/01_a", "--oturum", "o-cli"])
        with contextlib.redirect_stdout(io.StringIO()):
            niyet.cmd(a)
        self.assertEqual(niyet.son_baglam("o-cli"), "RNV/01_a")


if __name__ == "__main__":
    unittest.main()
