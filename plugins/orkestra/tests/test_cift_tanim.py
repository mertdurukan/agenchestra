"""I-464: scripts altındaki modüllerde aynı adlı iki üst düzey def/class olmaz.

Python ikinci tanımı hatasız kabul eder ve birinciyi sessizce ezer; çift tanım genellikle birleştirme ya da kopyalama
sırasında doğar ve yazım anında görünmez. En erken zorlanabilir sınır bu testtir (CI koşar)."""
import ast
import os
import unittest

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")


def cift_tanimlar(kaynak: str) -> list:
    """Modül düzeyinde birden çok kez tanımlanan def/class adları (satırlarıyla). `if`/`try` dalları sayılmaz:
    koşullu yedek tanımlar (ör. içe aktarma hatasında) bilinçlidir."""
    gorulen, cift = {}, []
    for dugum in ast.parse(kaynak).body:
        if isinstance(dugum, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if dugum.name in gorulen:
                cift.append(f"{dugum.name} ({gorulen[dugum.name]}, {dugum.lineno})")
            else:
                gorulen[dugum.name] = dugum.lineno
    return cift


class CiftTanim(unittest.TestCase):
    def test_yardimci_ciftleri_bulur(self):
        self.assertEqual(cift_tanimlar("def a():\n    pass\n\n\ndef a():\n    pass\n"), ["a (1, 5)"])
        self.assertEqual(cift_tanimlar("try:\n    def a(): pass\nexcept Exception:\n    def a(): pass\n"), [])

    def test_scripts_cift_tanim_yok(self):
        bulunan = {}
        for ad in sorted(os.listdir(SCRIPTS)):
            if not ad.endswith(".py"):
                continue
            with open(os.path.join(SCRIPTS, ad), encoding="utf-8") as f:
                cift = cift_tanimlar(f.read())
            if cift:
                bulunan[ad] = cift
        self.assertEqual(bulunan, {}, "modül düzeyinde çift tanım: ikinci tanım birinciyi sessizce ezer")


if __name__ == "__main__":
    unittest.main()
