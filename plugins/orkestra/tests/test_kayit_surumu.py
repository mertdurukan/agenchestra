"""Kalıcı kayıtlarda biçim sürümü ("v").

K1  jsonl_ekle, defter_ekle ve kart_yaz yeni kayda v=KAYIT_SURUMU yazar.
K2  v alanı olmayan eski kayıt olduğu gibi okunur ve sürüm 0 sayılır (dönüştürülmez).
K3  Kayıtta v zaten varsa üzerine yazılmaz; bozuk v 0 sayılır.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import ork_lib as L  # noqa: E402


class KayitSurumu(unittest.TestCase):
    def setUp(self):
        self.sd = tempfile.mkdtemp(prefix="ork_surum_")

    def tearDown(self):
        shutil.rmtree(self.sd, ignore_errors=True)

    def test_jsonl_ekle_surum_yazar(self):
        yol = os.path.join(self.sd, "maliyet.jsonl")
        L.jsonl_ekle(yol, {"zaman": "z", "ajan": "a"})
        (k,) = L.jsonl_oku(yol)
        self.assertEqual(k["v"], L.KAYIT_SURUMU)
        self.assertEqual(k["ajan"], "a")

    def test_defter_ekle_surum_yazar(self):
        L.defter_ekle(self.sd, {"gorev": "G-001", "ajan": "a", "sonuc": "tamam"})
        (k,) = L.defter_kayitlari(self.sd)
        self.assertEqual(L.kayit_surumu(k), L.KAYIT_SURUMU)

    def test_kart_yaz_surum_yazar(self):
        os.makedirs(os.path.join(self.sd, "gorevler"))
        L.kart_yaz(self.sd, {"id": "G-001", "baslik": "b"})
        with open(L.kart_yolu(self.sd, "G-001"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["v"], L.KAYIT_SURUMU)

    def test_eski_kayit_surum_0_ve_okunur(self):
        yol = os.path.join(self.sd, "gunluk.jsonl")
        with open(yol, "w", encoding="utf-8") as f:
            f.write(json.dumps({"zaman": "z", "tur": "istek"}) + "\n")
        L.jsonl_ekle(yol, {"zaman": "z2", "tur": "istek"})
        eski, yeni = L.jsonl_oku(yol)
        self.assertEqual(L.kayit_surumu(eski), 0)
        self.assertEqual(eski["tur"], "istek")
        self.assertEqual(L.kayit_surumu(yeni), L.KAYIT_SURUMU)

    def test_var_olan_v_korunur_bozuk_v_sifir(self):
        yol = os.path.join(self.sd, "x.jsonl")
        L.jsonl_ekle(yol, {"v": 7, "a": 1})
        self.assertEqual(L.jsonl_oku(yol)[0]["v"], 7)
        for bozuk in ({"v": "x"}, {"v": None}, {}, None, "s"):
            self.assertEqual(L.kayit_surumu(bozuk), 0)


if __name__ == "__main__":
    unittest.main()
