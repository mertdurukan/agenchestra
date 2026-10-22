"""Gelen kutusu: geri al süresi (5 sn) dolmadan sayfa yenilenirse onay/ret kararı kaybolmaz.

Kök neden: karar 5 sn'lik zamanlayıcıyla gönderiliyordu; yenilemede zamanlayıcı ölür, POST hiç gitmezdi.
Kriterler:
  K1  Onayla tıklanıp pagehide olunca karar POST'u hemen, keepalive ile gider.
  K2  Geri al'dan sonra pagehide POST göndermez (geri alınan karar kaydedilmez).
"""
import json
import os
import subprocess
import tempfile
import unittest

import test_panel_pencere_birim as TPB


def _calistir(adimlar):
    fx = TPB.fixture()
    fx["/onaylar.json"] = {"acik": True, "alan": {"id": "a"}, "sayac": {"bekliyor": 1, "uygulanacak": 0, "tur": {}},
                           "kayitlar": [{"id": "O-1", "tur": "perspektif", "baslik": "b", "metin": "m", "durum": "bekliyor"}]}
    senaryo = [{"hash": "#/gelen", "adimlar": adimlar}]
    with tempfile.TemporaryDirectory() as t:
        yollar = {a: os.path.join(t, a + ".json") for a in ("fx", "sn", "cikti")}
        json.dump(fx, open(yollar["fx"], "w", encoding="utf-8"), ensure_ascii=False)
        json.dump(senaryo, open(yollar["sn"], "w", encoding="utf-8"), ensure_ascii=False)
        subprocess.run(["node", TPB.DUMAN, TPB.APP, yollar["fx"], yollar["sn"], yollar["cikti"]], check=True, timeout=180)
        cikti = json.load(open(yollar["cikti"], encoding="utf-8"))
    assert cikti["hatalar"] == [], cikti["hatalar"]
    return cikti["sonuc"][0]["postlar"]


class OnayYenileme(unittest.TestCase):
    def test_k1_yenilemede_karar_gonderilir(self):
        postlar = _calistir([["tikla", "karar", {"id": "O-1", "sonuc": "onay"}], ["pencere", "pagehide"]])
        self.assertEqual(len(postlar), 1, postlar)
        self.assertTrue(postlar[0]["keepalive"])
        self.assertEqual({k: postlar[0]["govde"][k] for k in ("islem", "id", "sonuc")}, {"islem": "karar", "id": "O-1", "sonuc": "onay"})

    def test_k2_geri_alinan_karar_gonderilmez(self):
        postlar = _calistir([["tikla", "karar", {"id": "O-1", "sonuc": "ret"}], ["geriAl"], ["pencere", "pagehide"]])
        self.assertEqual(postlar, [])


if __name__ == "__main__":
    unittest.main()
