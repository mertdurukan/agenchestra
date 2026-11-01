"""I-003 hız: PreToolUse süreç başlatma maliyeti salt okuma araçlarında kaldırıldı; kimlik klasörü kapısı korunur."""
import json, os, re, unittest

HOOKS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks", "hooks.json")


class PreToolUseMatcher(unittest.TestCase):
    def setUp(self):
        self.pre = json.load(open(HOOKS, encoding="utf-8"))["hooks"]["PreToolUse"]

    def test_salt_okuma_araclari_genel_kapiya_girmez(self):
        genel = re.compile(self.pre[0]["matcher"])
        for a in ("Read", "Grep", "Glob", "ToolSearch"):
            self.assertIsNone(genel.search(a), a)

    def test_diger_her_arac_kapida(self):
        genel = re.compile(self.pre[0]["matcher"])
        for a in ("Bash", "PowerShell", "Edit", "Write", "MultiEdit", "NotebookEdit", "Agent", "Skill", "WebFetch",
                  "mcp__ccd_turn__wrap_up", "mcp__ccd_turn__update_plan", "mcp__github__create_branch",
                  "ReadMcpResourceTool", "GrepX", "Readme"):
            self.assertIsNotNone(genel.search(a), a)

    def test_kimlik_klasoru_okumasi_kapidan_gecer(self):
        ikinci = self.pre[1]
        self.assertEqual(ikinci["matcher"], "Read|Grep|Glob")
        self.assertEqual({h["if"].split("(")[0] for h in ikinci["hooks"]}, {"Read", "Grep", "Glob"})
        for h in ikinci["hooks"]:
            self.assertIn("/credentials/", h["if"])
        komutlar = {h["command"] for h in self.pre[0]["hooks"]} | {h["command"] for h in ikinci["hooks"]}
        self.assertEqual(len(komutlar), 1, "tüm girişler aynı hook komutunu çalıştırır")


if __name__ == "__main__":
    unittest.main()
