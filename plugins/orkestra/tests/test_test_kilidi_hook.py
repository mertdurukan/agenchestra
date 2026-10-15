"""Test kilidi hook kapısı (G-036): kilitli test dosyaları ve test_alani yazma kuralları.

`python -m unittest discover -s plugins/orkestra/tests -v`
"""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_cekirdek as C  # noqa: E402


class TestKilidiHook(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_tk_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        r = C.kos([C.CLI, "baslat"], self.proje)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.tdir = os.path.join(self.proje, "_transkript")
        os.makedirs(os.path.join(self.tdir, C.OTURUM, "subagents"))
        self.ana_tr = os.path.join(self.tdir, C.OTURUM + ".jsonl")
        open(self.ana_tr, "w").close()
        os.makedirs(os.path.join(self.proje, "tests"))
        os.makedirs(os.path.join(self.proje, "src"))

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)

    # ------------------------------------------------------------ yardımcılar
    def hook(self, girdi):
        g = {"session_id": C.OTURUM, "cwd": self.proje, "transcript_path": self.ana_tr, "hook_event_name": "PreToolUse"}
        g.update(girdi)
        import subprocess
        r = C.kos([C.HOOK, "PreToolUse"], self.proje, stdin=json.dumps(g))
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else {}

    def karar(self, c):
        return (c.get("hookSpecificOutput") or {}).get("permissionDecision")

    def neden(self, c):
        return (c.get("hookSpecificOutput") or {}).get("permissionDecisionReason") or ""

    def kod_karti(self, kilitli=None, durum=None):
        r = C.kos([C.CLI, "kart", "yeni", "--baslik", "kod", "--basamak", "T2", "--kabul", "k", "--sinif", "kod", "--tdd",
                   "--test-komutu", "python -m unittest", "--test-alani", "tests/**", "--yazma", "src/**"], self.proje)
        self.assertEqual(r.returncode, 0, r.stderr)
        gid = r.stdout.strip()
        yol = os.path.join(self.sd, "gorevler", gid + ".json")
        with open(yol, encoding="utf-8") as f:
            k = json.load(f)
        if kilitli is not None:
            k["test_kilidi"] = {"zaman": "2026-10-13T10:00:00+03:00", "dosyalar": {d: "0" * 64 for d in kilitli}}
        if durum:
            k["durum"] = durum
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(k, f)
        return gid

    def ajan(self, aid, gorev, surec):
        os.makedirs(os.path.join(self.sd, "oturumlar"), exist_ok=True)
        with open(os.path.join(self.sd, "oturumlar", f"ajan_{aid}.json"), "w", encoding="utf-8") as f:
            json.dump({"gorev": gorev, "surec": surec, "ajan": "orkestra:isci-t2"}, f)

    def yaz(self, yol, arac="Write", **ek):
        anahtar = "notebook_path" if arac == "NotebookEdit" else "file_path"
        return self.hook(dict({"tool_name": arac, "tool_input": {anahtar: os.path.join(self.proje, yol), "content": "x"}}, **ek))

    # ------------------------------------------------------------ kriter 1
    def test_kilitli_test_herkese_kapali(self):
        self.kod_karti(kilitli=["tests/test_a.py"])
        for arac in ("Write", "Edit", "MultiEdit"):
            c = self.yaz("tests/test_a.py", arac)
            self.assertEqual(self.karar(c), "deny", arac)
            self.assertIn("kilitli test", self.neden(c))
        c = self.yaz("tests/nb.ipynb", "NotebookEdit")
        self.assertNotEqual(self.karar(c), "deny")  # kilitte değil
        # ana ajan dahil: agent_id yok (üstte), alt ajan:
        self.ajan("w1", "G-999", "is")
        c = self.yaz("tests/test_a.py", agent_id="w1", agent_type="orkestra:isci-t2")
        self.assertEqual(self.karar(c), "deny")
        self.assertIn("kilitli test", self.neden(c))

    def test_kilitli_notebook(self):
        self.kod_karti(kilitli=["tests/nb.ipynb"])
        c = self.yaz("tests/nb.ipynb", "NotebookEdit")
        self.assertEqual(self.karar(c), "deny")
        self.assertIn("kilitli test", self.neden(c))

    def test_kilitte_olmayan_dosya_ve_teslim_edilmis_kart_serbest(self):
        self.kod_karti(kilitli=["tests/test_a.py"])
        self.assertNotEqual(self.karar(self.yaz("tests/test_b.py")), "deny")
        self.assertNotEqual(self.karar(self.yaz("src/m.py")), "deny")
        for d in ("teslim", "iptal"):
            gid = self.kod_karti(kilitli=["tests/test_son.py"], durum=d)
            self.assertNotEqual(self.karar(self.yaz("tests/test_son.py")), "deny", d)

    def test_goreli_yol_ve_proje_disi(self):
        self.kod_karti(kilitli=["tests/test_a.py"])
        c = self.hook({"tool_name": "Write", "tool_input": {"file_path": "tests/test_a.py", "content": "x"}})
        self.assertEqual(self.karar(c), "deny")
        dis = os.path.join(tempfile.gettempdir(), "tests", "test_a.py")
        c = self.hook({"tool_name": "Write", "tool_input": {"file_path": dis, "content": "x"}})
        self.assertNotEqual(self.karar(c), "deny")

    # ------------------------------------------------------------ kriter 2
    def test_test_yaz_yalniz_test_alanina_yazar(self):
        gid = self.kod_karti()
        self.ajan("ty", gid, "test-yaz")
        self.assertNotEqual(self.karar(self.yaz("tests/test_yeni.py", agent_id="ty", agent_type="orkestra:isci-t2")), "deny")
        c = self.yaz("src/m.py", agent_id="ty", agent_type="orkestra:isci-t2")
        self.assertEqual(self.karar(c), "deny")
        self.assertIn("test_alani", self.neden(c))

    def test_baska_surec_test_alanina_yazamaz(self):
        gid = self.kod_karti()
        self.ajan("kd", gid, "is")
        c = self.yaz("tests/test_yeni.py", agent_id="kd", agent_type="orkestra:isci-t2")
        self.assertEqual(self.karar(c), "deny")
        self.assertIn("test_alani", self.neden(c))
        self.assertNotEqual(self.karar(self.yaz("src/m.py", agent_id="kd", agent_type="orkestra:isci-t2")), "deny")

    def test_kod_olmayan_kartta_test_yaz_kurali_yok(self):
        r = C.kos([C.CLI, "kart", "yeni", "--baslik", "d", "--basamak", "T1", "--kabul", "k", "--yazma", "docs/**"], self.proje)
        gid = r.stdout.strip()
        self.ajan("dd", gid, "test-yaz")
        self.assertNotEqual(self.karar(self.yaz("docs/a.md", agent_id="dd", agent_type="orkestra:isci-t1")), "deny")

    # ------------------------------------------------------------ kriter 3
    def test_yazan_alt_komut_regex(self):
        sys.path.insert(0, os.path.join(C.KOK, "scripts"))
        import hook
        for alt in ("kart test-kos G-001 kirmizi", "kart test-kilit-ac G-001 --neden x"):
            self.assertTrue(hook.YAZAN_ALT_KOMUT.search(alt), alt)
        self.assertFalse(hook.YAZAN_ALT_KOMUT.search("kart goster G-001"))

    def test_zincirli_test_kos_reddedilir(self):
        for komut in ("orkestra kart test-kos G-001 yesil && echo ok", "orkestra kart test-kilit-ac G-001 --neden x | cat"):
            self.assertEqual(self.karar(self.hook({"tool_name": "Bash", "tool_input": {"command": komut}})), "deny", komut)
        c = self.hook({"tool_name": "Bash", "tool_input": {"command": "orkestra kart test-kos G-001 yesil"}})
        self.assertEqual(self.karar(c), "allow")

    def test_kabukla_kilitli_teste_yazma_reddedilir(self):
        self.kod_karti(kilitli=["tests/test_a.py"])
        yazanlar = ["echo x > tests/test_a.py", "echo x >> tests/test_a.py", "sed -i s/a/b/ tests/test_a.py", "rm tests/test_a.py",
                    "rm -f tests/test_a.py", "tee tests/test_a.py", "mv tests/test_a.py /tmp/x", "cp /tmp/x tests/test_a.py",
                    "Set-Content tests/test_a.py x", "Remove-Item tests/test_a.py",
                    "python -c \"open('tests/test_a.py','w').write('x')\""]
        for k in yazanlar:
            c = self.hook({"tool_name": "Bash", "tool_input": {"command": k}})
            self.assertEqual(self.karar(c), "deny", k)
            self.assertIn("kilitli test", self.neden(c), k)
        c = self.hook({"tool_name": "PowerShell", "tool_input": {"command": "Set-Content tests/test_a.py x"}})
        self.assertEqual(self.karar(c), "deny")

    def test_kabukla_okuma_ve_baska_dosya_serbest(self):
        self.kod_karti(kilitli=["tests/test_a.py"])
        for k in ("cat tests/test_a.py", "grep x tests/test_a.py", "python -m unittest tests/test_a.py",
                  "echo x > tests/test_b.py", "rm tests/test_b.py"):  # not: `cp kilitli hedef` kaynağı okur ama muhafazakâr olarak reddedilir
            self.assertNotEqual(self.karar(self.hook({"tool_name": "Bash", "tool_input": {"command": k}})), "deny", k)

    # ------------------------------------------------------------ kriter 5
    def test_ic_hata_guvenli_taraf(self):
        # bozuk kart dosyası kapıyı çökertmez; korunan dosya reddi sürer, sıradan yazma geçer
        with open(os.path.join(self.sd, "gorevler", "G-500.json"), "w", encoding="utf-8") as f:
            f.write("{bozuk")
        self.assertNotEqual(self.karar(self.yaz("src/m.py")), "deny")
        self.assertEqual(self.karar(self.hook({"tool_name": "Write", "tool_input": {
            "file_path": os.path.join(self.sd, "ortak_defter.md"), "content": "x"}})), "deny")


if __name__ == "__main__":
    unittest.main()
