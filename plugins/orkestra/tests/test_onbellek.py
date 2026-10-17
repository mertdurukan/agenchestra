"""İşlem içi önbellekler: ork_lib.kartlar() ve ork_lib.fiyat_tablosu().
`py -3.13 -m pytest plugins/orkestra/tests/test_onbellek.py -q`

1) kartlar(): dosya değişince (mtime_ns/boyut) yeni içerik görünür; silinen kart düşer.
2) kartlar(): dönen kart değiştirilirse önbellek bozulmaz (her çağrıda bağımsız kopya).
3) kartlar(): bozuk kart önbellekte kalsa da düzeldiğinde görünür.
4) fiyat_tablosu(): dosya değişmedikçe aynı nesne, değişince yeniden okunur.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_cekirdek as C  # noqa: E402

sys.path.insert(0, os.path.join(C.KOK, "scripts"))
import ork_lib as L  # noqa: E402


def _yaz(yol, veri):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8", newline="\n") as f:
        f.write(veri if isinstance(veri, str) else json.dumps(veri))


class KartOnbellegi(unittest.TestCase):
    def setUp(self):
        self.sd = tempfile.mkdtemp(prefix="ork_onbellek_sd_")
        self.yol = os.path.join(self.sd, "gorevler", "G-001.json")

    def tearDown(self):
        shutil.rmtree(self.sd, ignore_errors=True)

    def test_dosya_degisince_yeni_icerik_gorunur(self):
        _yaz(self.yol, {"id": "G-001", "baslik": "eski"})
        self.assertEqual(L.kartlar(self.sd)[0]["baslik"], "eski")
        _yaz(self.yol, {"id": "G-001", "baslik": "yeni baslik daha uzun"})
        self.assertEqual(L.kartlar(self.sd)[0]["baslik"], "yeni baslik daha uzun")

    def test_silinen_kart_duser(self):
        _yaz(self.yol, {"id": "G-001"})
        self.assertEqual(len(L.kartlar(self.sd)), 1)
        os.remove(self.yol)
        self.assertEqual(L.kartlar(self.sd), [])

    def test_donen_kart_degistirilirse_onbellek_bozulmaz(self):
        _yaz(self.yol, {"id": "G-001", "baslik": "temiz", "liste": [1]})
        k = L.kartlar(self.sd)[0]
        k["baslik"] = "bozuldu"
        k["liste"].append(2)
        yine = L.kartlar(self.sd)[0]
        self.assertEqual(yine["baslik"], "temiz")
        self.assertEqual(yine["liste"], [1])

    def test_bozuk_kart_duzelince_gorunur(self):
        _yaz(self.yol, "{bozuk")
        self.assertEqual(L.kartlar(self.sd), [])
        self.assertEqual(L.kartlar(self.sd), [])  # önbellekten, yine atlanır
        _yaz(self.yol, {"id": "G-001", "baslik": "düzeldi"})
        self.assertEqual([k["id"] for k in L.kartlar(self.sd)], ["G-001"])


class FiyatOnbellegi(unittest.TestCase):
    def test_degismedikce_ayni_nesne(self):
        self.assertIs(L.fiyat_tablosu(), L.fiyat_tablosu())

    def test_dosya_degisince_yeniden_okunur(self):
        kok = tempfile.mkdtemp(prefix="ork_fiyat_")
        try:
            yol = os.path.join(kok, "bin", "fiyat.json")
            _yaz(yol, {"varsayilan": "a", "modeller": {"a": {"x": 1}}})
            with mock.patch.object(L, "PLUGIN_ROOT", kok):
                self.assertEqual(L.fiyat_tablosu()["modeller"]["a"]["x"], 1)
                _yaz(yol, {"varsayilan": "a", "modeller": {"a": {"x": 22}}})
                self.assertEqual(L.fiyat_tablosu()["modeller"]["a"]["x"], 22)
        finally:
            shutil.rmtree(kok, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
