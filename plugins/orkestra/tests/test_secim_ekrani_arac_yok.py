"""I-455 / ADR-0180: kutu aracı (wrap_up) oturumda yoksa seçim hatırlatması, tur başı yönergesi ve devir yönergesi
`wrap_up` anmaz ve AskUserQuestion ile sunar; araç varsa ya da bilinmiyorsa metinler değişmez."""
import json
import os
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import devir_esigi as DE  # noqa: E402
import secim_ekrani_hatirlatma as SH  # noqa: E402

WRAP = "mcp__ccd_turn__wrap_up"


def _transkript(klasor, liste):
    """liste None: liste kaydı yok (bilinmiyor); aksi halde yüklü araç adları."""
    yol = os.path.join(klasor, "t.jsonl")
    satirlar = [{"type": "user", "message": {"content": "merhaba"}}]
    if liste is not None:
        satirlar.insert(0, {"type": "api-request-shape", "shape": {"tools": [{"name": a} for a in liste]}})
    with open(yol, "w", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(s) for s in satirlar))
    return yol


class SecimMetni(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.yok = _transkript(self.d, ["Read", "AskUserQuestion"])
        os.makedirs(os.path.join(self.d, "b"))
        self.var = _transkript(os.path.join(self.d, "b"), ["Read", WRAP])
        os.makedirs(os.path.join(self.d, "c"))
        self.bilinmiyor = _transkript(os.path.join(self.d, "c"), None)

    def test_hatirlatma_arac_yokken_wrap_up_anmaz(self):  # S3
        m = SH.hatirlatma_metni(None, self.yok)
        self.assertNotIn("wrap_up", m)
        self.assertIn("AskUserQuestion", m)

    def test_hatirlatma_arac_varken_ya_da_bilinmiyorken_degismez(self):  # S3
        eski = SH.hatirlatma_metni(None)
        self.assertIn("wrap_up", eski)
        self.assertEqual(SH.hatirlatma_metni(None, self.var), eski)
        self.assertEqual(SH.hatirlatma_metni(None, self.bilinmiyor), eski)
        self.assertEqual(SH.hatirlatma_metni(None, os.path.join(self.d, "yok.jsonl")), eski)

    def test_tur_basi_arac_yokken_wrap_up_anmaz_ve_sinir_icinde(self):  # S3
        m = SH.tur_basi_metni(None, self.yok)
        self.assertTrue(m)
        self.assertNotIn("wrap_up", m)
        self.assertIn("AskUserQuestion", m)
        self.assertLessEqual(len(m), SH.TUR_BASI_SINIR)

    def test_tur_basi_arac_varken_ya_da_bilinmiyorken_degismez(self):  # S3
        eski = SH.tur_basi_metni(None)
        self.assertIn("wrap_up", eski)
        self.assertEqual(SH.tur_basi_metni(None, self.var), eski)
        self.assertEqual(SH.tur_basi_metni(None, self.bilinmiyor), eski)

    def test_devir_yonergesi(self):  # S3
        yok = DE.yonerge(self.yok)
        self.assertNotIn("wrap_up", yok)
        self.assertIn("AskUserQuestion", yok)
        self.assertIn(DE.DUGME_DEVIR, yok)
        self.assertEqual(DE.yonerge(self.var), DE.YONERGE)
        self.assertEqual(DE.yonerge(self.bilinmiyor), DE.YONERGE)
        self.assertEqual(DE.yonerge(), DE.YONERGE)

    def test_arac_adi_ayardan_gelir(self):
        sd = os.path.join(self.d, "sd")
        os.makedirs(sd)
        with open(os.path.join(sd, "devir_esigi.json"), "w", encoding="utf-8") as f:
            json.dump({"arac": "kapat"}, f)
        self.assertEqual(DE.yonerge(self.var, sd), DE.YONERGE_ARAC_YOK)  # "kapat" aranır, yok


if __name__ == "__main__":
    unittest.main()
