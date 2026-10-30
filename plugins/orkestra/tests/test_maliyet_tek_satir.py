"""I-271 P1: span başına tek maliyet satırı.

Kabul kriterleri:
  K1  Aynı span için hook + tur senaryosunda defterde tek satır kalır.
  K2  Hook'un turdan fazla saydığı token 'hook-artik' olarak korunur; netlenmiş ve netlenmemiş defterin okuyucu
      toplamı birebir aynıdır (kayıp 0).
  K4  Tur satırı yoksa (ya da başka span'e aitse) hook satırı defterde kalır.
  K5  Bozuk satır, yarım son satır ve bozuk hook_artik alanı yazımı ve okumayı bozmaz.
  +   Okuyucu artığı span bazında netler: bir span'in eksiği öteki span'in fazlasını yutmaz.
"""
import json
import os
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import ork_lib as L  # noqa: E402
from komutlar import maliyet as KM  # noqa: E402

MODEL = "claude-opus-5-5"


def hook(span, g, c, o, y, agent_id=None, oturum="s1", zaman="2026-10-30T10:00:00+03:00", model=MODEL):
    return {"zaman": zaman, "oturum": oturum, "gorev": "-", "surec": "is", "ajan": "x", "agent_id": agent_id,
            "model": model, "giris": g, "cikis": c, "onbellek_okuma": o, "onbellek_yazma": y, "maliyet_usd": 0.0,
            "kaynak": "hook", "span_id": span, "tur": 3, "arac_cagrisi": 7}


def tur(span, g, c, o, y, agent_id=None, oturum="s1", zaman="2026-10-30T10:00:02+03:00", model=MODEL):
    r = hook(span, g, c, o, y, agent_id, oturum, zaman, model)
    for a in ("tur", "arac_cagrisi"):
        r.pop(a)
    r.update(kaynak="tur", tarife="1sa")
    return r


