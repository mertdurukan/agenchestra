"""ADR-0099: devir hatırlatması (scripts/devir_hatirlatma.py).
`py -3.13 -m pytest -q plugins/orkestra/tests/test_devir_hatirlatma.py`
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import devir_hatirlatma as DH  # noqa: E402
import ork_lib as L  # noqa: E402

OTURUM = "devirtest-oturum-1"


class DevirHatirlatma(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()
        self.sd = os.path.join(self.t, ".claude", "orkestra")
        os.makedirs(self.sd)
        self.ayar({"kontrol_orani": 0})
        L.istek_id_yeni(self.sd, OTURUM)

    def tearDown(self):
        shutil.rmtree(self.t, ignore_errors=True)

    def ayar(self, d):
        with open(os.path.join(self.sd, DH.PROJE_DOSYA), "w", encoding="utf-8") as f:
            json.dump(d, f)

    def yaz(self, ad, arac="Write", agent_id=None):
        return DH.izle(arac, {"file_path": ad}, self.sd, OTURUM, agent_id, self.t)

    def olaylar(self):
        yol = os.path.join(self.sd, "gunluk.jsonl")
        if not os.path.exists(yol):
            return []
        return [o for o in map(json.loads, open(yol, encoding="utf-8")) if o.get("tur") == "devir_olay"]

    def test_ucuncu_ayri_dosyada_bir_kez_hatirlatir(self):
        self.assertEqual(self.yaz("a.py"), "")
        self.assertEqual(self.yaz("b.py"), "")
        self.assertIn("devir", self.yaz("c.py"))
        self.assertEqual(self.yaz("d.py"), "")  # tur başına tek hatırlatma
        self.assertEqual(len(self.olaylar()), 1)

    def test_ayni_dosya_tekrari_sayilmaz(self):
        for _ in range(5):
            self.assertEqual(self.yaz("a.py"), "")
        self.assertEqual(self.olaylar(), [])

    def test_is_belgeleri_muaf(self):
        for ad in ("is/plan.md", "is/todo.md", "is/mevcut_durum_20261030.md", "adr/ADR-0099-x.md", "is/sozlesme_1.md"):
            self.assertEqual(self.yaz(ad), "")
        self.assertEqual(self.olaylar(), [])

    def test_alt_ajan_cagrisi_varsa_hatirlatmaz(self):
        self.yaz("a.py")
        DH.izle("Agent", {}, self.sd, OTURUM, None, self.t)
        self.yaz("b.py")
        self.assertEqual(self.yaz("c.py"), "")
        self.assertEqual(self.olaylar(), [])

    def test_alt_ajanin_kendi_cagrisi_sayilmaz(self):
        for ad in ("a.py", "b.py", "c.py"):
            self.assertEqual(self.yaz(ad, agent_id="x"), "")

    def test_yeni_istekte_sayac_sifirlanir(self):
        self.yaz("a.py"); self.yaz("b.py")
        L.istek_id_yeni(self.sd, OTURUM)
        self.assertEqual(self.yaz("c.py"), "")

    def test_kontrol_grubu_kaydeder_ama_hatirlatmaz(self):
        self.ayar({"kontrol_orani": 1})
        self.yaz("a.py"); self.yaz("b.py")
        self.assertEqual(self.yaz("c.py"), "")
        o = self.olaylar()
        self.assertEqual(len(o), 1)
        self.assertEqual(o[0]["grup"], "kontrol")
        self.assertTrue(o[0]["istek_id"])

    def test_atama_sabit_ve_orana_yakin(self):
        self.assertEqual(DH.kontrol_grubu_mu("s1", 0.5), DH.kontrol_grubu_mu("s1", 0.5))
        n = sum(DH.kontrol_grubu_mu(f"oturum-{i}", 0.5) for i in range(2000))
        self.assertTrue(900 < n < 1100, n)

    def test_kapali_mod_ve_ortam_degiskeni(self):
        self.ayar({"mod": "kapali", "kontrol_orani": 0})
        for ad in ("a.py", "b.py", "c.py"):
            self.assertEqual(self.yaz(ad), "")
        self.assertEqual(self.olaylar(), [])

    def test_hata_araci_bozmaz(self):
        self.assertEqual(DH.izle("Write", None, self.sd, OTURUM, None, self.t), "")


if __name__ == "__main__":
    unittest.main()
