"""Maliyet raporunda baglam çözümü, kırılım ve --baglam süzmesi."""
import argparse
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import analitik  # noqa: E402
import orkestra  # noqa: E402


def satir(usd, oturum="o1", agent_id=None, baglam=None):
    r = {"zaman": "2026-10-13T10:00:00+03:00", "oturum": oturum, "gorev": "-", "surec": "is", "ajan": "x",
         "model": "m", "maliyet_usd": usd}
    if agent_id:
        r["agent_id"] = agent_id
    if baglam is not None:
        r["baglam"] = baglam
    return r


class BaglamRapor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sd = self.tmp.name
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        self.addCleanup(self.tmp.cleanup)

    def yaz(self, ad, veri):
        with open(os.path.join(self.sd, "oturumlar", ad + ".json"), "w", encoding="utf-8") as f:
            json.dump(veri, f)

    def test_cozum_sirasi(self):
        self.yaz("ajan_a1", {"baglam": "RNV/ajan"})
        self.yaz("o1", {"baglam": "RNV/oturum"})
        rows = [satir(1, agent_id="a1", baglam="RNV/satir"),  # satır kazanır
                satir(1, agent_id="a1"),                       # ajan önbelleği
                satir(1, agent_id="zz"),                       # oturum dosyası
                satir(1, oturum="yok")]                        # belirsiz
        c = [r["baglam"] for r in analitik.baglam_coz(self.sd, rows)]
        self.assertEqual(c, ["RNV/satir", "RNV/ajan", "RNV/oturum", "(belirsiz)"])

    def test_kirilim_toplami_genel_toplama_esit(self):
        self.yaz("o1", {"baglam": "RNV/05/002"})
        rows = analitik.baglam_coz(self.sd, [satir(1.5), satir(2.0, baglam="RNV"), satir(0.5, oturum="yok"),
                                              satir(1.0, baglam="Proje/x")])
        k = analitik.baglam_kirilim(rows)
        self.assertAlmostEqual(k["toplam_usd"], 5.0)
        self.assertAlmostEqual(sum(p["usd"] for p in k["projeler"]), 5.0)
        rnv = next(p for p in k["projeler"] if p["proje"] == "RNV")
        self.assertAlmostEqual(rnv["usd"], 3.5)
        self.assertEqual({b["baglam"] for b in rnv["baglamlar"]}, {"RNV", "RNV/05/002"})

    def test_onek_suzmesi(self):
        rows = analitik.baglam_coz(self.sd, [satir(1, baglam="RNV/a/1"), satir(2, baglam="RNV/b/1"),
                                              satir(4, baglam="Proje/x"), satir(8)])
        s = analitik.baglam_filtre(rows, "RNV/a")
        self.assertEqual([r["baglam"] for r in s], ["RNV/a/1"])
        self.assertEqual(len(analitik.baglam_filtre(rows, "RNV")), 2)
        self.assertEqual(len(analitik.baglam_filtre(rows, None)), 4)

    def rapor(self, baglam=None):
        a = argparse.Namespace(gun=0, md=False, csv=False, cikti=None, baglam=baglam)
        orkestra.sd_gerekli = lambda: self.sd
        orkestra.L.sohbetler = lambda *x, **k: []
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            orkestra.cmd_maliyet_rapor(a)
        return buf.getvalue()

    def test_rapor_metni_ve_eski_defter(self):
        rows = [satir(1.0, baglam="RNV/a/1"), satir(2.0)]  # ikincisi baglamsız (eski)
        with open(os.path.join(self.sd, "maliyet.jsonl"), "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        m = self.rapor()
        self.assertIn("### Bağlam", m)
        self.assertIn("**RNV**", m)
        self.assertIn("RNV/a/1", m)
        self.assertIn("(belirsiz)", m)
        self.assertIn("| **Toplam** | 3.000 |", m)
        self.assertIn("≈$3.00", m)
        for bolum in ("Görev × süreç", "Ajan × model", "### Süreç", "### Gün"):
            self.assertIn(bolum, m)
        m2 = self.rapor("RNV")
        self.assertIn("≈$1.00", m2)
        self.assertNotIn("(belirsiz)", m2)


if __name__ == "__main__":
    unittest.main()