class TekSatir(unittest.TestCase):
    def setUp(self):
        self.sd = tempfile.mkdtemp()
        self.yol = os.path.join(self.sd, "maliyet.jsonl")

    def satirlar(self):
        with open(self.yol, encoding="utf-8") as f:
            return [ln for ln in f.read().split("\n") if ln]

    def oku(self, yol=None):
        return L._maliyet_kayitlari_oku(yol or self.yol, duzeltme=False)

    def toplam(self, yol=None):
        return L.kalemler(self.oku(yol))["token"]

    def iki_yol(self, olaylar):
        """Aynı olay dizisini düz eklemeyle (eski yazıcı) ve netleyen yazıcıyla yazar; iki defterin yolunu döner."""
        duz = os.path.join(self.sd, "duz.jsonl")
        for r in olaylar:
            L.jsonl_ekle(duz, r)
            if r["kaynak"] == "tur":
                KM.tur_satiri_yaz(self.yol, r)
            else:
                L.jsonl_ekle(self.yol, r)
        return duz

    # K1
    def test_k1_ana_span_tek_satir(self):
        L.jsonl_ekle(self.yol, hook("i1.t1", 100, 50, 1000, 200))
        self.assertTrue(KM.tur_satiri_yaz(self.yol, tur("i1.t1", 100, 50, 1000, 200)))
        s = self.satirlar()
        self.assertEqual(len(s), 1)
        r = json.loads(s[0])
        self.assertEqual(r["kaynak"], "tur")
        self.assertTrue(r["hook_netlendi"])
        self.assertNotIn("hook_artik", r)
        self.assertEqual(r["hook_meta"], {"tur": 3, "arac_cagrisi": 7})  # hook'a özgü alanlar kaybolmaz
        self.assertEqual([x["kaynak"] for x in self.oku()], ["tur"])

    def test_k1_alt_ajan_span_tek_satir(self):
        L.jsonl_ekle(self.yol, hook("i1.a-w1", 10, 5, 100, 20, agent_id="w1"))
        KM.tur_satiri_yaz(self.yol, tur("i1.a-w1", 10, 5, 100, 20, agent_id="w1"))
        self.assertEqual(len(self.satirlar()), 1)

    # K2
    def test_k2_fazla_token_hook_artik_olarak_korunur(self):
        duz = self.iki_yol([hook("i1.t1", 120, 60, 1000, 300), tur("i1.t1", 100, 50, 1000, 200)])
        self.assertEqual(len(self.satirlar()), 1)
        self.assertEqual(json.loads(self.satirlar()[0])["hook_artik"],
                         {"giris": 20, "cikis": 10, "onbellek_okuma": 0, "onbellek_yazma": 100,
                          "zaman": "2026-10-30T10:00:00+03:00"})
        art = [r for r in self.oku() if r["kaynak"] == "hook-artik"]
        self.assertEqual([(r["giris"], r["cikis"], r["onbellek_okuma"], r["onbellek_yazma"]) for r in art],
                         [(20, 10, 0, 100)])
        self.assertEqual(self.toplam(), self.toplam(duz))  # kayıp 0
        self.assertEqual(self.toplam()["toplam"], 120 + 60 + 1000 + 300)
        self.assertAlmostEqual(L.kalemler(self.oku())["usd"]["toplam"], L.kalemler(self.oku(duz))["usd"]["toplam"], places=9)

    def test_k2_ayni_span_ikinci_tur_artigi_yeniden_netler(self):
        duz = self.iki_yol([hook("i1.t1", 300, 0, 0, 0), tur("i1.t1", 100, 0, 0, 0),
                            tur("i1.t1", 150, 0, 0, 0, zaman="2026-10-30T10:00:03+03:00")])
        s = [json.loads(x) for x in self.satirlar()]
        self.assertEqual([x["kaynak"] for x in s], ["tur", "tur"])
        self.assertNotIn("hook_artik", s[0])
        self.assertEqual(s[1]["hook_artik"]["giris"], 50)
        self.assertEqual(self.toplam(), self.toplam(duz))

    def test_k2_alt_ajan_birikimli_devam_kayipsiz(self):
        """SendMessage ile sürdürülen alt ajan: ikinci hook satırı birikimlidir; aynı span ve sonraki span."""
        olaylar = [hook("i1.a-w1", 100, 10, 0, 0, "w1", zaman="2026-10-30T10:00:00+03:00"),
                   tur("i1.a-w1", 80, 10, 0, 0, "w1", zaman="2026-10-30T10:00:02+03:00"),
                   hook("i1.a-w1", 250, 30, 0, 0, "w1", zaman="2026-10-30T10:05:00+03:00"),
                   tur("i1.a-w1", 150, 20, 0, 0, "w1", zaman="2026-10-30T10:05:02+03:00"),
                   hook("i2.a-w1", 400, 40, 0, 0, "w1", zaman="2026-10-30T11:00:00+03:00"),
                   tur("i2.a-w1", 100, 10, 0, 0, "w1", zaman="2026-10-30T11:00:02+03:00")]
        duz = self.iki_yol(olaylar)
        self.assertEqual(len(self.satirlar()), 3)
        self.assertEqual(self.toplam(), self.toplam(duz))
        self.assertEqual(self.toplam()["giris"], 400)  # birikimli son anlık görüntü = 400, iki kez sayılmaz

    # K4
    def test_k4_tur_yoksa_hook_kalir(self):
        L.jsonl_ekle(self.yol, hook("i1.t1", 100, 50, 1000, 200))
        self.assertEqual([x["kaynak"] for x in self.oku()], ["hook"])
        self.assertFalse(KM.tur_satiri_yaz(self.yol, tur("i1.t2", 10, 5, 0, 0)))  # başka span
        self.assertEqual([json.loads(x)["kaynak"] for x in self.satirlar()], ["hook", "tur"])

    def test_k4_span_siz_tur_duz_eklenir(self):
        L.jsonl_ekle(self.yol, hook(None, 100, 0, 0, 0))
        r = tur(None, 100, 0, 0, 0)
        self.assertFalse(KM.tur_satiri_yaz(self.yol, r))
        self.assertEqual(len(self.satirlar()), 2)

    def test_pencere_disindaki_hook_dokunulmaz_toplam_ayni(self):
        duz = os.path.join(self.sd, "duz.jsonl")
        for r in (hook("i1.t1", 120, 0, 0, 0),) + tuple(tur(f"i0.t{n}", 1, 0, 0, 0, oturum="baska") for n in range(50)):
            L.jsonl_ekle(self.yol, r)
            L.jsonl_ekle(duz, r)
        t = tur("i1.t1", 100, 0, 0, 0)
        L.jsonl_ekle(duz, t)
        self.assertFalse(KM.tur_satiri_yaz(self.yol, t, pencere=2000))
        self.assertEqual(len(self.satirlar()), 52)
        self.assertEqual(self.toplam(), self.toplam(duz))

    # K5
    def test_k5_bozuk_satirlar_korunur_ve_atlanir(self):
        with open(self.yol, "w", encoding="utf-8", newline="\n") as f:
            f.write("{bozuk json\n")
            f.write(json.dumps(hook("i1.t1", 120, 0, 0, 0)) + "\n")
            f.write('{"yarim": ')  # yarım son satır (newline yok)
        self.assertTrue(KM.tur_satiri_yaz(self.yol, tur("i1.t1", 100, 0, 0, 0)))
        s = self.satirlar()
        self.assertEqual(s[0], "{bozuk json")
        self.assertEqual(s[1], '{"yarim": ')
        self.assertEqual(json.loads(s[2])["hook_artik"]["giris"], 20)
        self.assertEqual(self.toplam()["giris"], 120)

    def test_k5_yarim_son_satira_duz_ekleme_yapismaz(self):
        with open(self.yol, "w", encoding="utf-8", newline="\n") as f:
            f.write('{"yarim": ')
        KM.tur_satiri_yaz(self.yol, tur("i1.t1", 5, 0, 0, 0))
        self.assertEqual(len(self.satirlar()), 2)
        self.assertEqual([r["kaynak"] for r in self.oku()], ["tur"])

    def test_k5_bozuk_hook_artik_alani_okumayi_bozmaz(self):
        r = tur("i1.t1", 5, 0, 0, 0)
        r.update(hook_artik="bozuk", hook_netlendi=True)
        r2 = tur("i1.t2", 5, 0, 0, 0)
        r2.update(hook_artik={"giris": "x", "cikis": -3, "onbellek_okuma": True})
        L.jsonl_ekle(self.yol, r)
        L.jsonl_ekle(self.yol, r2)
        self.assertEqual([x["kaynak"] for x in self.oku()], ["tur", "tur"])

    # okuyucu: span bazlı netleme
    def test_okuyucu_span_bazli_eksik_fazlayi_yutmaz(self):
        L.jsonl_ekle(self.yol, hook("i1.t1", 150, 0, 0, 0))
        L.jsonl_ekle(self.yol, tur("i1.t1", 100, 0, 0, 0))
        L.jsonl_ekle(self.yol, hook("i1.t2", 50, 0, 0, 0))
        L.jsonl_ekle(self.yol, tur("i1.t2", 100, 0, 0, 0))
        art = [r for r in self.oku() if r["kaynak"] == "hook-artik"]
        self.assertEqual([(r["span_id"], r["giris"]) for r in art], [("i1.t1", 50)])

    def test_okuyucu_span_siz_eski_satirlar_grup_mantigi(self):
        L.jsonl_ekle(self.yol, hook(None, 10, 0, 0, 0, zaman="2026-10-30T09:00:00+03:00"))
        L.jsonl_ekle(self.yol, hook(None, 20, 0, 0, 0))
        L.jsonl_ekle(self.yol, tur(None, 20, 0, 0, 0))
        art = [r for r in self.oku() if r["kaynak"] == "hook-artik"]
        self.assertEqual([r["giris"] for r in art], [10])


if __name__ == "__main__":
    unittest.main()
