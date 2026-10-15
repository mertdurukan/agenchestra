"""Orkestra çekirdek testleri: `python -m unittest discover -s plugins/orkestra/tests -v`

Gerçek hook girdilerini (stdin JSON) geçici bir projede sınar: kapılar, defter, token defteri, bitiş kapısı.
"""
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ic_kos  # noqa: E402  (CLI'yi süreç içinde koşar)

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(KOK, "scripts", "orkestra.py")
HOOK = os.path.join(KOK, "scripts", "hook.py")
OTURUM = "test-oturum-1"


def kos(args, cwd, ortam=None, stdin=None):
    env = dict(os.environ, CLAUDE_CODE_SESSION_ID=OTURUM, PYTHONUTF8="1")
    env.pop("CLAUDE_PROJECT_DIR", None)
    env.update(ortam or {})
    return ic_kos.kos(args, cwd=cwd, env=env, input=stdin)


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
        r = self.cli("kart", "yeni", "--soru", "Kısa test sorusu?", "--baslik", "README satırı", "--basamak", "T1", "--kabul", "satır eklendi",
                     "--yazma", "docs/**", *([] if "--sinif" in ek else ["--sinif", "belge"]), *ek)  # G-109: sinif zorunlu
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
        self.assertEqual(self.cli("kart", "denetim", g, "--karar", "ret", "--neden", "kapsam-eksik", "--gerekce", "k1 kanıtsız", "--talimat", "kanıt ekle", ajan_id="d1", ajan_tipi="orkestra:denetci").returncode, 0)
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

    def test_sayac_alt_klasorden_de_proje_kaydina_yazar(self):
        """Çalışma dizini proje içi alt klasörken (.claude/orkestra) tur kaydı projenin maliyet.jsonl dosyasına düşer."""
        r = kos([CLI, "maliyet", "tur", "--oturum", OTURUM, "--model", "claude-opus-5-5",
                 "--giris", "7", "--cikis", "11", "--onb-okuma", "0", "--onb-yazma", "0", "--sure-ms", "1"], self.sd)
        self.assertEqual(r.returncode, 0, r.stderr)
        satirlar = [json.loads(s) for s in open(os.path.join(self.sd, "maliyet.jsonl"), encoding="utf-8") if s.strip()]
        tur = [x for x in satirlar if x.get("kaynak") == "tur" and x.get("cikis") == 11]
        self.assertEqual(len(tur), 1, satirlar)

    def test_sayac_orkestra_kapali_klasorde_sessiz_cikar(self):
        """.claude/orkestra olmayan klasörde maliyet tur 0 ile çıkar ve hiçbir dosya oluşturmaz."""
        kapali = tempfile.mkdtemp(prefix="ork_kapali_")
        try:
            r = kos([CLI, "maliyet", "tur", "--oturum", OTURUM, "--model", "claude-opus-5-5",
                     "--giris", "1", "--cikis", "2", "--onb-okuma", "0", "--onb-yazma", "0", "--sure-ms", "1"], kapali)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(os.listdir(kapali), [])
        finally:
            shutil.rmtree(kapali, ignore_errors=True)

    def test_kabuk_kapisi_ornekleri(self):
        """Komut konumu, tırnak içi veri, zincir ve korunan dosya hedefi ayrımı."""
        ornekler = [
            ("orkestra kart liste", "allow"),
            ("cd x && orkestra kart teslim G-1", "deny"),
            ("python C:/a/b/orkestra.py kart liste", "allow"),
            ('python "C:/x y/orkestra.py" defter ekle G --surec is', "allow"),
            ("orkestra.cmd maliyet ozet", "allow"),
            ("grep -n x orkestra.py hook.py", None),
            ("cat /c/a/orkestra.py | head", None),
            ('cd /x && python -c "s = \'cd y && orkestra kart teslim G-1\'"', None),
            ('orkestra kart denetim G-1 --karar ret --gerekce "k1; k2 | eksik"', "allow"),
            ("echo x >> .claude/orkestra/ortak_defter.md", "deny"),
            ("cat >> ork_lib.py <<'EOF'\nrows = jsonl_oku('maliyet.jsonl')\nEOF", None),
        ]
        for komut, bek in ornekler:
            c = self.hook("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": komut}})
            self.assertEqual(self.karar(c), bek, komut)

    def test_toplu_kart_ve_dongu(self):
        plan = os.path.join(self.proje, "plan.json")
        json.dump([{"ref": "a", "soru": "Kısa test sorusu?", "baslik": "A", "sinif": "belge", "basamak": "T1", "kabul_kriterleri": ["x"]},
                   {"ref": "b", "soru": "Kısa test sorusu?", "baslik": "B", "sinif": "belge", "basamak": "T2", "kabul_kriterleri": ["y"], "bagimliliklar": ["a"]}],
                  open(plan, "w", encoding="utf-8"))
        r = self.cli("kart", "toplu", "--json-dosya", plan)
        self.assertEqual(r.returncode, 0, r.stderr)
        olusan = json.loads(r.stdout)
        self.assertEqual(olusan[1]["bagimliliklar"], [olusan[0]["id"]])

    def test_yeni_defter_kaydi_oturum_tasir(self):
        tr = os.path.join(self.tdir, OTURUM, "subagents", "agent-ab12.jsonl")
        satir = {"type": "assistant", "timestamp": "2026-10-13T10:00:00Z",
                 "message": {"model": "claude-sonnet-5-5", "content": [{"type": "text", "text": "x"}],
                             "usage": {"input_tokens": 1, "output_tokens": 1}}}
        with open(tr, "w", encoding="utf-8") as f:
            f.write(json.dumps(satir) + chr(10))
        # hook yolu: ortamdaki oturum kimliği HOOK girdisindekinden farklı; oturum girdiden gelmeli
        def hook_kos(olay, g):
            g = dict({"session_id": OTURUM, "cwd": self.proje, "transcript_path": self.ana_tr, "hook_event_name": olay}, **g)
            r = kos([HOOK, olay], self.proje, ortam={"CLAUDE_CODE_SESSION_ID": "ortam-baska"}, stdin=json.dumps(g))
            self.assertEqual(r.returncode, 0, r.stderr)
        hook_kos("SubagentStop", {"agent_id": "ab12", "agent_type": "orkestra:isci-t2", "agent_transcript_path": tr,
                                  "last_assistant_message": "bitti"})
        # Stop yolu (ana ajan, gorev '-'): araç çağıran bir tur
        ana = {"type": "assistant", "timestamp": "2026-10-13T10:00:00Z",
               "message": {"model": "claude-opus-5-5", "content": [{"type": "tool_use", "name": "Agent", "input": {}}],
                           "usage": {"input_tokens": 1, "output_tokens": 1}}}
        with open(self.ana_tr, "w", encoding="utf-8") as f:
            f.write(json.dumps(ana) + chr(10))
        hook_kos("Stop", {"last_assistant_message": "tur bitti"})
        kay = [json.loads(s) for s in open(os.path.join(self.sd, "ortak_defter.jsonl"), encoding="utf-8")]
        self.assertEqual({k["ajan"] for k in kay}, {"orkestra:isci-t2", "ana-ajan"}, kay)
        self.assertTrue(all(k.get("oturum") == OTURUM for k in kay), kay)
        # CLI yolu: oturum ortam değişkeninden
        self.cli("defter", "ekle", "G-001", "--surec", "is", "--yaptim", "y")
        son = [json.loads(s) for s in open(os.path.join(self.sd, "ortak_defter.jsonl"), encoding="utf-8")][-1]
        self.assertEqual(son["oturum"], OTURUM)


