"""on_kontrol.py kontrol: --ajan-id yokken kartın son is-bitti olayının agent_id'si kullanılır (G-046 K4).

`py -3.13 -m pytest plugins/orkestra/tests/test_on_kontrol_ajan.py -q`
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import on_kontrol as OK  # noqa: E402


def olay(ad, agent_id=None):
    o = {"zaman": "2026-10-14T10:00:00+03:00", "olay": ad}
    if agent_id is not None:
        o["agent_id"] = agent_id
    return o


class AjanKimligiTestleri(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = self.tmp.name
        os.makedirs(os.path.join(self.p, ".claude", "orkestra", "gorevler"))
        os.makedirs(os.path.join(self.p, "src"))
        with open(os.path.join(self.p, "src", "x.txt"), "wb") as f:
            f.write(b"a\n")

    def tearDown(self):
        self.tmp.cleanup()

    def kart_yolu(self):
        return os.path.join(self.p, ".claude", "orkestra", "gorevler", "G-1.json")

    def kart(self, gecmis):
        k = {"id": "G-1", "yazma_alani": ["src/*.txt"], "gecmis": gecmis}
        with open(self.kart_yolu(), "w", encoding="utf-8") as f:
            json.dump(k, f)

    def kos(self, *args):
        cikti = io.StringIO()
        with contextlib.redirect_stdout(cikti):
            kod = OK.main(["kontrol", "G-1"] + list(args) + ["--proje", self.p])
        self.assertEqual(kod, 0, cikti.getvalue())

    def son_agent_id(self):
        with open(self.kart_yolu(), encoding="utf-8") as f:
            kayitlar = json.load(f)["onkontrol_kosulari"]
        return kayitlar[-1]["agent_id"]

    def test_son_is_bitti_agent_id_kullanilir(self):
        self.kart([olay("olusturuldu"), olay("isleniyor", "ilk-isleyen"), olay("is-bitti", "isci-abc")])
        self.kos()
        self.assertEqual(self.son_agent_id(), "isci-abc")

    def test_birden_cok_is_bitti_en_sonuncusu(self):
        self.kart([olay("is-bitti", "eski-1"), olay("reddedildi"), olay("isleniyor", "x"),
                   olay("is-bitti", "yeni-2"), olay("denetim-onay", "denetci-9")])
        self.kos()
        self.assertEqual(self.son_agent_id(), "yeni-2")

    def test_isleniyor_agent_id_kullanilmaz(self):
        self.kart([olay("isleniyor", "sadece-isleniyor")])
        self.kos()
        self.assertIsNone(self.son_agent_id())

    def test_is_bitti_yoksa_null(self):
        self.kart([olay("olusturuldu")])
        self.kos()
        self.assertIsNone(self.son_agent_id())

    def test_gecmis_bos_null(self):
        self.kart([])
        self.kos()
        self.assertIsNone(self.son_agent_id())

    def test_ana_agent_id_null(self):
        self.kart([olay("is-bitti", "ana")])
        self.kos()
        self.assertIsNone(self.son_agent_id())

    def test_is_bitti_agent_id_bos_veya_yok_null(self):
        for gecmis in ([olay("is-bitti")], [olay("is-bitti", "")]):
            with self.subTest(gecmis=gecmis):
                self.kart(gecmis)
                self.kos()
                self.assertIsNone(self.son_agent_id())

    def test_verilen_ajan_id_onceliklidir(self):
        self.kart([olay("is-bitti", "isci-abc")])
        self.kos("--ajan-id", "verilen-77")
        self.assertEqual(self.son_agent_id(), "verilen-77")

    def test_verilen_ajan_id_is_bitti_yokken_de_yazilir(self):
        self.kart([olay("olusturuldu")])
        self.kos("--ajan-id", "verilen-77")
        self.assertEqual(self.son_agent_id(), "verilen-77")


if __name__ == "__main__":
    unittest.main()
