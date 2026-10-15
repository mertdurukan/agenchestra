"""G-069: kpi.olcum(sd, gun=None, aralik=None) geriye uyumlu 'aralik=(bas,bit)' parametresi.

Sözleşme: aralik = (bas, bit) tz'li datetime çifti, yarı açık [bas, bit). Kartlar 'olusturma', maliyet satırları
'zaman' ile süzülür. aralik verilmezse davranış değişmez.
"""
import datetime
import json
import os
import sys
import tempfile
import unittest

AD = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(AD, "..", "scripts")
sys.path.insert(0, SCRIPTS)
import kpi  # noqa: E402

TZ = datetime.timezone(datetime.timedelta(hours=3))


def dt(g, sa=0):
    return datetime.datetime(2026, 3, g, sa, 0, 0, tzinfo=TZ)


class AralikTest(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.sd = os.path.join(self.t.name, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "gorevler"))
        self.mal = []

    def tearDown(self):
        self.t.cleanup()

    def kart(self, no, zaman, karar):
        gid = f"G-{no:03d}"
        k = {"id": gid, "baslik": "x", "sinif": "kod", "basamak": "T2", "baslangic_basamak": "T2",
             "durum": "teslim", "olusturma": zaman.isoformat(),
             "gecmis": [{"zaman": zaman.isoformat(), "olay": "olusturuldu", "basamak": "T2"}],
             "isciler": [gid + "-i0"],
             "denetimler": [{"zaman": zaman.isoformat(), "sira": 1, "karar": karar, "ajan": "x"}]}
        for ad, v in ((gid + ".json", k), (gid + ".denetim.json", k["denetimler"])):
            with open(os.path.join(self.sd, "gorevler", ad), "w", encoding="utf-8") as f:
                json.dump(v, f)
        self.mal.append({"zaman": zaman.isoformat(), "oturum": "o", "gorev": gid, "agent_id": "a" + gid,
                         "model": "m", "giris": 1, "cikis": 1, "onbellek_okuma": 0, "onbellek_yazma": 0,
                         "maliyet_usd": 1.0, "kaynak": "tur", "tarife": "1sa"})

    def bitir(self):
        with open(os.path.join(self.sd, "maliyet.jsonl"), "w", encoding="utf-8") as f:
            for r in self.mal:
                f.write(json.dumps(r) + "\n")

    def test_aralik_kartlari_ve_maliyeti_suzer(self):
        self.kart(1, dt(9, 12), "ret")      # önceki gün
        self.kart(2, dt(10, 12), "onay")    # aralık içi
        self.kart(3, dt(10, 18), "onay")    # aralık içi
        self.kart(4, dt(11, 12), "ret")     # sonraki gün
        self.bitir()
        s = kpi.olcum(self.sd, aralik=(dt(10), dt(11)))
        self.assertEqual(s["genel"]["ret_orani"], 0.0)
        self.assertEqual(s["genel"]["basari_basina_maliyet"], 1.0)
        self.assertEqual(s["genel"]["yeniden_deneme_carpani"], 1.0)

    def test_aralik_yari_acik_bas_dahil_bit_haric(self):
        self.kart(1, dt(10, 0), "ret")   # tam bas: dahil
        self.kart(2, dt(11, 0), "onay")  # tam bit: hariç
        self.bitir()
        s = kpi.olcum(self.sd, aralik=(dt(10), dt(11)))
        self.assertEqual(s["genel"]["ret_orani"], 1.0)

    def test_aralikta_kart_yoksa_degerler_none(self):
        self.kart(1, dt(9, 12), "ret")
        self.bitir()
        s = kpi.olcum(self.sd, aralik=(dt(10), dt(11)))
        self.assertIsNone(s["genel"]["ret_orani"])
        self.assertIsNone(s["genel"]["basari_basina_maliyet"])

    def test_aralik_verilmezse_eski_davranis(self):
        self.kart(1, dt(9, 12), "ret")
        self.kart(2, dt(10, 12), "onay")
        self.bitir()
        s = kpi.olcum(self.sd)
        self.assertEqual(s["genel"]["ret_orani"], 0.5)
        self.assertEqual(kpi.olcum(self.sd, None, None)["genel"]["ret_orani"], 0.5)


if __name__ == "__main__":
    unittest.main()
