"""Jira öncül sınaması ve `orkestra is dalga --jira` (ADR-0086, I-231 P2); gerçek PE yanıtı fixture'ıyla."""
import json
import os
import shutil
import sys
import unittest

import test_cekirdek as TC

sys.path.insert(0, os.path.join(TC.KOK, "scripts"))
import jira_bagimlilik as JB  # noqa: E402
import paralellik as PR  # noqa: E402
from komutlar import dalga as D  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "jira_ornek_PE.json")


def plan(*maddeler):
    """(n, jira|None, once, yazma) → plan metni; her madde kendi yazma alanında (kesişim yok)."""
    s = ["# Plan", "", "## 4. Plan maddeleri", ""]
    for n, jira, once, yazma in maddeler:
        s += [f"### P{n} Madde {n}", "", "**Ne:** iş", ""]
        if jira:
            s += [f"**Jira:** {jira}", ""]
        s += [f"**Önce:** {once}", "", f"**Yazma alanı:** {yazma}", "", f"**Kabul:** k{n}", ""]
    return "\n".join(s)


def _graf(*bagler):
    """(öncül, bloklanan[, öncül_kapali]) → coz() çıktısı; tek yönden (bloklananda inwardIssue) yazılır."""
    issues = {}
    for b in bagler:
        o, k = b[0], b[1]
        kat = "done" if len(b) > 2 and b[2] else "new"
        issues.setdefault(o, {"key": o, "fields": {"status": {"statusCategory": {"key": kat}}, "issuelinks": []}})
        issues.setdefault(k, {"key": k, "fields": {"status": {"statusCategory": {"key": "new"}}, "issuelinks": []}})
        issues[k]["fields"]["issuelinks"].append({"type": {"name": "Blocks"}, "inwardIssue": {
            "key": o, "fields": {"status": {"statusCategory": {"key": kat}}}}})
    return JB.coz({"okuma_saati": "2026-10-27T10:30:00", "issues": list(issues.values())})


def _fixture():
    with open(FIXTURE, encoding="utf-8") as f:
        return JB.coz(json.load(f))


class JiraEksikleri(unittest.TestCase):
    def test_alan_ayristirilir(self):
        md = PR.maddeler(plan((1, "PE-770", "yok", "a.py"), (2, None, "yok", "b.py")))
        self.assertEqual(md[1]["jira"], "PE-770")
        self.assertEqual(md[2]["jira"], "")

    def test_oncul_kumede_yok_ret_ve_ad(self):
        md = PR.maddeler(plan((1, "PE-770", "yok", "a.py")))
        e = PR.jira_eksikleri(md, _fixture())
        self.assertEqual(len(e), 1)
        self.assertIn("P1 (PE-770)", e[0])
        self.assertIn("PE-783", e[0])
        self.assertIn("plan kümesinde yok", e[0])

    def test_sonradan_eklenen_baglanti_once_yok_ret(self):
        # Plan iki görevi `Önce: yok` ile bağımsız yazmış; JSON'da PE-783 → PE-770 bağı var
        md = PR.maddeler(plan((1, "PE-783", "yok", "a.py"), (2, "PE-770", "yok", "b.py")))
        e = PR.jira_eksikleri(md, _fixture())
        self.assertEqual(len(e), 1)
        self.assertIn("PE-770", e[0])
        self.assertIn("PE-783 (P1)", e[0])
        self.assertIn("**Önce:** içinde anılmıyor", e[0])

    def test_oncul_kumede_ve_once_icinde_gecer(self):
        md = PR.maddeler(plan((1, "PE-783", "yok", "a.py"), (2, "PE-770", "P1 — Çıktı: PE-783 bloklar", "b.py")))
        self.assertEqual(PR.jira_eksikleri(md, _fixture()), [])

    def test_kapali_oncul_kumede_olmasa_da_gecer(self):
        md = PR.maddeler(plan((1, "B", "yok", "a.py")))
        self.assertEqual(PR.jira_eksikleri(md, _graf(("A", "B", True))), [])

    def test_dongu_ret(self):
        g = _graf(("A", "B"), ("B", "A"))
        md = PR.maddeler(plan((1, "A", "yok", "a.py"), (2, "B", "yok", "b.py")))
        e = PR.jira_eksikleri(md, g)
        self.assertTrue(any("döngü" in x and "A" in x and "B" in x for x in e), e)

    def test_dongu_plan_disi_anahtarlar_sayilmaz(self):
        g = _graf(("A", "B"), ("B", "A"))
        md = PR.maddeler(plan((1, "Z", "yok", "a.py")))
        self.assertEqual(PR.jira_eksikleri(md, g), [])

    def test_jira_alani_olmayan_eski_plan_degismez(self):
        md = PR.maddeler(plan((1, None, "yok", "a.py"), (2, None, "P1 — Çıktı: a", "b.py")))
        self.assertEqual(PR.jira_eksikleri(md, _fixture()), [])

    def test_jira_ihlali_paralellik_eksiklerine_sizmaz(self):
        metin = plan((1, "PE-783", "yok", "a.py"), (2, "PE-770", "yok", "b.py"))
        self.assertTrue(PR.jira_eksikleri(PR.maddeler(metin), _fixture()))
        self.assertEqual(PR.analiz(metin)["eksikler"], [])


