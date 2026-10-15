"""calistir.js: kapı zaman aşımı sınıfı (G-046 K2) ve ajan sonuç döndürmediğinde davranış (K3).

`py -3.13 -m pytest plugins/orkestra/tests/test_calistir_kapi_zaman.py -q`

Kapı artık `kart durum is-bitti` içinde (CLI) koşar; ayrı kapı ajanı ve `--zaman-asimi` bayrağı istemi yoktur (K1 kalktı).
Test yazarı / işçi sonucu `kapi`, `kapi_cikis`, `kapi_ozeti` ile bildirir. Sahte çalışma zamanı
test_calistir_akisi.KOSUM_JS'tir: kirmizi / yesil senaryo girdileri {gecti, cikis_kodu, ozet, cikti_kuyrugu}
(null = ajan sonuç döndürmedi). node yoksa testler FAIL olur (skip yok).
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from test_calistir_akisi import BETIK, KOSUM_JS, NODE, NODE_YOK_GEREKCE, kod_karti


def kapi(cikis, ozet, gecti=False, kuyruk=""):
    return {"gecti": gecti, "cikis_kodu": cikis, "ozet": ozet, "cikti_kuyrugu": kuyruk}


def zaman_asimi_kapisi():
    return kapi(-1, "orkestra: test_komutu zaman aşımına uğradı (600 sn)")


class KapiZamanTabani(unittest.TestCase):
    def setUp(self):
        if not NODE:  # skip yok: node'suz koşu kırmızı/yeşil için geçersizdir
            self.fail(NODE_YOK_GEREKCE)
        self.tmp = tempfile.mkdtemp(prefix="ork_kapi_zaman_")
        self.kosum = os.path.join(self.tmp, "kosum.js")
        with open(self.kosum, "w", encoding="utf-8") as f:
            f.write(KOSUM_JS)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def kos(self, kart=None, **senaryo):
        yol = os.path.join(self.tmp, "senaryo.json")
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(dict(senaryo, gorevler=[kart or kod_karti()]), f, ensure_ascii=False)
        env = dict(os.environ, ELECTRON_RUN_AS_NODE="1")
        p = subprocess.run([NODE, self.kosum, BETIK, yol], capture_output=True, env=env, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr.decode("utf-8", "replace"))
        c = json.loads(p.stdout.decode("utf-8"))
        self.assertEqual([x for x in c["cagrilar"] if x["phase"] in ("Kapı", "Ön kontrol")], [])
        return c["sonuc"]["sonuclar"][0], c["cagrilar"]

    @staticmethod
    def say(cagrilar, **ol):
        return len([c for c in cagrilar if all(c.get(a) == d for a, d in ol.items())])


class ZamanAsimiSinifi(KapiZamanTabani):
    """K2"""

    def dogrula_sinif(self, s):
        self.assertEqual(s["durum"], "kart-duzeltilmeli")
        self.assertEqual(s["neden"], "kapi-zaman-asimi")
        self.assertEqual(s["basamak"], "T2")
        metin = json.dumps(s, ensure_ascii=False)
        self.assertIn("test_komutu", metin)  # düzeltme talimatı
        self.assertIn("zaman-asimi", json.dumps(s.get("gecmis", []), ensure_ascii=False),
                      "gecmis kaydında karar 'zaman-asimi' yok: " + metin)

    def test_k2_kirmizi_kapi_cikis_eksi1(self):
        s, c = self.kos(kirmizi=[zaman_asimi_kapisi()] * 10)
        self.dogrula_sinif(s)
        self.assertEqual(self.say(c, agentType="orkestra:test-yazari"), 1)  # yeniden deneme yok
        self.assertEqual(self.say(c, phase="İş"), 0)
        self.assertEqual(self.say(c, phase="Denetim"), 0)

    def test_k2_yesil_kapi_cikis_eksi1(self):
        s, c = self.kos(yesil=[zaman_asimi_kapisi()] * 30)
        self.dogrula_sinif(s)
        self.assertEqual([x["agentType"] for x in c if x["phase"] == "İş"], ["orkestra:isci-t2"])
        self.assertEqual(self.say(c, phase="Denetim"), 0)
        self.assertIn("yesil", [g.get("asama") for g in s["gecmis"]])

    def test_k2_yukselt_cagrilmaz(self):
        s, c = self.kos(yesil=[zaman_asimi_kapisi()] * 30)
        self.assertEqual([x for x in c if x["agentType"] in ("orkestra:isci-t3", "orkestra:isci-t4")], [])
        self.assertNotEqual(s["durum"], "reddedildi")

    def test_k2_kuyrukta_orkestra_onekli_zaman_asimi_satiri(self):
        kuyruk = "1 passed\norkestra: komut zaman aşımına uğradı (600 sn)"
        for cikis in (1, 4):
            with self.subTest(cikis=cikis, asama="kirmizi"):
                s, c = self.kos(kirmizi=[kapi(cikis, "kapı geçmedi", kuyruk=kuyruk)] * 10)
                self.dogrula_sinif(s)
                self.assertEqual(self.say(c, agentType="orkestra:test-yazari"), 1)
            with self.subTest(cikis=cikis, asama="yesil"):
                s, c = self.kos(yesil=[kapi(cikis, "kapı geçmedi", kuyruk=kuyruk)] * 30)
                self.dogrula_sinif(s)
                self.assertEqual(self.say(c, phase="İş"), 1)

    # Bilinen açık: yeni sözleşmede ozet = kapi_ozeti = çıktının son 30 satırı olduğundan kapiZamanAsimiMi
    # ozet'in TAMAMINDA 'zaman aşımı' arar (çıkış koduna bakmadan); pytest satırındaki metin (önek yok,
    # çıkış 4 = gerçek test başarısızlığı) zaman aşımı sanılır.
    def test_k2_onekli_olmayan_zaman_asimi_metni_sinifa_girmez(self):
        # pytest çıktısındaki 'zaman aşımı' geçen satır (önek yok) gerçek test başarısızlığıdır
        kuyruk = "E   AssertionError: zaman aşımı bekleniyordu\n1 failed"
        s, c = self.kos(yesil=[kapi(4, "yesil False", kuyruk=kuyruk)] * 30)
        self.assertNotEqual(s.get("neden"), "kapi-zaman-asimi")
        self.assertEqual(s["durum"], "reddedildi")

    def test_k2_gercek_basarisizlik_eski_akis(self):
        s, c = self.kos(kirmizi=[kapi(4, "kırmızı False")] * 10)
        self.assertEqual(s["durum"], "reddedildi")
        self.assertEqual(s["neden"], "kirmizi-teyit")
        self.assertEqual(self.say(c, agentType="orkestra:test-yazari"), 3)

    def test_k2_zaman_asimindan_sonra_gecen_sonuc_beklenmez(self):
        s, c = self.kos(kirmizi=[zaman_asimi_kapisi(), kapi(0, "ok", gecti=True)])
        self.assertEqual(s["durum"], "kart-duzeltilmeli")
        self.assertEqual(self.say(c, agentType="orkestra:test-yazari"), 1)


class AjanSonucYok(KapiZamanTabani):
    """K3: ajan sonuç döndürmezse (null) kart 'hata' ile durur; zaman aşımı sınıfına girmez."""

    def test_k3_test_yazari_sonuc_yok(self):
        s, c = self.kos(kirmizi=[None] * 10)
        self.assertEqual(s["durum"], "hata")
        self.assertNotEqual(s.get("neden"), "kapi-zaman-asimi")
        self.assertEqual(self.say(c, agentType="orkestra:test-yazari"), 1)
        self.assertEqual(self.say(c, phase="İş"), 0)

    def test_k3_isci_sonuc_yok(self):
        s, c = self.kos(yesil=[None] * 30)
        self.assertEqual(s["durum"], "hata")
        self.assertNotEqual(s.get("neden"), "kapi-zaman-asimi")
        self.assertEqual(self.say(c, phase="İş"), 1)
        self.assertEqual(self.say(c, phase="Denetim"), 0)


if __name__ == "__main__":
    unittest.main()
