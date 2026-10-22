"""ADR-0037 (I-189): hook reddi ve Bash'e PowerShell cmdlet'i hata defterine davranış hatası olarak düşer."""
import json
import os

import test_cekirdek as TC


class HookDavranisKaydi(TC.Cekirdek):
    def hata_satirlari(self):
        yol = os.path.join(self.sd, "hata.jsonl")
        if not os.path.exists(yol):
            return []
        with open(yol, encoding="utf-8") as f:
            return [json.loads(s) for s in f if s.strip()]

    def bash(self, komut):
        return self.hook("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": komut}})

    def test_hook_reddi_kayda_duser(self):
        yol = os.path.join(self.sd, "gorevler", "G-001.json")
        c = self.hook("PreToolUse", {"tool_name": "Write", "tool_input": {"file_path": yol, "content": "{}"}})
        self.assertEqual(self.karar(c), "deny")
        (s,) = self.hata_satirlari()
        self.assertEqual((s["tur"], s["sinif"], s["kaynak"]), ("hook-red", "davranis", "davranis"))
        self.assertEqual(s["kok"]["kaynak"], "betik")  # kapı kimliksiz: kural değil kod kapısı
        self.assertIn("görev kartları", s["ileti"])

    def test_bash_powershell_cmdlet_kayda_duser_engellenmez(self):
        c = self.bash("Get-ChildItem C:\\x")
        self.assertNotEqual(self.karar(c), "deny")
        (s,) = self.hata_satirlari()
        self.assertEqual((s["tur"], s["kok"]["kaynak"]), ("kabuk-sozdizimi", "istem"))
        self.assertIsNone(s["kok"]["onlenebilir"])

    def test_bash_env_degiskeni_kayda_duser(self):
        self.bash("echo $env:PATH")
        self.assertEqual([s["tur"] for s in self.hata_satirlari()], ["kabuk-sozdizimi"])

    def test_gecerli_bash_kayit_uretmez(self):
        self.bash("ls -la")
        self.bash('echo "Get-ChildItem is a cmdlet"')
        self.bash("git status --short")
        self.assertEqual(self.hata_satirlari(), [])


if __name__ == "__main__":
    import unittest
    unittest.main()
