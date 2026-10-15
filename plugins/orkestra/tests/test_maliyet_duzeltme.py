"""Maliyet defteri düzeltmeleri (M1–M3) ve kural onayında etki kancası (E1).

Kabul kriterleri:
  K1  'tur' satırı okunurken önbellek yazma 1 sa tarifesiyle yeniden fiyatlanır (hook satırlarıyla aynı).
  K2  tur kaydı başlamadan önceki ana-ajan hook token'ı 'hook-artik' satırı olarak korunur; çakışan tur token'ı
      iki kez sayılmaz.
  K3  Alt ajan grubunda hook'un tur'u aşan kısmı yoksa artık satırı eklenmez.
  K4  analitik._formul_usd önbellek yazmayı 1 sa tarifesiyle hesaplar.
  K5  Panelden onaylanan kural onayı taban ve uygulama tarihi kancalarını çağırır.
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import ork_lib as L  # noqa: E402
import analitik  # noqa: E402
import onay  # noqa: E402
import etki  # noqa: E402

MODEL = "claude-opus-4-8"


def satir(kaynak, oturum, agent_id, giris, cikis, okuma, yazma, zaman="2026-10-15T10:00:00+03:00"):
    return {"zaman": zaman, "oturum": oturum, "gorev": "-", "surec": "is", "ajan": "x", "agent_id": agent_id,
            "model": MODEL, "giris": giris, "cikis": cikis, "onbellek_okuma": okuma, "onbellek_yazma": yazma,
            "maliyet_usd": 0.0, "kaynak": kaynak}


class MaliyetDuzeltme(unittest.TestCase):
    def setUp(self):
        self.sd = tempfile.mkdtemp()
        L._MALIYET_ONBELLEK.clear()

    def yaz(self, rows):
        with open(os.path.join(self.sd, "maliyet.jsonl"), "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        L._MALIYET_ONBELLEK.clear()
        return L.maliyet_kayitlari(self.sd)

    def test_k1_tur_1sa_tarife(self):
        out = self.yaz([satir("tur", "s1", None, 0, 0, 0, 1_000_000)])
        f = L.model_fiyati(MODEL)
        self.assertAlmostEqual(out[0]["maliyet_usd"], f["onbellek_yazma_1sa"], places=4)
        self.assertGreater(f["onbellek_yazma_1sa"], f["onbellek_yazma_5dk"])

    def test_k2_ana_ajan_artigi(self):
        out = self.yaz([
            satir("hook", "s1", None, 10, 100, 1000, 500, "2026-10-15T09:00:00+03:00"),
            satir("hook", "s1", None, 20, 200, 2000, 600, "2026-10-15T10:00:00+03:00"),
            satir("tur", "s1", None, 20, 200, 2000, 600),
        ])
        artik = [r for r in out if r["kaynak"] == "hook-artik"]
        self.assertEqual(len(artik), 1)
        self.assertEqual((artik[0]["giris"], artik[0]["cikis"], artik[0]["onbellek_okuma"], artik[0]["onbellek_yazma"]),
                         (30, 300, 3000, 1100) if False else (10, 100, 1000, 500))
        self.assertEqual(len([r for r in out if r["kaynak"] == "tur"]), 1)

    def test_k3_artik_yoksa_satir_yok(self):
        out = self.yaz([
            satir("hook", "s1", "a1", 5, 50, 500, 100),
            satir("tur", "s1", "a1", 5, 50, 500, 100),
        ])
        self.assertEqual([r["kaynak"] for r in out], ["tur"])

    def test_k4_formul_1sa(self):
        f = L.model_fiyati(MODEL)
        self.assertAlmostEqual(analitik._formul_usd({"onbellek_yazma": 1_000_000}, MODEL), f["onbellek_yazma_1sa"], places=4)


class KuralEtkiKancasi(unittest.TestCase):
    def test_k5_kural_onayi_kancalari_cagirir(self):
        sd = tempfile.mkdtemp()
        onay.kural_oner(sd, "Öneri kuralı", "neden", "test")
        onay.esitle(sd)
        bekleyen = [k for k in onay.liste(sd) if k.get("tur") == "kural" and k.get("durum") == "bekliyor"]
        self.assertTrue(bekleyen)
        with mock.patch.object(etki, "kanca_al") as ka, mock.patch.object(etki, "kanca_uygulandi") as ku:
            onay.karar_ver(sd, bekleyen[0]["id"], "onay")
        self.assertEqual(ka.call_count, 1)
        self.assertEqual(ku.call_count, 1)


if __name__ == "__main__":
    unittest.main()
