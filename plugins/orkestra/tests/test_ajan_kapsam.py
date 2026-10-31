"""I-292 P3 (ADR-0114, P-032): ajan türüne göre araç kapsamı — her kısıt için ihlal reddi ve izinli vaka."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import ajan_kapsam as AK  # noqa: E402

CFG = AK.ayar_yukle()
P = "C:/proje"


def k(tur, arac, **girdi):
    return AK.karar("orkestra:" + tur, arac, girdi, CFG, P, girdi.pop("_kart", None))


class KabukKisitlari(unittest.TestCase):
    RET = [
        'psql -c "INSERT INTO t VALUES (1)"',
        'psql -c "select 1; UPDATE t SET a=1"',
        'psql -c "DELETE FROM t"',
        'psql -c "DROP TABLE t"',
        'psql -c "select 1"; rm -rf x',
        "echo x > dosya.txt",
        "cat a >> b.md",
        "tee out.txt",
        "rm a.txt",
        "mv a b",
        "git commit -m x",
        "git -C repo push",
        "sed -i s/a/b/ f",
        "pip install x",
        "python -c \"open('a','w').write('x')\"",
        "Set-Content a.txt 'x'",
        "Remove-Item a.txt",
        "'x' | Out-File a.txt",
        "ls | xargs rm",
    ]
    IZIN = [
        'psql -c "SELECT * FROM t"',
        "grep -rn foo . 2>/dev/null",
        "cat a.txt | head -5",
        "git log --oneline",
        "git status",
        "ls -la && pwd",
        "python -c \"print(1)\"",
        "Get-Content a.txt",
        "Select-String -Path a.txt foo",
        'echo "a > b"',
    ]

    def test_bash_ihlalleri_reddedilir(self):
        for c in self.RET:
            with self.subTest(c=c):
                self.assertIsNotNone(k("arastirmaci", "Bash", command=c))

    def test_powershell_ihlalleri_reddedilir(self):
        for c in self.RET:
            with self.subTest(c=c):
                self.assertIsNotNone(k("arastirmaci", "PowerShell", command=c))

    def test_okuma_komutlari_izinli(self):
        for c in self.IZIN:
            for arac in ("Bash", "PowerShell"):
                with self.subTest(c=c, arac=arac):
                    self.assertIsNone(k("arastirmaci", arac, command=c))

    def test_dort_salt_okuma_ajani_kapsamda(self):
        for tur in ("arastirmaci", "perspektif-ajani", "skill-avcisi", "denetci"):
            self.assertIsNotNone(k(tur, "Bash", command="rm x"), tur)

    def test_kapsam_disi_ajan_etkilenmez(self):
        self.assertIsNone(k("isci-t2", "Bash", command="rm x"))
        self.assertIsNone(k("arsivci", "Bash", command="mv a b"))


class YazmaKisitlari(unittest.TestCase):
    def test_perspektif_yalniz_rapor(self):
        self.assertIsNone(k("perspektif-ajani", "Write", file_path=P + "/.claude/orkestra/perspektif/perspektif_20261031.md"))
        self.assertIsNotNone(k("perspektif-ajani", "Write", file_path=P + "/.claude/rules/x.md"))
        self.assertIsNotNone(k("perspektif-ajani", "Write", file_path=P + "/memory/MEMORY.md"))

    def test_skill_avcisi_yalniz_taslak(self):
        self.assertIsNone(k("skill-avcisi", "Write", file_path=P + "/.claude/orkestra/onerilen_skill/ornek/SKILL.md"))
        self.assertIsNone(k("skill-avcisi", "Write", file_path=P + "/.claude/orkestra/onerilen_skill/ornek/GEREKCE.md"))
        self.assertIsNotNone(k("skill-avcisi", "Write", file_path=P + "/.claude/skills/ornek/SKILL.md"))

    def test_denetci_yalniz_kart_ciktisi(self):
        cikti = [P + "/is/rapor.md"]
        self.assertIsNone(AK.karar("orkestra:denetci", "Edit", {"file_path": P + "/is/rapor.md"}, CFG, P, cikti))
        self.assertIsNotNone(AK.karar("orkestra:denetci", "Edit", {"file_path": P + "/baska.py"}, CFG, P, cikti))
        self.assertIsNotNone(AK.karar("orkestra:denetci", "Edit", {"file_path": P + "/is/rapor.md"}, CFG, P, None))

    def test_ayar_kapali_ve_golge(self):
        kapali = dict(CFG, mod="kapali")
        self.assertIsNone(AK.karar("orkestra:arastirmaci", "Bash", {"command": "rm x"}, kapali, P))
        self.assertEqual(AK.mod_bul(dict(CFG, mod="golge")), "golge")


if __name__ == "__main__":
    unittest.main()
