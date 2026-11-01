"""İzin politikası: kabuk ve MCP kapısı, mod/ortam/ezme katmanları, hook uçtan uca, doktor kontrolü."""
import json
import re
import os
import shutil
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(KOK, "scripts", "hook.py")
CLI = os.path.join(KOK, "scripts", "orkestra.py")
sys.path.insert(0, os.path.join(KOK, "scripts"))
import izin_politikasi as IP  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ic_kos  # noqa: E402

OTURUM = "izin-oturum"


def karar(arac, komut="", **kw):
    return IP.karar(arac, {"command": komut}, **kw)[0]


class Kabuk(unittest.TestCase):
    def setUp(self):
        self._ort = os.environ.get("ORKESTRA_IZIN")
        os.environ["ORKESTRA_IZIN"] = "genis"

    def tearDown(self):
        if self._ort is None:
            os.environ.pop("ORKESTRA_IZIN", None)
        else:
            os.environ["ORKESTRA_IZIN"] = self._ort

    def test_push_sorulur(self):
        for k in ("git push", "git push origin main", "git -C repo push -u origin b", "cd x && git push",
                  "git status; git push origin HEAD"):
            self.assertEqual(karar("Bash", k), "ask", k)
            self.assertEqual(karar("PowerShell", k), "ask", k)

    def test_zorla_silme_ayna_push_reddedilir(self):
        for k in ("git push --force", "git push -f origin main", "git push --force-with-lease origin main",
                  "git push origin --delete eski", "git push --mirror", "git push origin +main"):
            self.assertEqual(karar("Bash", k), "deny", k)

    def test_tirnak_ici_metin_veridir(self):
        self.assertEqual(karar("Bash", 'git commit -m "sonra git push yapılacak"'), "allow")
        self.assertEqual(karar("Bash", "echo 'gh pr create'"), "allow")

    def test_ic_ice_kabuk_ve_betik_kapiyi_asamaz(self):
        # tırnak içi kod başka bir kabuğa/yorumlayıcıya veriliyorsa gerçekten çalışır: veri sayılmaz
        for k in ('bash -c "git push origin main"', 'sh -c "git push"', 'powershell -Command "git push"',
                  "cmd /c git push", 'eval "git push"',
                  "python -c \"import subprocess;subprocess.run(['git','push'])\"",
                  "python -c \"import requests;requests.post('https://x.atlassian.net/a')\"",
                  "python - <<'EOF'\nimport requests\nrequests.post('https://a.atlassian.net/x', data=1)\nEOF",
                  "powershell -EncodedCommand ZQBjAGgA"):
            self.assertEqual(karar("Bash", k), "ask", k)
        for k in ("bash -c 'git push --force origin main'", 'sh -c "git push -f"'):
            self.assertEqual(karar("Bash", k), "deny", k)

    def test_ic_ice_zararsiz_komutlar_serbest(self):
        for k in ('python -c "print(1)"', 'bash -c "ls -la"', "python -c \"print('git commit -m x')\"",
                  "python -c \"import requests;requests.get('https://x.atlassian.net/a')\"",
                  "pytest -x tests/test_a.py"):
            self.assertEqual(karar("Bash", k), "allow", k)

    def test_gh_yazma_sorulur_okuma_serbest(self):
        for k in ("gh pr create --title x", "gh pr merge 3", "gh issue comment 4 -b x", "gh release create v1",
                  "gh api -X POST repos/a/b/issues", "gh api repos/a/b/issues -f title=x"):
            self.assertEqual(karar("Bash", k), "ask", k)
        for k in ("gh pr view 3", "gh pr list", "gh issue view 4", "gh api repos/a/b", "gh run list"):
            self.assertEqual(karar("Bash", k), "allow", k)

    def test_rest_yazma_sorulur_okuma_serbest(self):
        self.assertEqual(karar("Bash", "curl -X POST https://x.atlassian.net/rest/api/3/issue -d @a.json"), "ask")
        self.assertEqual(karar("Bash", "curl -X DELETE https://api.github.com/repos/a/b"), "ask")
        self.assertEqual(karar("PowerShell", "Invoke-RestMethod -Method Post -Uri https://x.atlassian.net/rest/api/3/issue -Body $b"), "ask")
        self.assertEqual(karar("Bash", "curl https://x.atlassian.net/rest/api/3/issue/1"), "allow")
        self.assertEqual(karar("Bash", "curl -X POST https://example.com/api -d x"), "allow")  # GitHub/Jira dışı adres

    def test_siradan_komutlar_serbest(self):
        for k in ("git status", "git commit -m x", "git log --oneline", "python x.py", "ls", "git pull"):
            self.assertEqual(karar("Bash", k), "allow", k)


