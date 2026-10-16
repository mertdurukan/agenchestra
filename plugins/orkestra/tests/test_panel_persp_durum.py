"""Panel Onaylar sayfası perspektif şeridi: /onaylar.json arka_plan (yalnız süren görevler) ve todo (yapıldı/kaldı) alanları."""
import os
import sys
import tempfile
import unittest
from unittest import mock

AD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AD, "..", "scripts"))
import ork_lib as L  # noqa: E402
import is_kaydi as IK  # noqa: E402
import niyet  # noqa: E402
import onay  # noqa: E402
import panel  # noqa: E402
import perspektif  # noqa: E402


class PerspektifSeridi(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.proje = os.path.join(self.t.name, "proje")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(self.sd)
        self.alan = {"id": "alan-x", "ad": "proje", "yol": self.proje, "orkestra": True, "sohbet": 1, "son": "x"}
        self.yama = mock.patch.object(L, "calisma_alanlari", lambda: [self.alan])
        self.yama.start()

    def tearDown(self):
        self.yama.stop()
        self.t.cleanup()

    def todo_yaz(self, ad, metin):
        i = IK.is_ac(self.sd, ad, os.path.join(self.t.name, ad.replace(" ", "_")))
        with open(os.path.join(i["klasor"], "todo.md"), "w", encoding="utf-8") as f:
            f.write(metin)
        return i

    def test_todo_sayaci_yapildi_ve_kaldi(self):
        self.todo_yaz("Birinci iş", "- [x] a\n- [x] b\n- [ ] c\n")
        self.todo_yaz("İkinci iş", "- [ ] d\n")
        self.todo_yaz("Todosuz iş", "")
        v = panel._onaylar_json("alan-x")["todo"]
        self.assertEqual((v["biten"], v["kalan"], v["toplam"]), (2, 2, 4))
        self.assertEqual(len(v["isler"]), 2)  # todo'su olmayan iş listelenmez

    def test_arka_plan_bos_iken_liste_bos(self):
        self.assertEqual(panel._onaylar_json("alan-x")["arka_plan"], [])
        self.assertEqual(panel._onaylar_json("alan-x")["todo"]["toplam"], 0)

    def test_perspektif_ve_uygulama_suruyorsa_listelenir(self):
        with mock.patch.object(perspektif, "durum", return_value={"calisiyor": "2026-10-16T21:00:00+03:00"}), \
                mock.patch.object(onay, "uygulama_durumu", return_value={"baslangic": "2026-10-16T21:05:00+03:00"}):
            bp = panel._onaylar_json("alan-x")["arka_plan"]
        self.assertEqual([x["tur"] for x in bp], ["perspektif", "uygulama"])

    def test_arka_plan_isi_suren_sohbet_listelenir(self):
        satir = {"arka_plan": True, "bekleyen": "claude", "ne": "Uzun tarama", "kisa": "abc"}
        diger = {"arka_plan": True, "bekleyen": "beklemede", "ne": "Ölü iş", "kisa": "def"}
        with mock.patch.object(niyet, "gorunum", return_value={"oturumlar": [satir, diger]}):
            bp = panel._onaylar_json("alan-x")["arka_plan"]
        self.assertEqual([x["ad"] for x in bp], ["Uzun tarama"])

    def test_sayfa_ogeleri_var(self):
        assets = os.path.join(AD, "..", "assets")
        with open(os.path.join(assets, "onaylar.html"), encoding="utf-8") as f:
            self.assertIn('id="perspDurum"', f.read())
        with open(os.path.join(assets, "onaylar.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn("perspDurumCiz", js)
        self.assertIn("yapıldı", js)


if __name__ == "__main__":
    unittest.main()
