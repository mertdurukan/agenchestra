"""I-139 P1: serbest yol anmaları için varlık denetimi (yol_denetimi.py ve plan_dogrulama entegrasyonu)."""
import os
import shutil
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import plan_dogrulama as PD  # noqa: E402
import yol_denetimi as YD  # noqa: E402

PLAN = """# T: plan

[mevcut_durum_20260101.md](mevcut_durum_20260101.md)

## 2. Mevcut durumdan çıkan sonuçlar (iddialar)

- ⬜ **C1** Dosya var. Dayanak: MD §1.
  - Kanıt: say var/olan.py => 1

## 4. Plan maddeleri

### P1 Madde

**Ne:** `var/olan.py` okunur, `yok/olmayan.py` aranır.

**İddialar:** C1
"""


class YolAdayi(unittest.TestCase):
    def test_yol_olmayanlar_atlanir(self):
        for parca in ["hook.py", "orkestra is devam", "a/*.py", "a/<ad>.md", "https://x.y/z.py", "$HOME/a.py", "--bayrak/x.py",
                      "a/b", "{a,b}/c.py", "tur=istek"]:
            self.assertIsNone(YD.yol_adayi(parca), parca)

    def test_yol_adaylari(self):
        self.assertEqual(YD.yol_adayi("scripts/hook.py"), "scripts/hook.py")
        self.assertEqual(YD.yol_adayi("scripts/hook.py:120"), "scripts/hook.py")
        self.assertEqual(YD.yol_adayi("a/b.py:10-20"), "a/b.py")
        self.assertEqual(YD.yol_adayi("tests/"), "tests/")


class MetinDenetimi(unittest.TestCase):
    def setUp(self):
        self.kok = tempfile.mkdtemp(prefix="ork_yol_")
        os.makedirs(os.path.join(self.kok, "var"))
        open(os.path.join(self.kok, "var", "olan.py"), "w").close()

    def tearDown(self):
        shutil.rmtree(self.kok, ignore_errors=True)

    def test_var_ve_yok(self):
        metin = "Bak `var/olan.py` ve `yok/olmayan.py`.\n"
        s = YD.denetle_metin(metin, [self.kok])
        self.assertEqual([(k["yol"], k["var"]) for k in s], [("var/olan.py", True), ("yok/olmayan.py", False)])
        self.assertEqual(s[0]["satir"], 1)

    def test_atlananlar(self):
        metin = "\n".join([
            "```", "`kod/citi.py`", "```",
            "<!-- `yorum/ici.py` -->",
            "- Kanıt: dosya `kanit/satiri.py:1` \"x\"",
            "Yeni dosya `yeni/dosya.py` yazılır.",
            "Joker `a/*.py` ve URL `https://a.b/c.py`.",
        ])
        self.assertEqual(YD.denetle_metin(metin, [self.kok]), [])

    def test_tekrar_bir_kez_sayilir(self):
        s = YD.denetle_metin("`yok/a.py`\n`yok/a.py`\n", [self.kok])
        self.assertEqual(len(s), 1)

    def test_mutlak_yol(self):
        mutlak = os.path.join(self.kok, "var", "olan.py")
        s = YD.denetle_metin(f"`{mutlak}`\n", [])
        self.assertTrue(s[0]["var"])

    def test_bulunamayanlar_bicimi(self):
        s = YD.denetle_dosyalar([], [self.kok])
        self.assertEqual(s, [])
        self.assertEqual(YD.bulunamayanlar([{"dosya": "plan.md", "satir": 3, "yol": "a/b.py", "var": False},
                                            {"dosya": "plan.md", "satir": 4, "yol": "c/d.py", "var": True}]),
                         ["plan.md:3 `a/b.py`"])


class PlanEntegrasyonu(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_yol_pl_")
        os.makedirs(os.path.join(self.proje, ".claude"))
        os.makedirs(os.path.join(self.proje, "var"))
        open(os.path.join(self.proje, "var", "olan.py"), "w").close()
        self.klasor = os.path.join(self.proje, "is")
        os.makedirs(self.klasor)
        self.plan = os.path.join(self.klasor, "plan.md")
        with open(self.plan, "w", encoding="utf-8", newline="\n") as f:
            f.write(PLAN)
        with open(os.path.join(self.klasor, "mevcut_durum_20260101.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("# MD\n\nBak `md/yok.py`.\n")

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)

    def test_sonuca_yol_alani_eklenir(self):
        s = PD.degerlendir(self.plan, kos=False)
        kayip = YD.bulunamayanlar(s["yol"])
        self.assertEqual(kayip, ["plan.md:14 `yok/olmayan.py`", "mevcut_durum_20260101.md:3 `md/yok.py`"])
        self.assertEqual(s["karar"], PD.KARAR_UYGULANABILIR)  # uyarı karara girmez

    def test_karar_blogunda_bulunamayan_satiri(self):
        s = PD.degerlendir(self.plan, kos=False)
        blok = PD.karar_blogu(s, "x")
        self.assertIn("**Bulunamayan yollar (uyarı):**", blok)
        self.assertIn("yok/olmayan.py", blok)

    def test_eksik_yol_yoksa_satir_yok(self):
        with open(self.plan, "w", encoding="utf-8", newline="\n") as f:
            f.write(PLAN.replace("`yok/olmayan.py`", "`var/olan.py`"))
        os.remove(os.path.join(self.klasor, "mevcut_durum_20260101.md"))
        s = PD.degerlendir(self.plan, kos=False)
        self.assertNotIn("Bulunamayan yollar", PD.karar_blogu(s, "x"))


if __name__ == "__main__":
    unittest.main()
