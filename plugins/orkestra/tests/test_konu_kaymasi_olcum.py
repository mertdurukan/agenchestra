"""I-297 P7: kayma sınıflayıcısının etiketli örnek setinde ölçümü (n=240: 160 aynı konu, 80 farklı konu).
Eşikler ADR-0114: yanlış pozitif (aynı konuya kayma deme) gözlenen <=%5, Wilson %95 üst <=%10;
kaçırma (farklı konuyu yakalamama) gözlenen <=%10, Wilson %95 üst <=%20. Etiketleyici uyumu (Cohen kappa) ayrı dosyada.
Kaynak: tests/veri/konu_kaymasi_ornek.jsonl (iş başlıklarından türetilmiş; kaynağı ve sınırı mevcut durum §5).
`py -3.13 -m pytest plugins/orkestra/tests/test_konu_kaymasi_olcum.py -s`
"""
import json
import math
import os
import sys
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import is_yonlendirme as IY  # noqa: E402

VERI = os.path.join(KOK, "tests", "veri", "konu_kaymasi_ornek.jsonl")


def wilson_ust(k, n, z=1.96):
    if n == 0:
        return 1.0
    p = k / n
    d = 1 + z * z / n
    m = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (m + h) / d


def kappa(a, b):
    n = len(a)
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    etk = set(a) | set(b)
    pe = sum((a.count(e) / n) * (b.count(e) / n) for e in etk)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def yukle():
    with open(VERI, encoding="utf-8") as f:
        return [json.loads(s) for s in f if s.strip()]


class OlcumTest(unittest.TestCase):
    def test_esikler(self):
        v = yukle()
        ayni = [x for x in v if x["etiket"] == "ayni"]
        farkli = [x for x in v if x["etiket"] == "farkli"]
        self.assertGreaterEqual(len(v), 240)
        self.assertEqual((len(ayni), len(farkli)), (160, 80))
        yp = sum(1 for x in ayni if IY.kayma_mi(x["mesaj"], x["is"]))
        kacir = sum(1 for x in farkli if not IY.kayma_mi(x["mesaj"], x["is"]))
        yp_g, yp_u = yp / len(ayni), wilson_ust(yp, len(ayni))
        k_g, k_u = kacir / len(farkli), wilson_ust(kacir, len(farkli))
        print("\nn=%d yanlış pozitif %d/%d=%.3f (Wilson üst %.3f); kaçırma %d/%d=%.3f (Wilson üst %.3f)"
              % (len(v), yp, len(ayni), yp_g, yp_u, kacir, len(farkli), k_g, k_u))
        self.assertLessEqual(yp_g, 0.05)
        self.assertLessEqual(yp_u, 0.10)
        self.assertLessEqual(k_g, 0.10)
        self.assertLessEqual(k_u, 0.20)

    def test_etiketleyici_uyumu(self):
        """60 örnek ayrı bir denetçi alt ajanca kör yeniden etiketlendi (iş başlığı + mesaj; etiketi görmeden)."""
        v = {str(x["n"]): "A" if x["etiket"] == "ayni" else "F" for x in yukle()}
        with open(os.path.join(KOK, "tests", "veri", "kayma_etiket_denetci_60.json"), encoding="utf-8") as f:
            d = json.load(f)
        k = sorted(d, key=int)
        self.assertEqual(len(k), 60)
        kp = kappa([v[i] for i in k], [d[i] for i in k])
        print("
kappa %.3f (n=60)" % kp)
        self.assertGreaterEqual(kp, 0.7)

    def test_wilson_dogru(self):
        self.assertAlmostEqual(wilson_ust(0, 60), 0.0597, places=3)
        self.assertAlmostEqual(wilson_ust(8, 160), 0.0958, places=3)

    def test_kappa(self):
        self.assertAlmostEqual(kappa(list("aabb"), list("aabb")), 1.0)
        self.assertLess(kappa(list("aabb"), list("abab")), 0.1)


if __name__ == "__main__":
    unittest.main()