class Mcp(unittest.TestCase):
    def setUp(self):
        self._ort = os.environ.get("ORKESTRA_IZIN")
        os.environ["ORKESTRA_IZIN"] = "genis"

    def tearDown(self):
        if self._ort is None:
            os.environ.pop("ORKESTRA_IZIN", None)
        else:
            os.environ["ORKESTRA_IZIN"] = self._ort

    def test_github_yazma_sorulur_okuma_serbest(self):
        for a in ("push_files", "create_or_update_file", "merge_pull_request", "delete_file", "create_pull_request",
                  "issue_write", "add_issue_comment", "pull_request_review_write", "create_branch", "yeni_bilinmeyen_arac"):
            self.assertEqual(karar(f"mcp__github__{a}"), "ask", a)
        for a in ("get_file_contents", "list_commits", "search_code", "issue_read", "pull_request_read", "get_me"):
            self.assertEqual(karar(f"mcp__github__{a}"), "allow", a)

    def test_jira_yazma_sorulur_okuma_serbest(self):
        p = "mcp__plugin_design_atlassian__"
        for a in ("createJiraIssue", "editJiraIssue", "transitionJiraIssue", "addCommentToJiraIssue", "addWorklogToJiraIssue",
                  "createConfluencePage", "updateConfluencePage", "createIssueLink"):
            self.assertEqual(karar(p + a), "ask", a)
        for a in ("getJiraIssue", "searchJiraIssuesUsingJql", "lookupJiraAccountId", "fetch", "search", "atlassianUserInfo",
                  "listJiraIssueComments", "discover", "executeRead"):
            self.assertEqual(karar(p + a), "allow", a)

    def test_uuid_adli_atlassian_sunucusu_sunucu_bazli_kapida(self):
        p = "mcp__73d9f9eb-9d44-4ce4-b615-490c4b090ae4__"
        for a in ("executeWrite", "executeDestructive", "createConfluenceContent", "updateConfluenceContent",
                  "addGraphContext", "yeni_bilinmeyen_arac"):
            self.assertEqual(karar(p + a), "ask", a)
        for a in ("executeRead", "discover", "getJiraIssue", "searchJiraIssuesUsingJql", "atlassianUserInfo",
                  "getAccessibleAtlassianResources",
                  "listJiraIssueComments"):
            self.assertEqual(karar(p + a), "allow", a)

    def test_sunucu_kimligi_degisse_de_execute_yazma_sorulur(self):
        p = "mcp__baska-kimlik-1234__"
        for a in ("executeWrite", "executeDestructive"):
            self.assertEqual(karar(p + a), "ask", a)
        self.assertEqual(karar(p + "executeRead"), "allow")

    def test_baska_sunucu_ve_yerlesik_arac_serbest(self):
        for a in ("mcp__Claude_Browser__navigate", "mcp__ccd_session__list_start_targets", "Edit", "Write", "WebFetch"):
            self.assertEqual(karar(a), "allow", a)


