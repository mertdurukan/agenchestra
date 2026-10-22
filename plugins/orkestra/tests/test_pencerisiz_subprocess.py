"""Başsız çalışma: eklentinin başlattığı her alt süreç Windows'ta konsol penceresi açmaz (cfg.PENCERESIZ).

Konsolsuz bir süreçten (hook, panel) çağrılan konsol programı yeni pencere açar. Bu test, üretim kodundaki her
subprocess.run/Popen/check_* çağrısının `creationflags` ya da `**` açılımı (`**cfg.PENCERESIZ`) taşımasını ister.
"""
import ast
import os
import sys
import unittest

AD = os.path.dirname(os.path.abspath(__file__))
KOK = os.path.abspath(os.path.join(AD, ".."))
sys.path.insert(0, os.path.join(KOK, "scripts"))

import cfg  # noqa: E402

CAGRILAR = ("run", "Popen", "check_output", "check_call", "call")
# Bilerek görünür ya da Windows dışı kollar: masaüstü bağlantısı açan çağrılar.
ISTISNA_IZ = ("xdg-open",)


def bayraksiz_cagrilar(kok):
    """(göreli yol, satır) listesi: bayraksız subprocess çağrıları (test dosyaları hariç)."""
    bulunan = []
    for dp, _, dosyalar in os.walk(kok):
        d = dp.replace(os.sep, "/")
        if "/tests" in d or "__pycache__" in d or "/.git" in d:
            continue
        for ad in dosyalar:
            if not ad.endswith(".py") or ad.startswith("test_") and ad != "test_paralel.py":
                continue
            yol = os.path.join(dp, ad)
            with open(yol, encoding="utf-8") as f:
                metin = f.read()
            for n in ast.walk(ast.parse(metin)):
                if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
                        and n.func.value.id == "subprocess" and n.func.attr in CAGRILAR):
                    continue
                kw = {k.arg for k in n.keywords}
                if "creationflags" in kw or None in kw:
                    continue
                if any(i in (ast.get_source_segment(metin, n) or "") for i in ISTISNA_IZ):
                    continue
                bulunan.append((os.path.relpath(yol, kok).replace(os.sep, "/"), n.lineno))
    return sorted(bulunan)


class PencerisizSubprocess(unittest.TestCase):
    def test_uretimde_bayraksiz_cagri_yok(self):
        self.assertEqual(bayraksiz_cagrilar(KOK), [], "subprocess çağrısına `**cfg.PENCERESIZ` ekle")

    def test_denetim_bayraksiz_cagriyi_yakalar(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            with open(os.path.join(t, "x.py"), "w", encoding="utf-8") as f:
                f.write("import subprocess\nsubprocess.run(['git'])\nsubprocess.run(['git'], **cfg.PENCERESIZ)\n")
            self.assertEqual(bayraksiz_cagrilar(t), [("x.py", 2)])

    def test_bayrak_yalniz_windowsta(self):
        if os.name == "nt":
            self.assertEqual(cfg.PENCERESIZ, {"creationflags": 0x08000000})
        else:
            self.assertEqual(cfg.PENCERESIZ, {})

    def test_ork_lib_adi_ayni_nesne(self):
        import ork_lib
        self.assertIs(ork_lib.PENCERESIZ, cfg.PENCERESIZ)


if __name__ == "__main__":
    unittest.main()
