"""I-159 P6: `orkestra maliyet taban` — kalem dökümü, eşik tablosu, iş başına $ (salt okuma; sentetik transkript)."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

AD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AD, "..", "scripts"))
import maliyet_taban as MT  # noqa: E402
import ork_lib as L  # noqa: E402


def yaz(yol, kayitlar):
    with open(yol, "w", encoding="utf-8") as f:
        for k in kayitlar:
            f.write(json.dumps(k) + "\n")


def cagri(mid, okuma, yazma=0, girdi=1, sidechain=False):
    return {"type": "assistant", "isSidechain": sidechain,
            "message": {"id": mid, "model": "claude-opus-5-5",
                        "usage": {"input_tokens": girdi, "output_tokens": 10, "cache_read_input_tokens": okuma,
                                  "cache_creation_input_tokens": yazma}}}


class Taban(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def test_kalem_dokumu_ve_ilk_cagri(self):
        f = os.path.join(self.d, "a.jsonl")
        yaz(f, [{"attachment": {"type": "instructions", "files": [{"content": "k" * 100}, {"content": "z" * 20}]}},
                {"attachment": {"type": "skill_listing", "content": "s" * 50}},
                {"type": "user", "message": {"content": "merhaba"}},
                cagri("m1", 1000, 500)])
        kalem, ilk = MT.oturum_taban(f)
        self.assertEqual((kalem["kural dosyaları"], kalem["skill listesi"], kalem["ilk kullanıcı mesajı"]), (120, 50, 7))
        self.assertEqual(ilk, 1000 + 500 + 1)

    def test_taban_bolumu_medyan_ve_kalibre_isareti(self):
        for i, ilk in enumerate((100, 300, 200)):
            yaz(os.path.join(self.d, f"{i}.jsonl"), [{"attachment": {"type": "instructions", "files": [{"content": "k" * 1000}]}},
                                                      cagri(f"m{i}", ilk)])
        r = MT.taban_bolumu(self.d, 1)
        self.assertEqual((r["oturum"], r["ilk_medyan"]), (3, 201))
        kural = next(k for k in r["kalemler"] if k["kalem"] == "kural dosyaları")
        self.assertTrue(kural["kalibre"])
        self.assertEqual(kural["token"], int(1000 * 0.447))
        self.assertFalse(next(k for k in r["kalemler"] if k["kalem"] == "skill listesi")["kalibre"])

    def test_esik_bolumu_tekilleştirir_yan_zinciri_atlar(self):
        yaz(os.path.join(self.d, "a.jsonl"), [cagri("m1", 120_000), cagri("m1", 120_000), cagri("m2", 160_000),
                                              cagri("m3", 210_000), cagri("y", 400_000, sidechain=True)])
        r = MT.esik_bolumu(self.d, 1)
        self.assertEqual(r["cagri"], 3)
        sat = {x["esik"]: x for x in r["esikler"]}
        self.assertEqual([sat[e]["cagri"] for e in (100_000, 150_000, 200_000)], [3, 2, 1])
        okuma = L.model_fiyati("claude-opus-5-5")["onbellek_okuma"]
        self.assertAlmostEqual(sat[200_000]["devir_kazanc_ust_sinir"], (210_001 - 200_000) * okuma / 1e6, places=6)
        self.assertEqual(sat[200_000]["oturum"], 1)

    def test_sonra_yalniz_sonradan_baslayan_oturumlari_alir(self):
        import datetime as D
        for ad, z in (("eski", "2026-10-20T10:00:00+00:00"), ("yeni", "2026-10-22T10:00:00+00:00")):
            yaz(os.path.join(self.d, ad + ".jsonl"), [{"type": "user", "timestamp": z, "message": {"content": "x"}}, cagri(ad, 1000)])
        kesim = D.datetime(2026, 10, 21, tzinfo=D.timezone.utc)
        self.assertEqual(MT.taban_bolumu(self.d, 9999)["oturum"], 2)
        self.assertEqual(MT.taban_bolumu(self.d, 9999, kesim)["oturum"], 1)
        self.assertEqual(MT.esik_bolumu(self.d, 9999, sonra=kesim)["cagri"], 1)

    def test_bos_dizin(self):
        self.assertEqual(MT.taban_bolumu(self.d, 1), {"oturum": 0})
        self.assertEqual(MT.esik_bolumu(self.d, 1), {"cagri": 0})

    def test_oran_dosyasi_yoksa_varsayilan(self):
        with mock.patch.object(MT, "_ORAN_YOLU", os.path.join(self.d, "yok.json")):
            self.assertEqual(MT.oranlar(), MT._ORAN_VARSAYILAN)


class IsBasina(unittest.TestCase):
    def test_kapanan_is_ve_teslim_kart(self):
        sd = tempfile.mkdtemp()
        isk = os.path.join(sd, "is1")
        os.makedirs(isk)
        json.dump({"id": "I-1", "gecmis": [{"olay": "durum:kapandi", "zaman": "2026-10-20T10:00:00"}]}, open(os.path.join(isk, "is.json"), "w"))
        json.dump({"isler": {"I-1": {"durum": "kapandi", "klasor": isk}, "I-2": {"durum": "acik", "klasor": isk}}}, open(os.path.join(sd, "isler.json"), "w"))
        os.makedirs(os.path.join(sd, "gorevler"))
        json.dump({"id": "G-1", "durum": "teslim", "gecmis": [{"olay": "teslim", "zaman": "2026-10-21T10:00:00"}],
                   "denetimler": [{"karar": "ret"}, {"karar": "onay"}]}, open(os.path.join(sd, "gorevler", "G-1.json"), "w"))
        json.dump({"id": "G-2", "durum": "teslim", "gecmis": [{"olay": "teslim", "zaman": "2026-10-21T11:00:00"}],
                   "denetimler": [{"karar": "onay"}]}, open(os.path.join(sd, "gorevler", "G-2.json"), "w"))
        defter = [{"zaman": "2026-10-20T09:00:00", "is": "I-1", "gorev": "-", "maliyet_usd": 6.0},
                  {"zaman": "2026-10-21T09:00:00", "is": "I-1", "gorev": "G-1", "maliyet_usd": 3.0},
                  {"zaman": "2026-10-21T09:30:00", "gorev": "G-2", "maliyet_usd": 1.0},
                  {"zaman": "2026-10-10T09:00:00", "is": "I-1", "gorev": "-", "maliyet_usd": 50.0}]
        with mock.patch.object(L, "maliyet_kayitlari", return_value=defter):
            r = MT.is_basina_bolumu(sd, "2026-10-16")
        self.assertEqual((r["kapanan_is"], r["a_usd"]), (1, 9.0))   # pencere dışı 50$ sayılmaz
        self.assertEqual((r["teslim_kart"], r["b_usd"], r["ret_orani"]), (2, 2.0, 0.5))

    def test_isler_yoksa_cokmez(self):
        sd = tempfile.mkdtemp()
        with mock.patch.object(L, "maliyet_kayitlari", return_value=[]):
            r = MT.is_basina_bolumu(sd, "2026-10-16")
        self.assertEqual((r["kapanan_is"], r["a_usd"], r["teslim_kart"], r["b_usd"]), (0, None, 0, None))


if __name__ == "__main__":
    unittest.main()
