"""Dış kaynaklı skill'ler (ADR-0095): varlık, ad=dizin, özgünlük (sha256), kaynak alanı."""
import hashlib
import json
import os
import re
import unittest

KOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
KAYIT = os.path.join(KOK, "ayarlar", "dis_skill_kaynaklari.json")


def _kayit():
    with open(KAYIT, encoding="utf-8") as f:
        return json.load(f)["skiller"]


class DisSkiller(unittest.TestCase):
    def test_on_bir_skill_kayitli(self):
        self.assertEqual(len(_kayit()), 11)

    def test_her_skill_ozgun_ve_adi_dizinle_ayni(self):
        for k in _kayit():
            yol = os.path.join(KOK, "skills", k["ad"], "SKILL.md")
            self.assertTrue(os.path.isfile(yol), k["ad"])
            with open(yol, "rb") as f:
                b = f.read()
            self.assertEqual(hashlib.sha256(b).hexdigest(), k["sha256"], k["ad"])
            m = re.search(rb"\A---\r?\nname: (\S+)\r?\n", b)
            self.assertIsNotNone(m, k["ad"])
            self.assertEqual(m.group(1).decode(), k["ad"])
            self.assertIn(b"\ndescription:", b)
            self.assertIn(("source: " + k["kaynak"]).encode(), b)

    def test_kaynak_https(self):
        for k in _kayit():
            self.assertTrue(k["kaynak"].startswith("https://github.com/"), k["ad"])


if __name__ == "__main__":
    unittest.main()
