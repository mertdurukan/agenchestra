"""I-271 P4: boş iş birikimi ve yanlış işe bağlanma — bakim 'ölü yol' ve 'terk' bölümleri, soru mesajı iş açmaz,
is devam geçiş satırı."""
import datetime
import json
import os
import shutil
import sys
import unittest

import test_cekirdek as TC

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
ANA = {"ajan_id": "ana", "ajan_tipi": "ana"}


class _Taban(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown
    cli = TC.Cekirdek.cli

    def merkez(self):
        with open(os.path.join(self.sd, "isler.json"), encoding="utf-8") as f:
            return json.load(f)

    def is_ac(self, ad, eski_saat=30):
        klasor = os.path.join(self.proje, "isler", ad)
        r = self.cli("is", "ac", "Otomatik iş " + ad, "--klasor", klasor)
        self.assertEqual(r.returncode, 0, r.stderr)
        i = r.stdout.split()[0]
        d = self.merkez()
        d["isler"][i]["olusturma"] = (datetime.datetime.now().astimezone()
                                      - datetime.timedelta(hours=eski_saat)).isoformat(timespec="seconds")
        with open(os.path.join(self.sd, "isler.json"), "w", encoding="utf-8") as f:
            json.dump(d, f)
        return i, klasor

    def bakim(self, *args):
        r = self.cli("bakim", "--json", *args, **ANA)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def proje_ayari(self, **kv):
        with open(os.path.join(self.sd, "is_esleme.json"), "w", encoding="utf-8") as f:
            json.dump(kv, f)


class OluYol(_Taban):
    def test_klasoru_olmayan_acik_is_olu_yol_listelenir(self):  # K1
        olu, klasor = self.is_ac("001-silinen", eski_saat=1)
        canli, _ = self.is_ac("002-canli", eski_saat=1)
        shutil.rmtree(klasor)
        r = self.bakim()
        self.assertEqual([g["id"] for g in r["olu_yol"]], [olu])
        self.assertNotIn(canli, [g["id"] for g in r["olu_yol"]])

    def test_goreli_klasor_proje_kokune_gore_cozulur(self):  # K1: göreli yol proje köküne göre
        i, klasor = self.is_ac("003-goreli", eski_saat=1)
        d = self.merkez()
        d["isler"][i]["klasor"] = os.path.relpath(klasor, self.proje)
        with open(os.path.join(self.sd, "isler.json"), "w", encoding="utf-8") as f:
            json.dump(d, f)
        self.assertNotIn(i, [g["id"] for g in self.bakim()["olu_yol"]])

    def test_metin_ciktisi_olu_yol_bolumu_tasir(self):  # K1: metin çıktısı
        olu, klasor = self.is_ac("004-silinen", eski_saat=1)
        shutil.rmtree(klasor)
        r = self.cli("bakim", **ANA)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ölü yol: 1", r.stdout)
        self.assertIn(olu, r.stdout)


class Terk(_Taban):
    def test_esikten_eski_bos_is_terk_taze_ve_maliyetli_degil(self):  # K2
        terk, _ = self.is_ac("001-terk", eski_saat=30)
        self.is_ac("002-taze", eski_saat=2)
        maliyetli, _ = self.is_ac("003-maliyetli", eski_saat=30)
        with open(os.path.join(self.sd, "maliyet.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"zaman": "2026-10-29T10:00:00+03:00", "oturum": "x", "is": maliyetli,
                                "maliyet_usd": 0.1}) + "\n")
        r = self.bakim()
        self.assertEqual([g["id"] for g in r["terk_isler"]], [terk])
        self.assertEqual(r["terk_isler"][0]["saat_esigi"], 24)

    def test_sure_ayardan_gelir(self):  # K2: süre is_esleme.json terk_is_saat
        i, _ = self.is_ac("001-terk", eski_saat=30)
        self.proje_ayari(terk_is_saat=40)
        self.assertEqual(self.bakim()["terk_isler"], [])
        self.proje_ayari(terk_is_saat=10)
        self.assertEqual([g["id"] for g in self.bakim()["terk_isler"]], [i])

    def test_eklenti_ayari_varsayilan_24(self):  # K2
        with open(os.path.join(KOK, "ayarlar", "is_esleme.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["terk_is_saat"], 24)

    def test_kapat_uygula_terk_isi_kapatir_kuru_kapatmaz(self):  # K2: mevcut --kapat --uygula yolu
        self.proje_ayari(terk_is_saat=10)
        i, _ = self.is_ac("001-terk", eski_saat=12)  # bos_saat 24'ün altında: yalnız terk yolu kapatır
        self.bakim("--kapat")
        self.assertEqual(self.merkez()["isler"][i]["durum"], "acik")
        r = self.bakim("--uygula", "--kapat")
        self.assertIn(i, r["kapatilan_is"])
        self.assertEqual(self.merkez()["isler"][i]["durum"], "kapandi")

    def test_olu_yol_terk_sayilmaz(self):
        i, klasor = self.is_ac("001-olu", eski_saat=30)
        shutil.rmtree(klasor)
        self.assertNotIn(i, [g["id"] for g in self.bakim()["terk_isler"]])


class SoruIsAcmaz(unittest.TestCase):
    """K3: mevcut sınıflayıcı (soru_sinif.tur) + hook._otomatik_yonlendirme 'ac' dalı (I-138 P2)."""

    def setUp(self):
        import tempfile
        self.proje = tempfile.mkdtemp(prefix="ork_soru_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)

    def test_soru_turu_mesaj_is_acmaz_is_turu_acar(self):
        import hook
        import is_kaydi
        import soru_sinif
        soru = "Bu fatura raporu neden boş geliyor?"
        self.assertEqual(soru_sinif.tur(soru, self.sd), "soru")
        self.assertEqual(hook._otomatik_yonlendirme(self.sd, "soru-oturum-1", soru, cwd=self.proje), "")
        self.assertEqual(is_kaydi.is_liste(self.sd, "acik"), [])
        is_mesaji = "kuantum gitar akort uygulaması yaz ve test et"
        self.assertEqual(soru_sinif.tur(is_mesaji, self.sd), "is")
        m = hook._otomatik_yonlendirme(self.sd, "soru-oturum-2", is_mesaji, cwd=self.proje)
        self.assertIn("Yeni iş otomatik açıldı", m)
        self.assertEqual(len(is_kaydi.is_liste(self.sd, "acik")), 1)


class GecisMesaji(_Taban):
    def test_is_devam_gecis_satiri_kimlik_ve_baslik_basar(self):  # K4: mevcut is devam başlık satırı
        a, _ = self.is_ac("001-birinci", eski_saat=1)
        b, _ = self.is_ac("002-ikinci", eski_saat=1)
        self.cli("is", "devam", a)
        r = self.cli("is", "devam", b)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.splitlines()[0].startswith(f"{b} — Otomatik iş 002-ikinci"), r.stdout)


if __name__ == "__main__":
    unittest.main()
