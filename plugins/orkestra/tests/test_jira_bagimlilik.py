"""Jira bağımlılık çözümleyici (ADR-0086, I-231 P1): gerçek PE yanıtı fixture'ı ve K4 durumları."""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import jira_bagimlilik as JB  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "jira_ornek_PE.json")


def _yanit(*gorevler, okuma="2026-10-27T10:30:00"):
    """gorevler: (anahtar, kategori, [(tür, yön, komşu, komşu kategori)]) → ham yanıt."""
    issues = []
    for anahtar, kat, baglar in gorevler:
        issues.append({"key": anahtar, "fields": {"status": {"statusCategory": {"key": kat}}, "issuelinks": [
            {"type": {"name": tur}, yon: {"key": komsu, "fields": {"status": {"statusCategory": {"key": kk}}}}}
            for tur, yon, komsu, kk in baglar]}})
    return {"okuma_saati": okuma, "issues": issues}


def _fixture():
    with open(FIXTURE, encoding="utf-8") as f:
        return JB.coz(json.load(f))


class GercekPEVerisi(unittest.TestCase):
    def test_dort_cift_dogru_oncul_kumesi(self):
        g = _fixture()
        self.assertEqual(g["oncul"], {"PE-780": {"PE-452"}, "PE-770": {"PE-783"}, "PE-772": {"PE-782"}, "PE-171": {"PE-490"}})

    def test_yon_PE770_PE783e_bagli(self):
        g = _fixture()
        self.assertEqual(JB.oncul_kumesi(g, "PE-770"), {"PE-783"})
        self.assertEqual(JB.oncul_kumesi(g, "PE-783"), set())

    def test_relates_yok_sayilir(self):
        g = _fixture()  # PE-770 → PE-200 Relates (Done): öncül sayılmaz, kapalı kümeye de girmez
        self.assertNotIn("PE-200", JB.oncul_kumesi(g, "PE-770"))
        self.assertNotIn("PE-200", g["kapali"])

    def test_bagintisiz_gorev_okundu_sayilir(self):
        g = _fixture()  # PE-720 issuelinks: []
        self.assertTrue(JB.okundu_mu(g, "PE-720"))
        self.assertEqual(JB.oncul_kumesi(g, "PE-720"), set())

    def test_dosyada_olmayan_gorev_okunmamis(self):
        self.assertFalse(JB.okundu_mu(_fixture(), "PE-999"))

    def test_acik_onculler_hepsi_acik(self):
        g = _fixture()
        self.assertEqual(JB.acik_onculler(g, "PE-171"), {"PE-490"})


class BaglantiCozumu(unittest.TestCase):
    def test_tek_uctaki_gorev_verilince_bag_bulunur(self):
        # yalnız PE-770 okundu (inward PE-783); PE-783'ün kendi kaydı yok
        g = JB.coz(_yanit(("PE-770", "new", [("Blocks", "inwardIssue", "PE-783", "new")])))
        self.assertEqual(JB.oncul_kumesi(g, "PE-770"), {"PE-783"})
        self.assertFalse(JB.okundu_mu(g, "PE-783"))

    def test_iki_uc_tekilleser(self):
        g = JB.coz(_yanit(("A", "new", [("Blocks", "outwardIssue", "B", "new")]),
                          ("B", "new", [("Blocks", "inwardIssue", "A", "new")])))
        self.assertEqual(g["oncul"], {"B": {"A"}})

    def test_kapali_oncul_acik_sayilmaz(self):
        g = JB.coz(_yanit(("B", "new", [("Blocks", "inwardIssue", "A", "done")])))
        self.assertEqual(JB.oncul_kumesi(g, "B"), {"A"})
        self.assertEqual(JB.acik_onculler(g, "B"), set())
        self.assertIn("A", g["kapali"])

    def test_donguanahtarlariyla_bildirilir(self):
        g = JB.coz(_yanit(("A", "new", [("Blocks", "inwardIssue", "B", "new")]),
                          ("B", "new", [("Blocks", "inwardIssue", "A", "new")])))
        d = JB.dongu(g)
        self.assertTrue(d and d[0] == d[-1])
        self.assertEqual(set(d), {"A", "B"})

    def test_kapali_dugumde_dongu_sayilmaz(self):
        g = JB.coz(_yanit(("A", "done", [("Blocks", "inwardIssue", "B", "new")]),
                          ("B", "new", [("Blocks", "inwardIssue", "A", "done")])))
        self.assertEqual(JB.dongu(g), [])

    def test_cok_dalgali_kume(self):
        # A → B → C ve A → D (A, B'yi ve D'yi bloklar; B, C'yi bloklar)
        g = JB.coz(_yanit(("B", "new", [("Blocks", "inwardIssue", "A", "new")]),
                          ("D", "new", [("Blocks", "inwardIssue", "A", "new")]),
                          ("C", "new", [("Blocks", "inwardIssue", "B", "new")]), ("A", "new", [])))
        self.assertEqual(JB.dalgalar(g, ["A", "B", "C", "D"]), [["A"], ["B", "D"], ["C"]])

    def test_kume_disi_oncul_dalgayi_etkilemez(self):
        g = JB.coz(_yanit(("B", "new", [("Blocks", "inwardIssue", "A", "new")])))
        self.assertEqual(JB.dalgalar(g, ["B"]), [["B"]])

    def test_dongude_dalgalar_bos(self):
        g = JB.coz(_yanit(("A", "new", [("Blocks", "inwardIssue", "B", "new")]),
                          ("B", "new", [("Blocks", "inwardIssue", "A", "new")])))
        self.assertEqual(JB.dalgalar(g, ["A", "B"]), [])

    def test_issues_yoksa_hata(self):
        with self.assertRaises(ValueError):
            JB.coz({"okuma_saati": "x"})


class DosyaDurumlari(unittest.TestCase):
    def test_dosya_yok_none(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(JB.yukle(d))

    def test_dosya_okunur(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, JB.DOSYA), "w", encoding="utf-8") as f, open(FIXTURE, encoding="utf-8") as src:
                f.write(src.read())
            self.assertEqual(JB.oncul_kumesi(JB.yukle(d), "PE-770"), {"PE-783"})

    def test_bozuk_dosya_hata(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, JB.DOSYA), "w", encoding="utf-8") as f:
                f.write("{bozuk")
            with self.assertRaises(ValueError):
                JB.yukle(d)

    def test_eski_okuma_saati(self):
        g = _fixture()  # 27.10.2026 10:30
        self.assertFalse(JB.eski_mi(g, datetime(2026, 10, 28, 10, 0)))   # 23,5 saat
        self.assertTrue(JB.eski_mi(g, datetime(2026, 10, 28, 11, 0)))    # 24,5 saat

    def test_okuma_saati_yoksa_eski(self):
        self.assertTrue(JB.eski_mi({"okuma_saati": None}, datetime(2026, 10, 27)))
        self.assertTrue(JB.eski_mi({"okuma_saati": "bozuk"}, datetime(2026, 10, 27)))


if __name__ == "__main__":
    unittest.main()
