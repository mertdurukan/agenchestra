"""Orkestra çekirdek testleri: `python -m unittest discover -s plugins/orkestra/tests -v`

Gerçek hook girdilerini (stdin JSON) geçici bir projede sınar: kapılar, defter, token defteri, bitiş kapısı.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(KOK, "scripts", "orkestra.py")
HOOK = os.path.join(KOK, "scripts", "hook.py")
OTURUM = "test-oturum-1"


def kos(args, cwd, ortam=None, stdin=None):
    env = dict(os.environ, CLAUDE_CODE_SESSION_ID=OTURUM, PYTHONUTF8="1")
    env.pop("CLAUDE_PROJECT_DIR", None)
    env.update(ortam or {})
    return subprocess.run([sys.executable] + args, cwd=cwd, env=env, input=stdin, capture_output=True, text=True, encoding="utf-8")


class Cekirdek(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_test_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        r = kos([CLI, "baslat"], self.proje)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.tdir = os.path.join(self.proje, "_transkript")
        os.makedirs(os.path.join(self.tdir, OTURUM, "subagents"))
        self.ana_tr = os.path.join(self.tdir, OTURUM + ".jsonl")
        open(self.ana_tr, "w").close()

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)

    # ---------------------------------------------------------- yardımcılar
    def cli(self, *args, ajan_id=None, ajan_tipi=None):
        a = [CLI] + list(args)
        if ajan_id:
            a += ["--ajan-id", ajan_id, "--ajan-tipi", ajan_tipi]
        return kos(a, self.proje)

    def hook(self, olay, girdi):
        g = {"session_id": OTURUM, "cwd": self.proje, "transcript_path": self.ana_tr, "hook_event_name": olay}
        g.update(girdi)
        r = kos([HOOK, olay], self.proje, stdin=json.dumps(g))
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else {}

    def karar(self, cikti):
        return (cikti.get("hookSpecificOutput") or {}).get("permissionDecision")

    def kart(self, *ek):
        r = self.cli("kart", "yeni", "--baslik", "README satırı", "--basamak", "T1", "--kabul", "satır eklendi",
                     "--yazma", "docs/**", *ek)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def alt_ajan_transkripti(self, aid, gorev, surec, model="claude-haiku-5-5", dosya=None):
        yol = os.path.join(self.tdir, OTURUM, "subagents", f"agent-{aid}.jsonl")
        satirlar = [
            {"type": "user", "timestamp": "2026-10-13T10:00:00Z", "message": {"role": "user", "content": f"#GOREV:{gorev} #SUREC:{surec}\nİşi yap."}},
            {"type": "assistant", "timestamp": "2026-10-13T10:00:05Z", "message": {"id": "m1", "model": model, "content": [{"type": "text", "text": "a"}],
             "usage": {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 100, "cache_creation_input_tokens": 0}}},
            {"type": "assistant", "timestamp": "2026-10-13T10:00:06Z", "message": {"id": "m1", "model": model,
             "content": [{"type": "tool_use", "id": "t1", "name": "Write", "input": {"file_path": dosya or "docs/a.md"}}],
             "usage": {"input_tokens": 10, "output_tokens": 50, "cache_read_input_tokens": 100, "cache_creation_input_tokens": 0}}},
            {"type": "assistant", "timestamp": "2026-10-13T10:00:30Z", "message": {"id": "m2", "model": model, "content": [{"type": "text", "text": "bitti"}],
             "usage": {"input_tokens": 3, "output_tokens": 20, "cache_read_input_tokens": 200,
                       "cache_creation": {"ephemeral_5m_input_tokens": 40, "ephemeral_1h_input_tokens": 0}, "cache_creation_input_tokens": 40}}},
        ]
        with open(yol, "w", encoding="utf-8") as f:
            for s in satirlar:
                f.write(json.dumps(s) + "\n")
        with open(yol[:-6] + ".meta.json", "w", encoding="utf-8") as f:
            json.dump({"agentType": "orkestra:isci-t1", "description": "README satırı ekle"}, f)
        return yol

    # ---------------------------------------------------------- testler
    def test_defter_ve_kartlar_elle_duzenlenemez(self):
        for ad in ("ortak_defter.md", "maliyet.jsonl", "gorevler/G-001.json", "gorevler/G-001.denetim.json"):
            c = self.hook("PreToolUse", {"tool_name": "Write", "tool_input": {"file_path": os.path.join(self.sd, ad), "content": "x"}})
            self.assertEqual(self.karar(c), "deny", ad)
        c = self.hook("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": f"echo x >> {self.sd}/ortak_defter.md"}})
        self.assertEqual(self.karar(c), "deny")

    def test_orkestra_dis_projede_sessiz(self):
        bos = tempfile.mkdtemp()
        try:
            r = kos([HOOK, "PreToolUse"], bos, stdin=json.dumps({"cwd": bos, "tool_name": "Write", "tool_input": {"file_path": "a.txt"}}))
            self.assertEqual(r.stdout.strip(), "")
        finally:
            shutil.rmtree(bos)

    def test_kimlik_enjeksiyonu_ve_sahte_kimlik_silinir(self):
        c = self.hook("PreToolUse", {"tool_name": "Bash", "agent_id": "ag1", "agent_type": "orkestra:isci-t1",
                                     "tool_input": {"command": "orkestra kart denetim G-001 --karar onay --gerekce ok --ajan-tipi orkestra:denetci"}})
        self.assertEqual(self.karar(c), "allow")
        komut = c["hookSpecificOutput"]["updatedInput"]["command"]
        self.assertIn("--ajan-id ag1 --ajan-tipi orkestra:isci-t1", komut)
        self.assertNotIn("--ajan-tipi orkestra:denetci", komut)

    def test_zincirli_yazan_komut_reddedilir_tirnak_ici_serbest(self):
        c = self.hook("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": "orkestra kart teslim G-001 && echo ok"}})
        self.assertEqual(self.karar(c), "deny")
        c = self.hook("PreToolUse", {"tool_name": "Bash", "agent_id": "d1", "agent_type": "orkestra:denetci",
                                     "tool_input": {"command": 'orkestra kart denetim G-001 --karar ret --gerekce "k1 tamam; k2 | eksik"'}})
        self.assertEqual(self.karar(c), "allow")

    def test_denetim_dongusu_ve_oz_denetim_yasagi(self):
        g = self.kart()
        # denetlenecek çıktı yokken denetim reddedilir
        self.assertNotEqual(self.cli("kart", "denetim", g, "--karar", "onay", "--gerekce", "x", ajan_id="d1", ajan_tipi="orkestra:denetci").returncode, 0)
        self.assertEqual(self.cli("kart", "durum", g, "is-bitti", "--ozet", "eklendi", "--cikti", "docs/a.md", ajan_id="w1", ajan_tipi="orkestra:isci-t1").returncode, 0)
        # işçi kendi işini denetleyemez (tipi denetçi olsa bile aynı agent_id)
        r = self.cli("kart", "denetim", g, "--karar", "onay", "--gerekce", "x", ajan_id="w1", ajan_tipi="orkestra:denetci")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("kendi işini", r.stderr)
        # işçi tipi denetim yazamaz
        self.assertNotEqual(self.cli("kart", "denetim", g, "--karar", "onay", "--gerekce", "x", ajan_id="w2", ajan_tipi="orkestra:isci-t2").returncode, 0)
        # ana ajan denetim yazamaz
        self.assertNotEqual(self.cli("kart", "denetim", g, "--karar", "onay", "--gerekce", "x", ajan_id="ana", ajan_tipi="ana").returncode, 0)
        # teslim onaysız olmaz
        self.assertNotEqual(self.cli("kart", "teslim", g, ajan_id="ana", ajan_tipi="ana").returncode, 0)
        # ret → düzeltme → onay → teslim
        self.assertEqual(self.cli("kart", "denetim", g, "--karar", "ret", "--gerekce", "k1 kanıtsız", "--talimat", "kanıt ekle", ajan_id="d1", ajan_tipi="orkestra:denetci").returncode, 0)
        self.assertIn("reddedildi", self.cli("kart", "goster", g).stdout)
        self.assertIn("kanıt ekle", self.cli("defter", "baglam", g).stdout)
        self.assertEqual(self.cli("kart", "durum", g, "is-bitti", "--ozet", "kanıt eklendi", ajan_id="w1", ajan_tipi="orkestra:isci-t1").returncode, 0)
        self.assertEqual(self.cli("kart", "denetim", g, "--karar", "onay", "--gerekce", "k1 kanıtlı", ajan_id="d2", ajan_tipi="orkestra:denetci").returncode, 0)
        r = self.cli("kart", "teslim", g, "--ozet", "tamam", ajan_id="ana", ajan_tipi="ana")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.sd, "gorevler", f"{g}.denetim.json")))

    def test_yazma_alani_kapisi(self):
        g = self.kart()
        self.alt_ajan_transkripti("w9", g, "is")
        disari = self.hook("PreToolUse", {"tool_name": "Write", "agent_id": "w9", "agent_type": "orkestra:isci-t1",
                                          "tool_input": {"file_path": os.path.join(self.proje, "src", "x.py")}})
        self.assertEqual(self.karar(disari), "deny")
        iceri = self.hook("PreToolUse", {"tool_name": "Write", "agent_id": "w9", "agent_type": "orkestra:isci-t1",
                                         "tool_input": {"file_path": os.path.join(self.proje, "docs", "x.md")}})
        self.assertIsNone(self.karar(iceri))
        proje_disi = self.hook("PreToolUse", {"tool_name": "Write", "agent_id": "w9", "agent_type": "orkestra:isci-t1",
                                              "tool_input": {"file_path": os.path.join(tempfile.gettempdir(), "scratch.txt")}})
        self.assertIsNone(self.karar(proje_disi))

    def test_ana_ajan_isleniyor_kartin_alanina_yazmaz(self):
        g = self.kart()
        self.cli("kart", "durum", g, "isleniyor", ajan_id="ana", ajan_tipi="ana")
        c = self.hook("PreToolUse", {"tool_name": "Edit", "tool_input": {"file_path": os.path.join(self.proje, "docs", "a.md")}})
        self.assertEqual(self.karar(c), "deny")

    def test_subagent_stop_token_ve_defter(self):
        g = self.kart()
        tr = self.alt_ajan_transkripti("w5", g, "is")
        self.hook("SubagentStop", {"agent_id": "w5", "agent_type": "orkestra:isci-t1", "agent_transcript_path": tr,
                                   "last_assistant_message": "README'ye satır ekledim."})
        satirlar = [json.loads(s) for s in open(os.path.join(self.sd, "maliyet.jsonl"), encoding="utf-8")]
        self.assertEqual(len(satirlar), 1)
        r = satirlar[0]
        # m1 iki satırda: SON kullanım sayılır (çıkış 50), m2 eklenir → çıkış 70, giriş 13
        self.assertEqual((r["gorev"], r["surec"], r["model"], r["giris"], r["cikis"], r["onbellek_okuma"]), (g, "is", "claude-haiku-5-5", 13, 70, 300))
        beklenen = (13 * 0.10 + 70 * 0.50 + 300 * 0.01 + 40 * 0.125) / 1e6
        self.assertAlmostEqual(r["maliyet_usd"], round(beklenen, 6), places=6)
        self.assertEqual(r["sure_ms"], 30000)
        defter = open(os.path.join(self.sd, "ortak_defter.md"), encoding="utf-8").read()
        self.assertIn(f"{g} · is · orkestra:isci-t1", defter)
        self.assertIn("docs/a.md", defter)
        k = json.loads(self.cli("kart", "goster", g).stdout)
        self.assertIn("w5", k["isciler"])

    def test_bitis_kapisi(self):
        g = self.kart()
        self.cli("kart", "durum", g, "isleniyor", ajan_id="ana", ajan_tipi="ana")
        c = self.hook("Stop", {"stop_hook_active": False, "last_assistant_message": "bitti"})
        self.assertEqual(c.get("decision"), "block")
        c = self.hook("Stop", {"stop_hook_active": True})
        self.assertNotEqual(c.get("decision"), "block")
        c = self.hook("Stop", {"stop_hook_active": False, "background_tasks": [{"id": "x"}]})
        self.assertNotEqual(c.get("decision"), "block")
        self.cli("kart", "durum", g, "beklemede", "--not", "kullanıcıyı bekliyor", ajan_id="ana", ajan_tipi="ana")
        c = self.hook("Stop", {"stop_hook_active": False})
        self.assertNotEqual(c.get("decision"), "block")

    def test_paralel_defter_yazimi_kayipsiz(self):
        def ekle(i):
            return self.cli("defter", "ekle", f"G-{i:03d}", "--surec", "is", "--yaptim", f"iş {i}", ajan_id=f"a{i}", ajan_tipi="orkestra:isci-t1").returncode
        with ThreadPoolExecutor(8) as ex:
            kodlar = list(ex.map(ekle, range(12)))
        self.assertEqual(kodlar, [0] * 12)
        jl = [json.loads(s) for s in open(os.path.join(self.sd, "ortak_defter.jsonl"), encoding="utf-8")]
        self.assertEqual(len(jl), 12)
        self.assertEqual(open(os.path.join(self.sd, "ortak_defter.md"), encoding="utf-8").read().count("## ["), 12)

    def test_maskeleme(self):
        self.hook("UserPromptSubmit", {"prompt": "host x password: Gizli123! ve postgres://u:Pw9x@h/db mail a.b@c.com"})
        satir = open(os.path.join(self.sd, "gunluk.jsonl"), encoding="utf-8").read()
        for sir in ("Gizli123!", "Pw9x", "a.b@c.com"):
            self.assertNotIn(sir, satir)

    def test_maliyet_raporu(self):
        g = self.kart()
        tr = self.alt_ajan_transkripti("w6", g, "is")
        self.hook("SubagentStop", {"agent_id": "w6", "agent_type": "orkestra:isci-t1", "agent_transcript_path": tr})
        r = self.cli("maliyet", "rapor")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Görev × süreç", r.stdout)
        self.assertIn(g, r.stdout)
        self.assertIn("claude-haiku-5-5", r.stdout)

    def test_sayac_tur_kaydi_transkript_tahminini_ezer(self):
        g = self.kart()
        tr = self.alt_ajan_transkripti("w7", g, "is")
        self.hook("SubagentStop", {"agent_id": "w7", "agent_type": "orkestra:isci-t1", "agent_transcript_path": tr})
        # sayaç modülü: aynı ajan için kesin tur kullanımı (çıkış transkripttekinden çok daha büyük)
        r = kos([CLI, "maliyet", "tur", "--oturum", OTURUM, "--agent-id", "w7", "--model", "claude-haiku-5-5",
                 "--giris", "13", "--cikis", "5000", "--onb-okuma", "300", "--onb-yazma", "40"], self.proje)
        self.assertEqual(r.returncode, 0, r.stderr)
        sys.path.insert(0, os.path.join(KOK, "scripts"))
        import ork_lib as L
        satirlar = [x for x in L.maliyet_kayitlari(self.sd) if x.get("agent_id") == "w7"]
        self.assertEqual(len(satirlar), 1)
        self.assertEqual((satirlar[0]["kaynak"], satirlar[0]["cikis"], satirlar[0]["gorev"], satirlar[0]["surec"]), ("tur", 5000, g, "is"))
        # ana döngü turu: agent id yok → ana-ajan / orkestrasyon
        kos([CLI, "maliyet", "tur", "--oturum", OTURUM, "--model", "claude-opus-5-5", "--giris", "5", "--cikis", "100"], self.proje)
        ana = [x for x in L.maliyet_kayitlari(self.sd) if x.get("agent_id") is None and x.get("kaynak") == "tur"]
        self.assertEqual((ana[0]["ajan"], ana[0]["surec"]), ("ana-ajan", "orkestrasyon"))

    def test_toplu_kart_ve_dongu(self):
        plan = os.path.join(self.proje, "plan.json")
        json.dump([{"ref": "a", "baslik": "A", "basamak": "T1", "kabul_kriterleri": ["x"]},
                   {"ref": "b", "baslik": "B", "basamak": "T2", "kabul_kriterleri": ["y"], "bagimliliklar": ["a"]}],
                  open(plan, "w", encoding="utf-8"))
        r = self.cli("kart", "toplu", "--json-dosya", plan)
        self.assertEqual(r.returncode, 0, r.stderr)
        olusan = json.loads(r.stdout)
        self.assertEqual(olusan[1]["bagimliliklar"], [olusan[0]["id"]])


if __name__ == "__main__":
    unittest.main(verbosity=2)
