"""`**Jira:**` alanı plan şablonunda ve /orkestra:is skill'inde anlatılır (ADR-0086, I-231 P4)."""
import os
import re
import sys
import unittest

_KOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(_KOK, "scripts"))
import is_kaydi as K  # noqa: E402
import paralellik as PR  # noqa: E402

SKILL = os.path.join(_KOK, "skills", "is", "SKILL.md")


def sablon() -> str:
    return K.sablon_metni("plan_sirali.md", "Deneme işi", None, "20261027")


class JiraSablon(unittest.TestCase):
    def test_sablon_jira_alanini_anlatir(self):
        m = re.search(r"\*\*Jira:\*\*[^\n]*", sablon())
        self.assertIsNotNone(m, "plan_sirali şablonunda `**Jira:**` yok")
        self.assertIn("jira_bagimlilik.json", m.group(0))
        self.assertIn("ADR-0086", m.group(0))

    def test_sablon_paralellik_ayristiricisinca_okunur(self):
        # Şablonun söylediği biçimde doldurulmuş P maddesi: `**Jira:**` ayrıştırılır, `**Önce:**` hatasız okunur
        metin = sablon() + "\n### P1 Madde\n\n**Jira:** PE-770\n\n**Önce:** yok\n\n**Yazma alanı:** scripts/a.py\n"
        md = PR.maddeler(metin)
        self.assertEqual(md[1]["jira"], "PE-770")
        self.assertEqual(md[1]["once_hatalari"], [])

    def test_sablon_kendi_basina_jira_maddesi_uretmez(self):
        # Yer tutucu yorum içinde durur; doldurulmamış şablon `**Jira:**` taşıyan madde sayılmaz
        self.assertEqual([m for m in PR.maddeler(sablon()).values() if m.get("jira")], [])

    def test_skill_jira_adimini_anlatir(self):
        with open(SKILL, encoding="utf-8") as f:
            s = f.read()
        self.assertIn("jira_bagimlilik.json", s)
        self.assertIn("orkestra is dalga <iş> --jira", s)
        self.assertIn("getAccessibleAtlassianResources", s)


if __name__ == "__main__":
    unittest.main()
