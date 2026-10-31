"""Proje bilgi grafiği şeması (ADR-0112, I-296): kenar ve konu kartı doğrulayıcısı; ihlal vakası kırmızı, doğru örnek yeşil."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import harita_sema as S  # noqa: E402

KENAR = {"kaynak": "scripts/panel.py", "iliski": "import", "hedef": "scripts/araclar_skill.py", "koken": "statik",
         "guven": "yuksek", "kanit": "scripts/panel.py:937", "hash": "ab12cd34", "dogrulama_zamani": "2026-10-31T18:00:00"}
KART = "# Skill\n## Amaç\nSkill ekleme.\n## Eşanlamlılar\nyetenek\n## Yüzeyler\naç/kapa listesi\n## Değişmezler\nSKILL.md zorunlu\n"


class KenarSema(unittest.TestCase):
    def test_gecerli_kenar(self):
        self.assertEqual(S.kenar_hatalari(KENAR), [])

    def test_zorunlu_alan_bos_reddedilir(self):
        for alan in S.ayar()["kenar_zorunlu"]:
            k = dict(KENAR, **{alan: ""})
            self.assertTrue(any(alan in x for x in S.kenar_hatalari(k)), alan)

    def test_bilinmeyen_iliski_koken_guven(self):
        for alan in ("iliski", "koken", "guven"):
            self.assertTrue(S.kenar_hatalari(dict(KENAR, **{alan: "yok_boyle"})), alan)

    def test_statik_kanit_satirsiz_reddedilir(self):
        self.assertTrue(S.kenar_hatalari(dict(KENAR, kanit="scripts/panel.py")))

    def test_llm_kenari_yuksek_guvenle_reddedilir(self):
        k = dict(KENAR, koken="llm", guven="yuksek", kanit="sezgi")
        self.assertTrue(any("llm" in x for x in S.kenar_hatalari(k)))

    def test_llm_kenari_dusuk_guvenle_gecer(self):
        self.assertEqual(S.kenar_hatalari(dict(KENAR, koken="llm", guven="dusuk", kanit="sezgi")), [])

    def test_jsonl_okuma_hatali_satiri_bildirir(self):
        with tempfile.TemporaryDirectory() as d:
            yol = os.path.join(d, "kenarlar.jsonl")
            with open(yol, "w", encoding="utf-8") as f:
                f.write(json.dumps(KENAR) + "\n" + json.dumps(dict(KENAR, hash="")) + "\nbozuk\n")
            gecerli, hatalar = S.kenarlari_oku(yol)
        self.assertEqual(len(gecerli), 1)
        self.assertEqual(len(hatalar), 2)
        self.assertTrue(hatalar[0].startswith("satır 2") and hatalar[1].startswith("satır 3"))


class KartSema(unittest.TestCase):
    def test_gecerli_kart(self):
        self.assertEqual(S.kart_hatalari(KART), [])

    def test_eksik_bolum_reddedilir(self):
        self.assertEqual(S.kart_hatalari(KART.replace("## Değişmezler\nSKILL.md zorunlu\n", "")), ["bölüm yok: Değişmezler"])

    def test_bos_bolum_reddedilir(self):
        self.assertEqual(S.kart_hatalari(KART.replace("yetenek\n", "")), ["bölüm boş: Eşanlamlılar"])


if __name__ == "__main__":
    unittest.main()