class Mod(unittest.TestCase):
    def setUp(self):
        self._ort = os.environ.get("ORKESTRA_IZIN")
        os.environ["ORKESTRA_IZIN"] = "genis"
        self.sd = tempfile.mkdtemp(prefix="ork_izin_")

    def tearDown(self):
        shutil.rmtree(self.sd, ignore_errors=True)
        if self._ort is None:
            os.environ.pop("ORKESTRA_IZIN", None)
        else:
            os.environ["ORKESTRA_IZIN"] = self._ort

    def test_ortam_kapali(self):
        os.environ["ORKESTRA_IZIN"] = "0"
        self.assertEqual(IP.karar("Bash", {"command": "git push"}, self.sd), (None, ""))

    def test_ortam_kapi_modu_geniş_yetki_vermez(self):
        os.environ["ORKESTRA_IZIN"] = "kapi"
        self.assertEqual(karar("Bash", "git push", sd=self.sd), "ask")
        self.assertIsNone(karar("Bash", "git status", sd=self.sd))
        self.assertIsNone(karar("Edit", sd=self.sd))

    def test_tanimsiz_mod_kapiya_duser(self):
        os.environ["ORKESTRA_IZIN"] = "sacma"
        self.assertEqual(IP.mod_bul({"mod": "genis"}), "kapi")

    def test_proje_ezmesi(self):
        os.environ.pop("ORKESTRA_IZIN", None)  # ortam ezmeyi de ezer; burada yalnız ezme dosyası sınanır
        with open(os.path.join(self.sd, "izin_politikasi.json"), "w", encoding="utf-8") as f:
            json.dump({"mod": "kapi"}, f)
        self.assertEqual(IP.mod_bul(IP.ayar_yukle(self.sd)), "kapi")
        self.assertIsNone(karar("Bash", "git status", sd=self.sd))
        self.assertEqual(karar("Bash", "git push", sd=self.sd), "ask")  # kapı ezmede de durur

    def test_bozuk_ayar_yedege_duser(self):
        cfg = IP.ayar_yukle(self.sd)
        self.assertEqual(cfg["mod"], "genis")  # eklentinin kendi dosyası geçerli
        self.assertEqual(IP.gecersiz_desenler(cfg), [])
        self.assertEqual(IP.gecersiz_desenler({"kabuk_kapi": [{"ad": "x", "desen": "("}]}), ["kabuk_kapi.x.desen"])


