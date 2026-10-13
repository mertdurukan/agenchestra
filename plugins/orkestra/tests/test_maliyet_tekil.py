"""ork_lib.maliyet_kayitlari: birikimli hook satirlari agent basina tekillestirilir (cift sayim yok)."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import ork_lib  # noqa: E402


def satir(agent_id, zaman, usd, kaynak=None, oturum="o1"):
    r = {"zaman": zaman, "oturum": oturum, "ajan": "x", "agent_id": agent_id, "maliyet_usd": usd}
    if kaynak:
        r["kaynak"] = kaynak
    return r


class MaliyetTekil(unittest.TestCase):
    def kayitlar(self, rows):
        with tempfile.TemporaryDirectory() as sd:
            with open(os.path.join(sd, "maliyet.jsonl"), "w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r) + "\n")
            return ork_lib.maliyet_kayitlari(sd)

    def test_birikimli_hook_tek_satira_iner(self):
        out = self.kayitlar([satir("a1", "2026-01-01T10:00", 0.33, "hook"),
                             satir("a1", "2026-01-01T10:05", 0.51),
                             satir("a1", "2026-01-01T10:03", 0.43, "hook")])
        self.assertEqual([r["maliyet_usd"] for r in out], [0.51])

    def test_esit_zamanda_buyuk_maliyet(self):
        out = self.kayitlar([satir("a1", "Z", 0.2), satir("a1", "Z", 0.4), satir("a1", "Z", 0.3)])
        self.assertEqual([r["maliyet_usd"] for r in out], [0.4])

    def test_tur_delta_toplami_korunur(self):
        out = self.kayitlar([satir("a1", "1", 0.35, "tur"), satir("a1", "2", 0.096, "tur")])
        self.assertAlmostEqual(sum(r["maliyet_usd"] for r in out), 0.446)

    def test_karisik_grup_tur_tercih_edilir(self):
        out = self.kayitlar([satir("a1", "1", 0.35, "tur"), satir("a1", "2", 0.9, "hook"),
                             satir("a1", "3", 1.0), satir("a1", "4", 0.096, "tur")])
        self.assertEqual({r.get("kaynak") for r in out}, {"tur"})
        self.assertEqual(len(out), 2)

    def test_gruplar_birbirini_etkilemez(self):
        out = self.kayitlar([satir("a1", "1", 0.1), satir("a1", "2", 0.2),
                             satir("a2", "1", 0.5), satir("a1", "1", 0.7, oturum="o2")])
        self.assertEqual(sorted(r["maliyet_usd"] for r in out), [0.2, 0.5, 0.7])

    def test_ana_ajan_satirlari_oldugu_gibi(self):
        out = self.kayitlar([satir(None, "1", 1.0, "hook"), satir(None, "2", 2.0, "hook"), satir(None, "3", 3.0)])
        self.assertEqual(len(out), 3)

    def test_ana_ajan_tur_varsa_diger_satirlar_atilir(self):
        out = self.kayitlar([satir(None, "1", 1.0, "tur"), satir(None, "2", 2.0, "hook")])
        self.assertEqual([r["maliyet_usd"] for r in out], [1.0])

    def test_sira_korunur(self):
        out = self.kayitlar([satir("a1", "1", 0.1), satir(None, "2", 1.0), satir("a1", "3", 0.3)])
        self.assertEqual([r["maliyet_usd"] for r in out], [1.0, 0.3])


if __name__ == "__main__":
    unittest.main()