class PanelVeri(unittest.TestCase):
    """Panel veri katmanı: ozet.py defter ve bugün, analitik.py trend ve sıçrama uyarıları (geçici durum klasörü)."""

    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_panel_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        r = kos([CLI, "baslat"], self.proje)
        self.assertEqual(r.returncode, 0, r.stderr)
        sys.path.insert(0, os.path.join(KOK, "scripts"))
        import analitik
        import ozet
        self.A, self.O = analitik, ozet

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)

    def _yaz(self, ad, satirlar):
        with open(os.path.join(self.sd, ad), "w", encoding="utf-8") as f:
            for s in satirlar:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")

    def _maliyet(self, gun_once, saat, usd, **ek):
        z = (datetime.datetime.now().astimezone().replace(hour=saat, minute=0, second=0, microsecond=0)
             - datetime.timedelta(days=gun_once))
        r = {"zaman": z.isoformat(timespec="seconds"), "oturum": "o1", "ajan": "ana-ajan", "surec": "orkestrasyon",
             "model": "claude-opus-5-5", "gorev": "-", "kaynak": "tur", "maliyet_usd": usd}
        r.update(ek)
        return r

    def test_defter_temizleme_ve_olay(self):
        self._yaz("ortak_defter.jsonl", [
            {"gorev": "G-001", "surec": "sentez", "ajan": "ana-ajan", "yaptim": "x", "sonuc": "TESLİM", "zaman": "2026-10-13T10:00:00+03:00"},
            {"gorev": "-", "surec": "orkestrasyon", "ajan": "ana-ajan", "oturum": "o9", "zaman": "2026-10-13T10:05:00+03:00",
             "yaptim": "x", "sonuc": "**Yargı:** Belge [rapor.md](rapor.md) hazır; `kod` ve __kalın__ yok.\n\n- üç madde daha var ve cümle uzun"},
            {"gorev": "G-002", "surec": "denetim", "ajan": "orkestra:denetci", "yaptim": "G-002 denetim", "sonuc": "", "zaman": "2026-10-13T10:06:00+03:00"},
        ])
        o = self.O.olustur(self.sd, self.proje)
        d = o["defter"]
        self.assertEqual([r["olay"] for r in d], [True, False, True])
        # olay yalnız karta bağlı kayıtlarda; gorev '-' ise kısa cümle bile olay değildir
        self._yaz("ortak_defter.jsonl", [
            {"gorev": "G-013", "surec": "is", "ajan": "a", "sonuc": "G-013 Word yeniden üretim"},
            {"gorev": "G-013", "surec": "sentez", "ajan": "a", "sonuc": "TESLİM"},
            {"gorev": "-", "surec": "orkestrasyon", "ajan": "a", "sonuc": "Üç denetim de sürüyor."},
            {"gorev": "-", "surec": "orkestrasyon", "ajan": "a", "sonuc": "G-010 ve G-011 denetimde."},
            {"gorev": "G-016", "surec": "is", "ajan": "a", "sonuc": "G-016 pane and band"},
        ])
        self.assertEqual([r["olay"] for r in self.O.olustur(self.sd, self.proje)["defter"]], [True, True, False, False, True])
        self.assertEqual(self.O._KART_KIMLIK.pattern, chr(92) + "b[A-Z]{1,3}-" + chr(92) + "d+" + chr(92) + "b")
        self.assertEqual(d[0]["metin"], "TESLİM")
        self.assertEqual(d[1]["oturum"], "o9")
        self.assertNotIn("**", d[1]["metin"])
        self.assertNotIn("`", d[1]["metin"])
        self.assertNotIn("](", d[1]["metin"])
        self.assertIn("Belge rapor.md hazır", d[1]["metin"])
        self.assertTrue(all(len(r["metin"]) <= 160 and "oturum" in r for r in d))
        self._yaz("ortak_defter.jsonl", [{"gorev": "-", "surec": "is", "ajan": "a", "sonuc": f"kayıt {i} burada uzun bir cümledir"}
                                         for i in range(30)])
        self.assertEqual(len(self.O.olustur(self.sd, self.proje)["defter"]), 20)

    def test_eski_defter_kaydi_maliyetten_geri_dolar(self):
        d = [{"gorev": "-", "surec": "orkestrasyon", "ajan": "ana-ajan", "zaman": "2026-10-13T10:00:00+03:00", "sonuc": "a"},
             {"gorev": "-", "surec": "orkestrasyon", "ajan": "ana-ajan", "zaman": "2026-10-13T11:00:00+03:00", "sonuc": "b"},
             {"gorev": "-", "surec": "orkestrasyon", "ajan": "baska", "zaman": "2026-10-13T10:00:00+03:00", "sonuc": "c"},
             {"gorev": "-", "surec": "orkestrasyon", "ajan": "ana-ajan", "zaman": "2026-10-13T12:00:00+03:00", "oturum": "kendi", "sonuc": "d"}]
        self._yaz("ortak_defter.jsonl", d)
        self._yaz("maliyet.jsonl", [
            self._maliyet(0, 1, 1.0, zaman="2026-10-13T10:00:02+03:00", oturum="oA"),   # +2 sn: eşleşir
            self._maliyet(0, 1, 1.0, zaman="2026-10-13T11:00:03+03:00", oturum="oB")])  # +3 sn: eşleşmez
        raw = open(os.path.join(self.sd, "ortak_defter.jsonl"), "rb").read()
        sonuc = [r["oturum"] for r in self.O.olustur(self.sd, self.proje)["defter"]]
        self.assertEqual(sonuc, ["oA", None, None, "kendi"])
        self.assertEqual(raw, open(os.path.join(self.sd, "ortak_defter.jsonl"), "rb").read())  # dosya değişmez

    def test_geri_doldur_en_yakin_ve_esitlikte_none(self):
        d = [{"gorev": "-", "surec": "o", "ajan": "ana-ajan", "zaman": "2026-10-13T10:00:00+03:00", "sonuc": "a"},
             {"gorev": "-", "surec": "o", "ajan": "ana-ajan", "zaman": "2026-10-13T11:00:00+03:00", "sonuc": "b"}]
        self._yaz("ortak_defter.jsonl", d)
        self._yaz("maliyet.jsonl", [
            self._maliyet(0, 1, 1.0, zaman="2026-10-13T09:59:59+03:00", oturum="oA"),   # -1 sn
            self._maliyet(0, 1, 1.0, zaman="2026-10-13T10:00:00+03:00", oturum="oB"),   # 0 sn → kazanır
            self._maliyet(0, 1, 1.0, zaman="2026-10-13T10:59:59+03:00", oturum="oC"),   # eşit mesafe, farklı oturum
            self._maliyet(0, 1, 1.0, zaman="2026-10-13T11:00:01+03:00", oturum="oD")])
        self.assertEqual([r["oturum"] for r in self.O.olustur(self.sd, self.proje)["defter"]], ["oB", None])

    def test_bugun_uc_kaynakta_tutarli(self):
        kay = [self._maliyet(0, 1, 5.55), self._maliyet(0, 2, 1.1),
               self._maliyet(1, 3, 40.0), self._maliyet(2, 3, 8.0)]
        # UTC damgalı kayıt: yerel gün sınırına göre sayılmalı (önek karşılaştırmasıyla değil)
        yerel = datetime.datetime.now().astimezone().replace(hour=0, minute=30, second=0, microsecond=0)
        kay.append(dict(self._maliyet(0, 1, 2.2), zaman=yerel.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))
        self._yaz("maliyet.jsonl", kay)
        ozet_bugun = self.O.olustur(self.sd, self.proje)["maliyet"]["bugun"]
        trend_bugun = self.A.olustur(self.sd, self.proje)["trend"]["gunluk"][-1]["usd"]
        self.assertAlmostEqual(ozet_bugun, 8.85, places=2)
        self.assertLessEqual(abs(ozet_bugun - trend_bugun), 0.01)
        self.assertAlmostEqual(self.A.bugun_usd(self.A.L.maliyet_kayitlari(self.sd)), ozet_bugun, places=3)
        # tum_alanlar: bu geçici proje çalışma alanı listesinde değilse satır bulunamaz; alan listesini bu projeye sabitle
        eski = self.A._alan_listesi
        self.A._alan_listesi = lambda: [{"id": "x", "ad": "x", "yol": self.proje, "orkestra": True}]
        try:
            satir = self.A.tum_alanlar()["alanlar"][0]
        finally:
            self.A._alan_listesi = eski
        self.assertLessEqual(abs(satir["bugun"] - ozet_bugun), 0.01)

    def test_trend_ilk_kayit_gununden_baslar_ve_sicrama_metni(self):
        kay = [self._maliyet(4, 10, 10.0), self._maliyet(3, 10, 12.0), self._maliyet(2, 10, 11.0),
               self._maliyet(1, 10, 60.0, ajan="orkestra:isci-t2"), self._maliyet(0, 1, 90.0)]
        self._yaz("maliyet.jsonl", kay)
        a = self.A.olustur(self.sd, self.proje)
        g = a["trend"]["gunluk"]
        ilk = (datetime.date.today() - datetime.timedelta(days=4)).isoformat()
        self.assertEqual(g[0]["donem"], ilk)
        self.assertEqual(a["trend"]["ilk_kayit"], ilk)
        self.assertEqual(len(g), 5)
        # sıçrama: dünkü tam gün uyarılır, bugünün kısmi günü ($90) uyarılmaz
        gun = [u for u in a["birim"]["uyarilar"] if u["tur"] == "gun"]
        self.assertEqual(len(gun), 1)
        dun = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%d.%m")
        self.assertRegex(gun[0]["metin"], rf"^{dun}: önceki günlerin 5,\d katı \(\$60 · ort\. \$11\)$")
        self.assertEqual(self.A.ajan_adi("orkestra:isci-t2"), "İşçi T2")
        self.assertEqual(self.A.ajan_adi("orkestra:denetci"), "Denetçi")
        t = self.A.tum_alanlar()
        self.assertLessEqual(t["gunluk"][0]["donem"], datetime.date.today().isoformat())


    def test_defter_metni_dusus_ve_baslik_kesme(self):
        """Defter metni sonuc/yaptim boşsa not/sonraki ve diğer metin alanlarına düşer; uzun kart başlığı '…' ile kesilir."""
        O = self.O
        self.assertEqual(O.defter_metni({"sonuc": "", "yaptim": None, "not": "**önemli** not"}), "önemli not")
        self.assertEqual(O.defter_metni({"sonuc": " ", "yaptim": "", "sonraki": "denetim bekliyor"}), "denetim bekliyor")
        self.assertEqual(O.defter_metni({"sonuc": None, "yaptim": None, "gorev": "G-1", "ozel_alan": "serbest metin"}), "serbest metin")
        self.assertEqual(O.defter_metni({"sonuc": "tamam", "not": "ikincil"}), "tamam")
        self.assertEqual(O.defter_metni({"gorev": "G-1", "ajan": "ana-ajan", "zaman": "2026-10-13T10:00:00+03:00"}), "")
        uzun = "x" * 100
        k = O.kisalt_baslik(uzun)
        self.assertEqual(len(k), 80)
        self.assertTrue(k.endswith("…"))
        self.assertEqual(O.kisalt_baslik("kısa başlık"), "kısa başlık")
        self.assertEqual(O.kisalt_baslik("y" * 80), "y" * 80)