class JiraSatirlari(unittest.TestCase):
    def test_cok_dalgali_kume_dogru_dalga_ve_once(self):
        # A → B → C ve A → D
        g = _graf(("A", "B"), ("A", "D"), ("B", "C"))
        s = D.jira_satirlari(g, ["A", "B", "C", "D"])
        self.assertEqual(s["dalgalar"], [["A"], ["B", "D"], ["C"]])
        self.assertEqual(s["numara"], {"A": 1, "B": 2, "D": 3, "C": 4})
        md = PR.maddeler("\n\n".join(s["bloklar"]))
        self.assertEqual([m["once_hatalari"] for m in md.values()], [[], [], [], []])
        self.assertEqual(md[1]["once"], [])
        self.assertEqual([d for d, _, _ in md[2]["once"]], [1])
        self.assertEqual([d for d, _, _ in md[4]["once"]], [2])  # C ← B
        self.assertEqual(md[4]["jira"], "C")
        self.assertEqual(s["eksik"], [])

    def test_kapali_oncul_once_yazilmaz(self):
        s = D.jira_satirlari(_graf(("A", "B", True)), ["B"])
        self.assertIn("**Önce:** yok", s["bloklar"][0])

    def test_acik_oncul_kumede_yoksa_eksik(self):
        s = D.jira_satirlari(_fixture(), ["PE-770"])
        self.assertEqual(s["eksik"], [("PE-770", "PE-783")])

    def test_mevcut_numaralar_korunur(self):
        s = D.jira_satirlari(_fixture(), ["PE-783", "PE-770"], {"PE-783": 3})
        self.assertEqual(s["numara"], {"PE-783": 3, "PE-770": 4})
        self.assertIn("**Önce:** P3 — Çıktı: PE-783", s["bloklar"][1])


class JiraKomutu(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown

    def kos(self, *args):
        return TC.kos([TC.CLI] + list(args), self.proje)

    def klasor(self, jira_dosyasi=True, plan_metni=None):
        d = os.path.join(self.proje, "is_klasoru")
        os.makedirs(d, exist_ok=True)
        if jira_dosyasi:
            shutil.copy(FIXTURE, os.path.join(d, JB.DOSYA))
        if plan_metni is not None:
            with open(os.path.join(d, "plan.md"), "w", encoding="utf-8") as f:
                f.write(plan_metni)
        return d

    def test_anahtarlardan_dalga_ve_satirlar(self):
        d = self.klasor()
        r = self.kos("is", "dalga", d, "--jira", "PE-783,PE-770")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Jira dalga 1: PE-783", r.stdout)
        self.assertIn("Jira dalga 2: PE-770", r.stdout)
        md = PR.maddeler(r.stdout)
        self.assertEqual(md[2]["jira"], "PE-770")
        self.assertEqual([(x, t) for x, t, _ in md[2]["once"]], [(1, "Çıktı")])
        self.assertEqual(md[2]["once_hatalari"], [])

    def test_plan_olmadan_da_calisir_planin_jira_alanlari_kullanilir(self):
        d = self.klasor(plan_metni=plan((1, "PE-783", "yok", "a.py"), (2, "PE-770", "P1 — Çıktı: PE-783", "b.py")))
        r = self.kos("is", "dalga", d, "--jira")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("### P2 PE-770", r.stdout)

    def test_acik_oncul_kumede_yok_cikis_1(self):
        r = self.kos("is", "dalga", self.klasor(), "--jira", "PE-770")
        self.assertEqual(r.returncode, 1)
        self.assertIn("PE-770 ← PE-783", r.stderr)
        self.assertIn("**Jira:** PE-770", r.stdout)

    def test_okunmamis_anahtar_hata(self):
        r = self.kos("is", "dalga", self.klasor(), "--jira", "PE-999")
        self.assertEqual(r.returncode, 2)
        self.assertIn("PE-999", r.stderr)
        self.assertIn("bağımsız sayılamaz", r.stderr)

    def test_dosya_yok_hata(self):
        r = self.kos("is", "dalga", self.klasor(jira_dosyasi=False), "--jira", "PE-1")
        self.assertEqual(r.returncode, 2)
        self.assertIn(JB.DOSYA + " yok", r.stderr)

    def test_anahtar_yok_hata(self):
        r = self.kos("is", "dalga", self.klasor(plan_metni=plan((1, None, "yok", "a.py"))), "--jira")
        self.assertEqual(r.returncode, 2)
        self.assertIn("Jira anahtarı yok", r.stderr)

    def test_yardim_jira_secenegini_gosterir(self):
        r = self.kos("is", "dalga", "--yardım")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--jira", r.stdout)


if __name__ == "__main__":
    unittest.main()