class HookUcAdanUca(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_izinhook_")
        self.ev = tempfile.mkdtemp(prefix="ork_ev_")
        self.env = dict(os.environ, CLAUDE_CODE_SESSION_ID=OTURUM, PYTHONUTF8="1", HOME=self.ev, USERPROFILE=self.ev)
        self.env["ORKESTRA_IZIN"] = "genis"
        self.env["ORKESTRA_MOD_KAPISI"] = "0"  # ADR-0115: varsayılan mod auto; bu sınıf plan modunda push `ask` kapısını sınar
        self.env.pop("CLAUDE_PROJECT_DIR", None)
        r = ic_kos.kos([CLI, "baslat"], cwd=self.proje, env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)
        shutil.rmtree(self.ev, ignore_errors=True)

    def pre(self, arac, girdi, cwd=None):
        g = {"session_id": OTURUM, "cwd": cwd or self.proje, "hook_event_name": "PreToolUse",
             "tool_name": arac, "tool_input": girdi}
        r = ic_kos.kos([HOOK, "PreToolUse"], cwd=cwd or self.proje, env=self.env, input=json.dumps(g))
        self.assertEqual(r.returncode, 0, r.stderr)
        return (json.loads(r.stdout).get("hookSpecificOutput") or {}) if r.stdout.strip() else {}

    def test_push_ask_force_deny_siradan_allow(self):
        self.assertEqual(self.pre("Bash", {"command": "git push origin main"}).get("permissionDecision"), "ask")
        self.assertEqual(self.pre("Bash", {"command": "git push --force"}).get("permissionDecision"), "deny")
        self.assertEqual(self.pre("Bash", {"command": "git status"}).get("permissionDecision"), "allow")

    def test_mcp_ve_yazma_araclari(self):
        self.assertEqual(self.pre("mcp__github__push_files", {}).get("permissionDecision"), "ask")
        self.assertEqual(self.pre("mcp__plugin_design_atlassian__getJiraIssue", {}).get("permissionDecision"), "allow")
        dosya = os.path.join(self.proje, "a.txt")
        self.assertEqual(self.pre("Write", {"file_path": dosya, "content": "x"}).get("permissionDecision"), "allow")

    def test_orkestra_cli_kimlik_eklemeye_devam_eder(self):
        c = self.pre("Bash", {"command": "orkestra is liste"})
        self.assertEqual(c.get("permissionDecision"), "allow")
        self.assertIn("--ajan-id", (c.get("updatedInput") or {}).get("command", ""))

    def test_zincirde_push_kapiya_takilir(self):
        c = self.pre("Bash", {"command": "orkestra is liste && git push"})
        self.assertEqual(c.get("permissionDecision"), "ask")

    def test_kapali_modda_hook_karar_vermez(self):
        self.env["ORKESTRA_IZIN"] = "0"
        self.assertEqual(self.pre("Bash", {"command": "git push"}), {})
        self.assertEqual(self.pre("Bash", {"command": "git status"}), {})

    def test_orkestrasiz_projede_karar_yok(self):
        bos = tempfile.mkdtemp(prefix="ork_bos_")
        try:
            self.assertEqual(self.pre("Bash", {"command": "git push"}, cwd=bos), {})
        finally:
            shutil.rmtree(bos, ignore_errors=True)

    def test_hooks_json_tum_araclari_kapsar(self):
        # ADR-0143: Read/Grep/Glob/ToolSearch genel kapıdan çıktı (hız); kimlik klasörü okumaları ikinci girişte kapıdan geçer
        with open(os.path.join(KOK, "hooks", "hooks.json"), encoding="utf-8") as f:
            pre = json.load(f)["hooks"]["PreToolUse"]
        genel = re.compile(pre[0]["matcher"])
        for a in ("mcp__github__x", "WebFetch", "WebSearch", "Bash", "PowerShell", "Write", "Agent", "Skill"):
            self.assertRegex(a, genel)
        for a in ("Read", "Glob", "Grep", "ToolSearch"):
            self.assertIsNone(genel.search(a), a)
        self.assertEqual(pre[1]["matcher"], "Read|Grep|Glob")

    def test_session_start_politikayi_duyurur(self):
        g = {"session_id": OTURUM, "cwd": self.proje, "hook_event_name": "SessionStart", "source": "startup"}
        r = ic_kos.kos([HOOK, "SessionStart"], cwd=self.proje, env=self.env, input=json.dumps(g))
        ek = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("İzin: geniş.", ek)
        self.env["ORKESTRA_IZIN"] = "0"
        r = ic_kos.kos([HOOK, "SessionStart"], cwd=self.proje, env=self.env, input=json.dumps(g))
        self.assertNotIn("İzin:", json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"])


class KimlikKapisi(unittest.TestCase):
    """ADR-0014: kimlik klasörü okunabilir (Read/Grep/Glob, tüm projeler); yazma ve kabuk yasak."""
    YOL = os.path.join(os.path.expanduser("~"), ".orkestra", "credentials")

    def setUp(self):
        self._ort = os.environ.pop("ORKESTRA_KIMLIK_OKUMA", None)

    def tearDown(self):
        os.environ.pop("ORKESTRA_KIMLIK_OKUMA", None)
        if self._ort is not None:
            os.environ["ORKESTRA_KIMLIK_OKUMA"] = self._ort

    def _k(self, arac, girdi, **cfg):
        return IP.karar(arac, girdi, cfg=dict({"mod": "kapi"}, **cfg))[0]

    def test_okuma_her_proje_ve_ortak_icin_serbest(self):
        for proje in ("DemoRoot", "BaskaProje", "_ortak"):
            y = os.path.join(self.YOL, proje, "db.env")
            self.assertNotEqual(self._k("Read", {"file_path": y}), "deny", y)
            self.assertNotEqual(self._k("Grep", {"pattern": "KEY", "path": os.path.dirname(y)}), "deny", y)
            self.assertNotEqual(self._k("Glob", {"pattern": "*.env", "path": os.path.dirname(y)}), "deny", y)

    def test_yazma_ve_kabuk_yasak(self):
        y = os.path.join(self.YOL, "DemoRoot", "db.env")
        for arac in ("Write", "Edit", "NotebookEdit"):
            self.assertEqual(self._k(arac, {"file_path": y}), "deny", arac)
        for arac in ("Bash", "PowerShell"):
            self.assertEqual(self._k(arac, {"command": f"cat {y}"}), "deny", arac)
            self.assertEqual(self._k(arac, {"command": "type ~/.orkestra/credentials/DemoRoot/db.env"}), "deny", arac)

    def test_ayar_kapaliyken_okuma_yasak(self):
        y = os.path.join(self.YOL, "DemoRoot", "db.env")
        self.assertEqual(self._k("Read", {"file_path": y}, kimlik_okuma=False), "deny")

    def test_ortam_degiskeni_okumayi_kapatir(self):
        y = os.path.join(self.YOL, "DemoRoot", "db.env")
        os.environ["ORKESTRA_KIMLIK_OKUMA"] = "0"
        self.assertEqual(self._k("Read", {"file_path": y}), "deny")

    def test_okuyucu_komutu_serbest_kalir(self):
        self.assertNotEqual(self._k("Bash", {"command": "orkestra kimlik liste"}), "deny")


class OnayKapisiKabuk(unittest.TestCase):
    """I-224: P-016 onay kapısı yalnız proje içi yazımı bekletir; kabukla yazım Edit/Write ile aynı kapıdan geçer;
    veri heredoc'undaki "push" metni kapıya takılmaz, gerçek `git push` takılır."""
    OID = "i224-onay-oturum"

    def setUp(self):
        import is_kaydi
        import is_onay
        self.is_onay = is_onay
        self.proje = tempfile.mkdtemp(prefix="ork_i224_")
        self.disari = tempfile.mkdtemp(prefix="ork_i224_scratch_")  # proje dışı (scratchpad / %TEMP% yerine)
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        self._env = dict(os.environ)
        for k in ("CLAUDE_PROJECT_DIR", "ORKESTRA_ONAY_KAPISI", "ORKESTRA_IS_KAPISI"):
            os.environ.pop(k, None)
        os.environ.update(CLAUDE_PROJECT_DIR=self.proje, ORKESTRA_SIRA_KAPISI="1", ORKESTRA_DOGRULAMA_KAPISI="0",
                          ORKESTRA_IZIN="genis")
        self.klasor = os.path.join(self.proje, "isler", "001-x")
        self.kayit = is_kaydi.is_ac(self.sd, "I-224 sınaması", self.klasor)
        with open(os.path.join(self.sd, "oturumlar", self.OID + ".json"), "w", encoding="utf-8") as f:
            json.dump({"is": self.kayit["id"]}, f)
        self.assertEqual(is_kaydi.is_al(self.sd, self.kayit["id"]).get("onay"), "bekliyor")

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        shutil.rmtree(self.proje, ignore_errors=True)
        shutil.rmtree(self.disari, ignore_errors=True)

    def pre(self, arac, girdi):
        """Hook'u süreç içinde koşar; (karar, neden)."""
        import contextlib
        import io
        import hook
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                hook.pre_tool_use({"tool_name": arac, "cwd": self.proje, "session_id": self.OID, "tool_input": girdi})
            except SystemExit:
                pass
        ham = buf.getvalue().strip()
        h = (json.loads(ham.splitlines()[-1]).get("hookSpecificOutput") or {}) if ham else {}
        return h.get("permissionDecision"), h.get("permissionDecisionReason", "")

    def kabuk(self, komut, arac="Bash"):
        return self.pre(arac, {"command": komut})[0]

    def test_k1_proje_disi_yazim_bekliyor_iken_serbest(self):
        d = os.path.join(self.disari, "not.txt")
        self.assertEqual(self.is_onay.yazma_engeli(self.kayit, self.proje, d), "")
        self.assertNotEqual(self.pre("Write", {"file_path": d, "content": "x"})[0], "deny")
        for arac, komut in (("Bash", f"echo x > {d}"), ("Bash", f"cat <<'EOF' > {d}\nmetin\nEOF"),
                            ("PowerShell", f'Set-Content -Path "{d}" -Value x'),
                            ("PowerShell", f"'x' | Out-File -FilePath '{d}' -Encoding utf8"),
                            ("Bash", f"cp a.txt {self.disari}/"), ("Bash", "python -m unittest 2>&1 > /dev/null"),
                            ("PowerShell", "git status > $null")):
            self.assertNotEqual(self.kabuk(komut, arac), "deny", komut)
        # proje içi Edit/Write hâlâ reddedilir; işin belgeleri ve adr/ serbest
        self.assertEqual(self.pre("Write", {"file_path": os.path.join(self.proje, "src", "a.py"), "content": "x"})[0], "deny")
        self.assertNotEqual(self.kabuk(f"echo x > {os.path.join(self.klasor, 'plan.md')}"), "deny")
        self.assertNotEqual(self.kabuk(f"echo x > {os.path.join(self.proje, 'adr', 'ADR-0001-x.md')}"), "deny")

    def test_k2_proje_ici_kabuk_yazimi_reddedilir(self):
        p = os.path.join(self.proje, "src", "a.py")
        for arac, komut in (("Bash", f"echo x > {p}"), ("Bash", f"echo x >> {p}"), ("Bash", f"printf x | tee {p}"),
                            ("Bash", f"cp /tmp/a.py {p}"), ("Bash", f"mv x.py {self.proje}/src/"),
                            ("Bash", f"cd {self.proje} && echo x > src/a.py"), ("Bash", f"rm -f {p}"),
                            ("Bash", f"cat > {p} <<'EOF'\nprint(1)\nEOF"),
                            ("PowerShell", f'Set-Content -Path "{p}" -Value x'), ("PowerShell", f"Set-Content '{p}' x"),
                            ("PowerShell", f'"x" | Out-File "{p}"'), ("PowerShell", f'Add-Content -LiteralPath "{p}" -Value x'),
                            ("PowerShell", f'Copy-Item a.py -Destination "{self.proje}\\src"'),
                            ("PowerShell", f"[IO.File]::WriteAllText('{p}', 'x')"),
                            ("PowerShell", "$f = 'x'; Set-Content $f 'y'"),
                            ("Bash", f"echo {{}} > {os.path.join(self.klasor, 'is.json')}")):
            self.assertEqual(self.kabuk(komut, arac), "deny", komut)
        # izin modu kapalı olsa da P-016 kapısı durur; onay verilince serbest
        os.environ["ORKESTRA_IZIN"] = "0"
        self.assertEqual(self.kabuk(f"echo x > {p}"), "deny")
        self.is_onay.yaz(self.sd, self.kayit["id"], "verildi", "test")
        self.assertNotEqual(self.kabuk(f"echo x > {p}"), "deny")

    def test_k3_heredoc_push_metni_reddedilmez_gercek_push_reddedilir(self):
        veri = ("git commit -F - <<'EOF'\nfix: git push kapısı düzeldi\nEOF",
                "cat <<EOF\nsonra git push origin main\nEOF",
                "@'\ngit push origin main\n'@ | Out-Host")
        for k in veri:
            self.assertEqual(karar("Bash", k), "allow", k)  # izin politikası: push sorusu yok
        # onay bekleyen işte de (hook'un tırnak maskeli metniyle) heredoc gövdesi push sayılmaz
        d = os.path.join(self.disari, "m.txt")
        self.assertNotEqual(self.kabuk(f"cat <<'EOF' > {d}\ngit push origin main\nEOF"), "deny")
        self.assertEqual(self.is_onay.kabuk_engeli('cat <<""\ngit push origin main\nEOF'), "")
        # gerçek push: izin politikasında ask, onay bekleyen işte deny; heredoc sonrası ve yorumlayıcıya giden gövde dahil
        for k in ("git push", "git push origin main", "cat <<'EOF'\nx\nEOF\ngit push origin main",
                  "cat <<'EOF' | bash\ngit push origin main\nEOF", "bash <<'EOF'\ngit push\nEOF",
                  "echo '<<X'\ngit push"):
            self.assertEqual(karar("Bash", k), "ask", k)
        self.assertIn(self.kabuk("git push origin main"), ("ask", "deny"))  # hook: izin kapısı (ask) onay kapısından önce
        self.assertTrue(self.is_onay.kabuk_engeli("git push origin main"))
        self.assertTrue(self.is_onay.kabuk_engeli('cat <<""\nx\nEOF\ngit push origin main'))


class Cli(unittest.TestCase):
    def test_goster_ve_sina(self):
        env = dict(os.environ, PYTHONUTF8="1")
        env["ORKESTRA_IZIN"] = "genis"
        r = ic_kos.kos([CLI, "izin", "goster"], cwd=KOK, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("mod: genis", r.stdout)
        r = ic_kos.kos([CLI, "izin", "sina", "--arac", "Bash", "--komut", "git push origin x"], cwd=KOK, env=env)
        self.assertTrue(r.stdout.startswith("ask"), r.stdout)


if __name__ == "__main__":
    unittest.main()
