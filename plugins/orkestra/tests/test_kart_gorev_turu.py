"""ADR-0092: kart basamağı görev türü kataloğundan türer; katalog dışı sınıf, yüksek basamak ve gerekçesiz T3 golge uyarır."""
import json
import os
import sys
import unittest

import test_cekirdek as TC

sys.path.insert(0, os.path.join(TC.KOK, "scripts"))
import gorev_turleri as GT  # noqa: E402


class KartGorevTuru(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown

    def yeni(self, sinif, *ek):
        return TC.kos([TC.CLI, "kart", "yeni", "--baslik", "X", "--sinif", sinif, "--kabul", "k",
                       "--soru", "Bu ne?", *ek], self.proje)

    def kart(self, gid):
        with open(os.path.join(self.sd, "gorevler", f"{gid}.json"), encoding="utf-8") as f:
            return json.load(f)

    def golge(self):
        yol = os.path.join(self.sd, "gunluk.jsonl")
        if not os.path.exists(yol):
            return []
        with open(yol, encoding="utf-8") as f:
            return [j for j in (json.loads(s) for s in f if s.strip()) if j.get("kapi") == "gorev_turleri"]

    def test_basamaksiz_belge_katalogdan(self):
        r = self.yeni("belge")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.kart(r.stdout.strip())["basamak"], GT.varsayilan_basamak("belge") or "T2")
        self.assertEqual(self.golge(), [])

    def test_katalog_disi_sinif_golge(self):
        r = self.yeni("uydurma")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.kart(r.stdout.strip())["basamak"], "T2")
        self.assertIn("kataloğunda yok", self.golge()[0]["neden"])

    def test_yuksek_basamak_golge(self):
        r = self.yeni("belge", "--basamak", "T4", "--basamak-neden", "K1 belirsiz plan")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.kart(r.stdout.strip())["basamak_neden"], "K1 belirsiz plan")
        self.assertIn("varsayılanından", self.golge()[0]["neden"])

    def test_gerekcesiz_t3_golge(self):
        r = self.yeni("belge", "--basamak", "T3")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(any("basamak_neden yok" in g["neden"] for g in self.golge()))

    def test_kapi_env_kapali(self):
        os.environ["ORKESTRA_GOREV_TURU_KAPISI"] = "0"
        try:
            r = self.yeni("uydurma", "--basamak", "T3")
        finally:
            del os.environ["ORKESTRA_GOREV_TURU_KAPISI"]
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.golge(), [])


if __name__ == "__main__":
    unittest.main()
