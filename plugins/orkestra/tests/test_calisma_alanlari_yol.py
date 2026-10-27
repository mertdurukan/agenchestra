"""calisma_alanlari() klasör yolunu önbellekten körü körüne almaz; proje klasörünün adıyla doğrular.

Kabul kriterleri:
  K1  Önbellekteki yol proje klasörünün adını üretmiyorsa (yeniden adlandırma, yanlış ilk okuma) kayıt atılır,
      transkriptten yeniden okunur ve önbellek düzeltilir.
  K2  Transkriptte ilk `cwd` başka klasörse, klasör adını üreten `cwd` seçilir.
  K3  Adı üreten yol önbellekteyse transkripte hiç dokunulmaz (maliyet artmaz).
  K4  Klasör adını üreten `cwd` yoksa eski davranış korunur (ilk `cwd`), alan düşmez.
"""
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import ork_lib  # noqa: E402

GERCEK = "C:\\Is\\Gercek\\Alan"
BASKA = "C:\\Is\\Baska\\Klasor"


def kodla(yol: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", yol)


class AlanYolu(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.ev = self._t.name
        self.genel = os.path.join(self.ev, "panel")
        os.makedirs(self.genel)
        self.onb = os.path.join(self.genel, "alanlar.json")
        self._p = [mock.patch.dict(os.environ, {"HOME": self.ev, "USERPROFILE": self.ev}),
                   mock.patch.object(ork_lib, "GENEL_DIZIN", self.genel)]
        for p in self._p:
            p.start()

    def tearDown(self):
        for p in self._p:
            p.stop()
        self._t.cleanup()

    def _proje(self, aid, cwdler):
        d = os.path.join(self.ev, ".claude", "projects", aid)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "s1.jsonl"), "w", encoding="utf-8") as f:
            for c in cwdler:
                f.write(json.dumps({"type": "user", "cwd": c}, separators=(",", ":")) + "\n")  # gerçek transkript gibi sıkı

    def _onbellek(self, veri):
        with open(self.onb, "w", encoding="utf-8") as f:
            json.dump(veri, f)

    def _yol(self):
        (a,) = ork_lib.calisma_alanlari()
        return a["yol"]

    def test_k1_bayat_onbellek_duzelir(self):
        aid = kodla(GERCEK)
        self._proje(aid, [GERCEK])
        self._onbellek({aid: {"yol": BASKA}})
        self.assertEqual(self._yol(), GERCEK)
        with open(self.onb, encoding="utf-8") as f:
            self.assertEqual(json.load(f)[aid]["yol"], GERCEK)

    def test_k2_ilk_cwd_baska_klasor(self):
        aid = kodla(GERCEK)
        self._proje(aid, [BASKA, GERCEK])
        self.assertEqual(self._yol(), GERCEK)

    def test_k3_dogru_onbellege_dokunulmaz(self):
        aid = kodla(GERCEK)
        self._proje(aid, [BASKA])  # transkript okunursa yanlış yol çıkar
        self._onbellek({aid: {"yol": GERCEK}})
        self.assertEqual(self._yol(), GERCEK)

    def test_k4_eslesen_cwd_yoksa_ilk_cwd(self):
        aid = kodla(GERCEK)
        self._proje(aid, [BASKA])
        self.assertEqual(self._yol(), BASKA)


if __name__ == "__main__":
    unittest.main()
