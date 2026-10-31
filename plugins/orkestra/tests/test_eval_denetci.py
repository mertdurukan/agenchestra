"""I-292 P5: denetci ölçüm setinin yapısı (30+30, 5 kusur türü x6), deterministik ve etiketsiz istem; istatistik."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import eval_denetci as E  # noqa: E402


class Set(unittest.TestCase):
    def test_yapi(self):
        v = E.vakalar()
        self.assertEqual(len(v), 60)
        self.assertEqual(sum(1 for x in v if x["etiket"] == "bozuk"), 30)
        for k in E.KUSURLAR:
            self.assertEqual(sum(1 for x in v if x["kusur"] == k), 6, k)

    def test_deterministik(self):
        self.assertEqual([x["prompt"] for x in E.vakalar()], [x["prompt"] for x in E.vakalar()])

    def test_istem_etiket_sizdirmaz(self):
        for x in E.vakalar():
            for yasak in ("bozuk", "dogru", "kusur", "etiket"):
                self.assertNotIn(yasak, x["prompt"].lower().replace("kabul kriterleri", ""), x["id"])

    def test_bozuk_vakada_gercek_kusur_var(self):
        for x in E.vakalar():
            if x["kusur"] == "sayi-tutarsiz":
                satir = [l for l in x["prompt"].splitlines() if l.startswith("| ") and "|---" not in l]
                adetler = [int(l.split("|")[2]) for l in satir[1:-1]]
                self.assertNotEqual(sum(adetler), int(satir[-1].split("|")[2]), x["id"])
            if x["etiket"] == "dogru":
                satir = [l for l in x["prompt"].splitlines() if l.startswith("| ") and "|---" not in l]
                adetler = [int(l.split("|")[2]) for l in satir[1:-1]]
                self.assertEqual(sum(adetler), int(satir[-1].split("|")[2]), x["id"])


class Istatistik(unittest.TestCase):
    def test_cp_sifir_hata_n30(self):
        self.assertAlmostEqual(E.cp_ust(0, 30), 0.0950, places=3)

    def test_puanla(self):
        gercek = E.vakalar()
        satir = []
        for x in gercek:
            satir.append(f"{x['id']}|{'ret' if x['etiket']=='bozuk' else 'onay'}|{x['kusur']}")
        r = E.puanla(satir)
        self.assertEqual((r["kacirma"], r["yanlis_ret"], r["neden_dogru"]), (0, 0, 30))
        satir[0] = f"{gercek[0]['id']}|{'onay' if gercek[0]['etiket']=='bozuk' else 'ret'}|-"
        r2 = E.puanla(satir)
        self.assertEqual(r2["kacirma"] + r2["yanlis_ret"], 1)


if __name__ == "__main__":
    unittest.main()
