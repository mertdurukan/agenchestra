"""İzin politikası: kabuk ve MCP kapısı, mod/ortam/ezme katmanları, hook uçtan uca, doktor kontrolü."""
import json
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
        for a in ("getJiraIssue", "searchJiraIssuesUsingJql", "lookupJiraAccountId", "fetch", "search", "atlassianUserInfo"):
            self.assertEqual(karar(p + a), "allow", a)

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
        # eşleşme ".*": Read, Glob, Grep, Agent, Skill gibi araçlar da politikadan geçer (varsayılan Claude Code istemine düşmez)
        with open(os.path.join(KOK, "hooks", "hooks.json"), encoding="utf-8") as f:
            eslesme = json.load(f)["hooks"]["PreToolUse"][0]["matcher"]
        self.assertEqual(eslesme, ".*")
        for a in ("mcp__github__x", "WebFetch", "WebSearch", "Bash", "PowerShell", "Write", "Read", "Glob", "Grep", "Agent", "Skill"):
            self.assertRegex(a, eslesme)

    def test_session_start_politikayi_duyurur(self):
        g = {"session_id": OTURUM, "cwd": self.proje, "hook_event_name": "SessionStart", "source": "startup"}
        r = ic_kos.kos([HOOK, "SessionStart"], cwd=self.proje, env=self.env, input=json.dumps(g))
        ek = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("İzin politikası: geniş yetki açık", ek)
        self.env["ORKESTRA_IZIN"] = "0"
        r = ic_kos.kos([HOOK, "SessionStart"], cwd=self.proje, env=self.env, input=json.dumps(g))
        self.assertNotIn("İzin politikası", json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"])


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
