"""I-312: panel veri alma gecikmesi — süre günlüğü (P1), is_serit N+1 düzeltmesi (P3), istemci yeniden deneme (P4)."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))

import panel  # noqa: E402
import is_kaydi as IK  # noqa: E402


class GecikmeGunluguTest(unittest.TestCase):
    def test_yavas_istek_isaretlenir(self):
        with tempfile.TemporaryDirectory() as d:
            yol = os.path.join(d, "g.jsonl")
            with mock.patch.object(panel, "GECIKME_GUNLUK", yol):
                panel.gecikme_yaz("/isler.json?alan=*", 1.5, 200)
                panel.gecikme_yaz("/saglik", 0.01, 200)
            satirlar = [json.loads(s) for s in open(yol, encoding="utf-8")]
        self.assertEqual([s["yol"] for s in satirlar], ["/isler.json", "/saglik"])
        self.assertTrue(satirlar[0]["yavas"])
        self.assertEqual(satirlar[0]["alan"], "*")
        self.assertFalse(satirlar[1]["yavas"])

    def test_gunluk_hatasi_istegi_bozmaz(self):
        with mock.patch.object(panel, "GECIKME_GUNLUK", os.path.join(os.devnull, "x", "g.jsonl")):
            panel.gecikme_yaz("/saglik", 0.0, 200)   # istisna fırlatmamalı


class IsSeritTekGirisTest(unittest.TestCase):
    def test_is_serit_tum_is_listesini_cozmez(self):
        """Gerileme: is_serit is_liste(sd) çağırırsa panel iş sayısının karesi kadar dosya sistemi çağrısı yapar."""
        with mock.patch.object(IK, "is_liste", side_effect=AssertionError("is_liste çağrıldı")), \
                mock.patch.object(IK, "is_al", return_value={"id": "I-1"}), \
                mock.patch.object(IK, "merkez_giris", return_value={"klasor": "yok", "baslik": "x", "durum": "acik"}) as mg, \
                mock.patch.object(IK, "todo_maddeleri", return_value=[]):
            try:
                IK.is_serit("sd", "I-1", tum_kartlar=[])
            except AssertionError:
                raise
            except Exception:  # noqa: BLE001  (ileri adımlar sahte veriyle düşebilir; yalnız çağrı biçimi sınanır)
                pass
            mg.assert_called_once_with("sd", "I-1")


class TodoOnbellekTest(unittest.TestCase):
    def test_degismeyen_todo_bir_kez_ayristirilir_degisince_yenilenir(self):
        with tempfile.TemporaryDirectory() as d:
            yol = os.path.join(d, "todo.md")
            open(yol, "w", encoding="utf-8").write("- [ ] P1: a\n")
            IK._TODO_ONBELLEK.clear()
            with mock.patch.object(IK, "_todo_dosyasi", return_value=yol), \
                    mock.patch.object(IK, "_todo_ayristir", wraps=IK._todo_ayristir) as ay:
                m1 = IK.todo_maddeleri(d)
                m1[0]["metin"] = "bozuldu"          # çağıranın değişikliği önbelleği kirletmemeli
                m2 = IK.todo_maddeleri(d)
                self.assertEqual(ay.call_count, 1)
                self.assertNotEqual(m2[0]["metin"], "bozuldu")
                open(yol, "w", encoding="utf-8").write("- [x] P1: a\n- [ ] P2: b\n")
                self.assertEqual(len(IK.todo_maddeleri(d)), 2)
                self.assertEqual(ay.call_count, 2)


class IsitmaKapsamiTest(unittest.TestCase):
    def test_acilis_isitmasi_yildiz_alani_da_ister(self):
        istenen = []
        with mock.patch.object(panel.L, "calisma_alanlari", return_value=[{"id": "a", "orkestra": True}]),                 mock.patch.object(panel.urllib.request, "urlopen", side_effect=lambda u, timeout=0: istenen.append(u) or mock.Mock(read=lambda: b"")):
            panel._isit(1)
        self.assertTrue(any("alan=*" in u for u in istenen))
        self.assertTrue(any("alan=a" in u for u in istenen))


class IstemciYenidenDenemeTest(unittest.TestCase):
    def test_getir_zaman_asiminda_yeniden_dener_ve_bayat_isaretler(self):
        js = open(os.path.join(KOK, "assets", "app.js"), encoding="utf-8").read()
        self.assertIn("const DENEME = 2", js)
        self.assertIn("k.bayat = !!k.veri", js)
        self.assertIn("e.sunucu", js)   # HTTP/JSON hatası yeniden denenmez


if __name__ == "__main__":
    unittest.main()
