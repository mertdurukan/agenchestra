"""Sohbet konu defteri çekirdeği (ADR-0115): yazım, sayım, örtüşme, aday, rapor, maskeleme, paralel ekleme."""
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import konu_defteri as KD  # noqa: E402
import ork_lib as L  # noqa: E402

ZAMAN_RE = r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d$"
ILK = "konu defteri hook testleri yazalım hemen şimdi"
DEVAM = "konu defteri hook testleri için bir senaryo daha ekle şimdi"
FARKLI = "yarınki toplantı için sunum slaytlarını hazırla ve müşteriye gönder lütfen"


class KonuDefteri(unittest.TestCase):
    def setUp(self):
        self.sd = tempfile.mkdtemp(prefix="ork_konu_")
        self.an = datetime.datetime(2026, 10, 31, 10, 0, 0).astimezone()

    def tearDown(self):
        shutil.rmtree(self.sd, ignore_errors=True)

    def saat(self, dk):
        return mock.patch.object(L, "simdi", lambda: (self.an + datetime.timedelta(minutes=dk)).isoformat(timespec="seconds"))

    def test_ac_saniyeli_zaman_ve_alanlar(self):
        self.assertEqual(KD.ac(self.sd, "o1", "Konu defteri tasarımı", kaynak="ajan", neden="takip"), 1)
        k = KD.oku(self.sd)[0]
        self.assertRegex(k["zaman"], ZAMAN_RE)
        self.assertEqual((k["oturum"], k["tur"], k["sira"], k["baslik"], k["kaynak"], k["neden"]),
                         ("o1", "ac", 1, "Konu defteri tasarımı", "ajan", "takip"))

    def test_sira_oturum_basinadir_ve_artar(self):
        KD.ac(self.sd, "o1", "a")
        self.assertEqual(KD.ac(self.sd, "o1", "b"), 2)
        self.assertEqual(KD.ac(self.sd, "o2", "c"), 1)

    def test_baslik_kisalir_ve_sir_maskelenir(self):
        KD.ac(self.sd, "o1", "x " * 200)
        self.assertLessEqual(len(KD.oku(self.sd)[0]["baslik"]), KD.BASLIK_AZAMI)
        sir = "sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        KD.ac(self.sd, "o2", f"anahtar {sir} kullan")
        self.assertNotIn(sir, json.dumps(KD.oku(self.sd), ensure_ascii=False))

    def test_tur_say_konu_yoksa_none(self):
        self.assertIsNone(KD.tur_say(self.sd, "o1", "merhaba"))
        KD.ac(self.sd, "o1", "a")
        self.assertEqual(KD.tur_say(self.sd, "o1", "merhaba"), 1)

    def test_ozet_tur_ve_sure(self):
        with self.saat(0):
            KD.ac(self.sd, "o1", "a")
            KD.tur_say(self.sd, "o1", "x")
        with self.saat(5):
            KD.tur_say(self.sd, "o1", "y")
        with self.saat(20):
            KD.ac(self.sd, "o1", "b")
            KD.tur_say(self.sd, "o1", "z")
        oz = KD.oturum_ozeti(KD.oku(self.sd))
        self.assertEqual([(c["sira"], c["tur"], c["sure_sn"]) for c in oz], [(1, 2, 300), (2, 1, 0)])

    def test_ortusme_kisa_ve_onay_muaf(self):
        self.assertIsNone(KD.ortusme("tamam", "konu defteri"))
        self.assertIsNone(KD.ortusme("evet yap", "konu defteri"))
        self.assertIsNone(KD.ortusme("şunu bir de bak", "konu defteri"))

    def test_ortusme_ayni_ve_farkli_konu(self):
        konu = "orkestra konu defteri hook testleri yazılıyor"
        yuksek = KD.ortusme("konu defteri hook testleri için yeni senaryo ekle ve çalıştır", konu)
        dusuk = KD.ortusme(FARKLI, konu)
        self.assertGreater(yuksek, KD.VARSAYILAN["ortusme_esigi"])
        self.assertLess(dusuk, KD.VARSAYILAN["ortusme_esigi"])

    def test_hook_ilk_istek_konu_acar_aday_yok(self):
        self.assertEqual(KD.hook_istek(self.sd, "o1", ILK), "")
        ol = KD.oku(self.sd)
        self.assertEqual([k["tur"] for k in ol], ["ac", "tur"])
        self.assertEqual(ol[0]["kaynak"], "hook")

    def test_hook_sistem_iletisi_sayilmaz(self):
        KD.hook_istek(self.sd, "o1", "<task-notification>bitti</task-notification>")
        self.assertEqual(KD.oku(self.sd), [])

    def test_hook_ortusme_adayi_ve_hatirlatma(self):
        KD.hook_istek(self.sd, "o1", ILK)
        h = KD.hook_istek(self.sd, "o1", FARKLI)
        self.assertIn("orkestra konu ac", h)
        self.assertEqual([x["tip"] for x in KD.oku(self.sd) if x["tur"] == "aday"], ["ortusme"])

    def test_hook_devam_adaysiz(self):
        KD.hook_istek(self.sd, "o1", ILK)
        self.assertEqual(KD.hook_istek(self.sd, "o1", DEVAM), "")
        self.assertFalse([k for k in KD.oku(self.sd) if k["tur"] == "aday"])

    def test_hook_bosluk_adayi(self):
        with self.saat(0):
            KD.hook_istek(self.sd, "o1", ILK)
        with self.saat(75):
            h = KD.hook_istek(self.sd, "o1", DEVAM)
        self.assertIn("bosluk", h)
        self.assertEqual([k["tip"] for k in KD.oku(self.sd) if k["tur"] == "aday"], ["bosluk"])

    def test_ajan_acilisi_adayi_teyit_eder(self):
        KD.hook_istek(self.sd, "o1", ILK)
        KD.hook_istek(self.sd, "o1", FARKLI)
        KD.ac(self.sd, "o1", "Sunum hazırlığı")
        oz = KD.oturum_ozeti(KD.oku(self.sd))
        self.assertEqual([(c["sira"], c["tur"], c["devral"], c["aday_tip"]) for c in oz],
                         [(1, 1, False, None), (2, 1, True, "ortusme")])
        r = KD.rapor([self.sd])
        self.assertEqual(r["gostergeler"]["ortusme"], {"aday": 1, "teyit": 1, "teyit_orani": 1.0})
        self.assertEqual(r["adaysiz_acilis"], 0)

    def test_rapor_sayilari_defterden(self):
        for o, n in (("o1", 1), ("o2", 3), ("o3", 3)):
            for i in range(n):
                KD.ac(self.sd, o, f"k{i}")
        r = KD.rapor([self.sd])
        self.assertEqual((r["sohbet"], r["konu"], r["en_cok"], r["ortalama"]), (3, 7, 3, 2.33))
        self.assertEqual(r["dagilim"], {"1": 1, "2": 0, "3": 2, "4+": 0})
        self.assertEqual(r["adaysiz_acilis"], 4)
        self.assertIn("Sohbet konu raporu", KD.rapor_md(r))

    def test_kapali_bayrak(self):
        with mock.patch.dict(os.environ, {"ORKESTRA_KONU_DEFTERI": "0"}):
            self.assertEqual(KD.hook_istek(self.sd, "o1", ILK), "")
        self.assertEqual(KD.oku(self.sd), [])

    def test_hata_hook_u_dusurmez(self):
        with mock.patch.object(KD, "ac", side_effect=OSError("disk")):
            self.assertEqual(KD.hook_istek(self.sd, "o1", ILK), "")

    def test_stop_golge_bir_kez_yazar(self):
        KD.hook_istek(self.sd, "o1", ILK)
        KD.hook_istek(self.sd, "o1", FARKLI)
        self.assertTrue(KD.stop_kontrol(self.sd, "o1"))
        self.assertFalse(KD.stop_kontrol(self.sd, "o1"))
        g = [json.loads(s) for s in open(os.path.join(self.sd, "gunluk.jsonl"), encoding="utf-8")]
        self.assertEqual([x["kapi"] for x in g if x["tur"] == "kapi_golge"], ["konu_defteri"])
        KD.ac(self.sd, "o1", "Sunum")
        self.assertFalse(KD.stop_kontrol(self.sd, "o1"))

    def test_paralel_ekleme_satir_kaybi_yok(self):
        kod = ("import sys;sys.path.insert(0,sys.argv[1]);import konu_defteri as K\n"
               "for i in range(40): K.aday(sys.argv[2], sys.argv[3], 'ortusme', 0.01)")
        scripts = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
        ps = [subprocess.Popen([sys.executable, "-c", kod, scripts, self.sd, f"p{i}"]) for i in range(3)]
        for p in ps:
            self.assertEqual(p.wait(), 0)
        ol = KD.oku(self.sd)
        self.assertEqual(len(ol), 120)
        self.assertEqual({o: sum(1 for k in ol if k["oturum"] == o) for o in ("p0", "p1", "p2")}, {"p0": 40, "p1": 40, "p2": 40})


if __name__ == "__main__":
    unittest.main()
