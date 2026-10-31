"""I-292 P6: P-030 kural metni ayar modu ile çelişmez (gölge/ihlal tek gerçek: ayarlar/best_in_class.json)."""
import json
import os
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _oku(*y):
    with open(os.path.join(KOK, *y), encoding="utf-8") as f:
        return f.read()


class P030Mod(unittest.TestCase):
    def test_metin_ayar_modunu_soyler(self):
        mod = json.loads(_oku("ayarlar", "best_in_class.json"))["mod"]
        kural = next(k for k in json.loads(_oku("kurallar", "eklenti_kurallari.json"))["kurallar"] if k["id"] == "P-030")
        zit = "gölge" if mod == "ihlal" else "ihlal"
        for ad, metin in (("eklenti_kurallari.json", kural["metin"]), ("KURALLAR.md", _oku("KURALLAR.md"))):
            self.assertNotIn(f"Kapı 'best_in_class' {zit} modundadır", metin, ad)
            self.assertIn(f"Kapı 'best_in_class' {mod} modundadır", metin, ad)


if __name__ == "__main__":
    unittest.main()
