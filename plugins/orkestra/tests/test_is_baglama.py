"""I-297 P9: bağsız oturumda otomatik bağlama. Regresyon (I-021 vakası: ayırt edilemeyen iki iş arasında bağlanmaz),
güven etiketi ve 120 etiketli örnekte ölçüm (60 olumlu: mesajın işi aday listede; 60 olumsuz: listede yok).
Eşikler (ADR-0114): yanlış bağ (olumsuzda bagla) gözlenen 0 ve Wilson %95 üst <=%6,1; bağsız kalma (olumluda bagla çıkmadı) <=%20.
Kaynak: tests/veri/is_baglama_ornek.jsonl (iş başlıklarından türetilmiş; sınırı mevcut durum §5).
`py -3.13 -m pytest plugins/orkestra/tests/test_is_baglama.py -s`
"""
import json
import os
import sys
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
sys.path.insert(0, os.path.join(KOK, "tests"))
import is_yonlendirme as IY  # noqa: E402
from test_konu_kaymasi_olcum import wilson_ust  # noqa: E402

VERI = os.path.join(KOK, "tests", "veri", "is_baglama_ornek.jsonl")
BAG = IY.baglama_ayari(None)


def karar_ver(mesaj, adaylar, baglama=BAG):
    puan = IY.eslestir(mesaj, adaylar, None, baglama)
    return IY.karar(puan, None, baglama), IY.guven(puan, baglama), puan


class RegresyonTest(unittest.TestCase):
    ADAY = [{"id": "I-A", "baslik": "Orkestra sohbet modu plan auto seçimi", "klasor": "010-orkestra-sohbet-modu"},
            {"id": "I-B", "baslik": "Orkestra sohbet oturum kapsamı konu kayması", "klasor": "011-orkestra-sohbet-kapsam"}]

    def test_ayirt_edilemeyen_iki_is_arasinda_baglanmaz(self):
        k, _, _ = karar_ver("orkestra sohbet davranışı nasıl çalışıyor", self.ADAY)
        self.assertNotEqual(k[0], "bagla")

    def test_eski_davranista_baglardi(self):
        puan = IY.eslestir("orkestra sohbet modu plan auto seçimi", self.ADAY)
        self.assertEqual(IY.karar(puan)[0], "bagla")

    def test_net_eslesme_baglanir_ve_kesin_etiketi(self):
        aday = self.ADAY + [{"id": "I-C", "baslik": "Fatura raporu entegrasyonu", "klasor": "012-fatura"}]
        k, g, _ = karar_ver("fatura raporu entegrasyonu", aday)
        self.assertEqual(k, ("bagla", "I-C"))
        self.assertEqual(g, "kesin")

    def test_kapali_modda_eski_davranis(self):
        kapali = IY.baglama_ayari({"mod": "kapali"})
        puan = IY.eslestir("orkestra sohbet modu plan auto seçimi", self.ADAY, None, kapali)
        self.assertEqual(IY.karar(puan, None, kapali)[0], "bagla")

    def test_bozuk_ayar_varsayilana_duser(self):
        self.assertEqual(IY.baglama_ayari({"marj": "x", "mod": "?"}), IY.BAGLAMA_VARSAYILAN)


class OlcumTest(unittest.TestCase):
    def test_esikler(self):
        with open(VERI, encoding="utf-8") as f:
            v = [json.loads(s) for s in f if s.strip()]
        olumlu = [x for x in v if x["etiket"] == "olumlu"]
        olumsuz = [x for x in v if x["etiket"] == "olumsuz"]
        self.assertEqual((len(olumlu), len(olumsuz)), (60, 60))
        yanlis = sum(1 for x in olumsuz if karar_ver(x["mesaj"], x["adaylar"])[0][0] == "bagla")
        yanlis_eski = sum(1 for x in olumsuz if IY.karar(IY.eslestir(x["mesaj"], x["adaylar"]))[0] in ("bagla", "sec"))
        bagsiz = sum(1 for x in olumlu if karar_ver(x["mesaj"], x["adaylar"])[0] != ("bagla", x["hedef"]))
        yanlis_hedef = sum(1 for x in olumlu if karar_ver(x["mesaj"], x["adaylar"])[0][0] == "bagla"
                           and karar_ver(x["mesaj"], x["adaylar"])[0][1] != x["hedef"])
        print("\nolumsuz yanlış bağ %d/60 (Wilson üst %.3f; eski davranışta bagla+sec %d/60); olumlu bağsız kalma %d/60=%.2f; olumluda yanlış iş %d"
              % (yanlis, wilson_ust(yanlis, 60), yanlis_eski, bagsiz, bagsiz / 60, yanlis_hedef))
        self.assertEqual(yanlis, 0)
        self.assertLessEqual(wilson_ust(yanlis, 60), 0.061)
        self.assertEqual(yanlis_hedef, 0)
        self.assertLessEqual(bagsiz / 60, 0.20)


if __name__ == "__main__":
    unittest.main()