class Bayatlik(unittest.TestCase):
    """Önbellek bayatlığı karşılaştırması ve projeye_kur autoUpdate."""

    def setUp(self):
        self.t = tempfile.mkdtemp(prefix="ork_bay_")
        self.depo = os.path.join(self.t, "depo")
        self.kaynak = os.path.join(self.depo, "plugins", "orkestra")
        self.kopya = os.path.join(self.t, "onbellek", "orkestra", "x")
        for k in (self.kaynak, self.kopya):
            os.makedirs(os.path.join(k, "scripts"))
            with open(os.path.join(k, "scripts", "a.py"), "w", encoding="utf-8") as f:
                f.write("print(1)" + chr(10))
        sys.path.insert(0, os.path.join(KOK, "scripts"))
        import ork_lib
        self.L = ork_lib

    def tearDown(self):
        shutil.rmtree(self.t, ignore_errors=True)

    def test_ayni_ise_uyari_yok_pycache_ve_in_use_yok_sayilir(self):
        os.makedirs(os.path.join(self.kopya, "scripts", "__pycache__"))
        with open(os.path.join(self.kopya, "scripts", "__pycache__", "a.pyc"), "wb") as f:
            f.write(b"x")
        with open(os.path.join(self.kopya, ".in_use"), "w") as f:
            f.write("1")
        self.assertIsNone(self.L.bayatlik(self.kopya, self.depo))

    def test_in_use_klasoru_ve_orphaned_at_yok_sayilir(self):
        os.makedirs(os.path.join(self.kopya, ".in_use"))
        for pid in ("123", "20952"):
            with open(os.path.join(self.kopya, ".in_use", pid), "w") as f:
                f.write(pid)
        with open(os.path.join(self.kopya, ".orphaned_at"), "w") as f:
            f.write("2026-10-13")
        self.assertIsNone(self.L.bayatlik(self.kopya, self.depo))

    def test_farkli_dosya_sayilir(self):
        with open(os.path.join(self.kopya, "scripts", "a.py"), "w", encoding="utf-8") as f:
            f.write("print(2)" + chr(10))
        with open(os.path.join(self.kaynak, "yeni.md"), "w") as f:
            f.write("y")
        b = self.L.bayatlik(self.kopya, self.depo)
        self.assertEqual(b["farkli"], 2)
        self.assertIn(b["kaynakta_commitsiz"], (None, False, True))

    def test_kaynak_yok_ya_da_kaynak_icinde_sessiz(self):
        self.assertIsNone(self.L.bayatlik(self.kopya, os.path.join(self.t, "yok")))
        with open(os.path.join(self.kaynak, "yeni.md"), "w") as f:
            f.write("y")
        self.assertIsNone(self.L.bayatlik(self.kaynak, self.depo))

    def test_projeye_kur_autoupdate_korur_ve_tekrar_guvenli(self):
        import contextlib
        import io
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(KOK)), "araclar"))
        import projeye_kur as P
        proje = os.path.join(self.t, "proje")
        os.makedirs(os.path.join(proje, ".claude"))
        yol = os.path.join(proje, ".claude", "settings.json")
        with open(yol, "w", encoding="utf-8") as f:
            json.dump({"extraKnownMarketplaces": {P.MARKET: {"source": {"source": "directory", "path": "Z:/ozel"}}, "baska": {"x": 1}}, "ozel": 5}, f)
        for _ in range(2):
            with contextlib.redirect_stdout(io.StringIO()):
                P.ayar_birlestir(proje, True, False)
        with open(yol, encoding="utf-8") as f:
            s = json.load(f)
        m = s["extraKnownMarketplaces"]
        self.assertIs(m[P.MARKET]["autoUpdate"], True)
        self.assertEqual(m[P.MARKET]["source"]["path"], "Z:/ozel")
        self.assertEqual(m["baska"], {"x": 1})
        self.assertEqual(s["ozel"], 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
