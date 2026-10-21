"""I-139 P7 (bce F37): `orkestra ara` - iş klasörü, ADR ve kural metni araması (TF-IDF, model yok)."""
import json
import os
import sys
import unittest

import test_cekirdek as TC

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import belge_ara as BA  # noqa: E402


def _yaz(yol, metin):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8", newline="\n") as f:
        f.write(metin)


class BelgeAra(unittest.TestCase):
    tearDown = TC.Cekirdek.tearDown

    def setUp(self):
        TC.Cekirdek.setUp(self)
        _yaz(os.path.join(self.proje, "adr", "ADR-0001-kimlik.md"),
             "# ADR-0001: Kimlik klasörü\n\nParola ve anahtar değerleri kullanıcı düzeyindeki kimlik klasöründe tutulur.\n")
        _yaz(os.path.join(self.proje, ".claude", "rules", "push.md"),
             "# Push kuralı\n\nYasak yola dokunan push pre-push kancasında reddedilir.\n")
        self.klasor = os.path.join(self.proje, "is1")
        r = TC.kos([TC.CLI, "is", "ac", "Panel renk işi", "--klasor", self.klasor], self.proje)
        self.assertEqual(r.returncode, 0, r.stderr)
        _yaz(os.path.join(self.klasor, "notlar.md"), "# Panel renkleri\n\nKoyu tema için gri tonları ve vurgu rengi seçildi.\n")

    def ara(self, *args):
        return TC.kos([TC.CLI, "ara", *args], self.proje)

    def test_en_ilgili_belge_birinci(self):
        r = self.ara("kimlik klasörü parola", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        sonuc = json.loads(r.stdout)
        self.assertEqual(sonuc[0]["yol"], "adr/ADR-0001-kimlik.md")
        self.assertEqual(sonuc[0]["tur"], "adr")
        self.assertIn("Kimlik", sonuc[0]["parca"])

    def test_is_klasoru_ve_kural_taranir(self):
        tur = {r["yol"]: r["tur"] for r in json.loads(self.ara("panel renk tema", "--json").stdout)}
        self.assertEqual(tur.get("is1/notlar.md"), "is")
        self.assertEqual({r["tur"] for r in json.loads(self.ara("pre-push kancasında reddedilir", "--json").stdout)[:1]}, {"kural"})

    def test_olmayan_sozcuk_bos(self):
        r = self.ara("zzzxqwv", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), [])
        self.assertIn("eşleşme yok", self.ara("zzzxqwv").stdout)

    def test_n_sinirlar_ve_metin_ciktisi(self):
        iki = self.ara("klasörü renkleri", "--json")
        self.assertEqual(len(json.loads(iki.stdout)), 2)
        r = self.ara("klasörü renkleri", "--n", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.startswith("1. ["), r.stdout)
        self.assertNotIn("\n2. ", r.stdout)

    def test_birim_proje_disi_dizin_bos(self):
        self.assertEqual(BA.ara([], "kimlik"), [])
        self.assertEqual(BA.ara(BA.belgeler(os.path.join(self.proje, "yok_dizin")), "kimlik"), [])


if __name__ == "__main__":
    unittest.main()
