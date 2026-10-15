"""Sohbet başına 'Kapatılabilir' rozeti: niyet.gorunum() satırlarındaki `kapanis` alanı ve isler.html çizimi.

`py -3.13 -m pytest plugins/orkestra/tests/test_kapanis_rozeti.py -q -p no:cacheprovider`
Gerçek niyet.jsonl'a dokunmaz; proje geçici klasördür (NIYET_YOLU ve _gecici yamalı).
"""
import datetime
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import is_kaydi as IK  # noqa: E402
import niyet  # noqa: E402

OTURUM = "oturum-kapanis-1"
DIGER = "oturum-baska-2"


def _z(dk_once: float) -> str:
    return (datetime.datetime.now().astimezone() - datetime.timedelta(minutes=dk_once)).isoformat(timespec="seconds")


def _ts(dk_once: float) -> float:
    return (datetime.datetime.now() - datetime.timedelta(minutes=dk_once)).timestamp()


class KapanisTemel(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="kapanis_")
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)
        self.proje = os.path.join(self.d, "proje")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "gorevler"), exist_ok=True)
        os.makedirs(os.path.join(self.sd, "oturumlar"), exist_ok=True)
        self.niyet_yolu = os.path.join(self.d, "niyet.jsonl")

    # ------------------------------------------------------------ yardımcılar
    def _is_ac(self, ad="Deneme işi"):
        klasor = os.path.join(self.d, "isler", "001-deneme")
        kayit = IK.is_ac(self.sd, ad, klasor)
        return kayit["id"], klasor

    def _kart(self, gid, durum, is_id=None, oturum=OTURUM):
        k = {"id": gid, "baslik": f"kart {gid}", "sinif": "kod", "durum": durum, "oturum": oturum, "gecmis": [], "v": 1}
        if is_id:
            k["is"] = is_id
        with open(os.path.join(self.sd, "gorevler", gid + ".json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(k, f, ensure_ascii=False)

    def _ajan(self, ad, ajan, oturum=OTURUM):
        with open(os.path.join(self.sd, "oturumlar", f"acik_ajan_{ad}.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump({"oturum": oturum, "ajan": ajan, "baslangic": _z(5)}, f)

    def _todo_mtime(self, klasor, dk_once):
        for ad in os.listdir(klasor):
            if ad.lower() == "todo.md":
                t = _ts(dk_once)
                os.utime(os.path.join(klasor, ad), (t, t))
                return
        self.fail("todo.md yok")

    def _gorunum(self, olaylar, oturum=OTURUM):
        """olaylar: [(dk_once, tur, ekstra)] → oturumun satırı."""
        with open(self.niyet_yolu, "w", encoding="utf-8") as f:
            for dk, tur, ek in olaylar:
                f.write(json.dumps({"zaman": _z(dk), "oturum": oturum, "proje": self.proje, "tur": tur, **ek}) + "\n")
        with mock.patch.object(niyet, "NIYET_YOLU", self.niyet_yolu), \
                mock.patch.object(niyet, "_gecici", return_value=False), \
                mock.patch.object(niyet, "masaustu_oturumlari", return_value={}), \
                mock.patch.object(niyet, "_basliklar", return_value={}), \
                mock.patch.object(niyet, "_gunluk_istekleri", return_value=[]), \
                mock.patch.object(niyet.L, "calisma_alanlari", return_value=[], create=True):
            g = niyet.gorunum()
        satir = [r for r in g["oturumlar"] if r["oturum"] == oturum]
        self.assertEqual(len(satir), 1, g["oturumlar"])
        return satir[0]

    # tur bitmiş, niyet + sonuç yazılmış sohbet (bekleyen=bitti), son_zaman ~40 dk önce
    SAKIN = [(60, "istek", {"metin": "iş"}), (59, "niyet", {"ne": "bir şey yap", "neden": "çünkü"}),
             (50, "tur", {}), (40, "sonuc", {"sonuc": "yapıldı"})]

    def _eksik(self, satir):
        self.assertIn("kapanis", satir)
        self.assertIsInstance(satir["kapanis"]["kapatilabilir"], bool)
        self.assertIsInstance(satir["kapanis"]["eksik"], list)
        return " | ".join(satir["kapanis"]["eksik"])


class KapanisKosullari(KapanisTemel):
    def test_sonuctan_sonra_yeni_istek_bitti_sayilmaz(self):
        s = self._gorunum(self.SAKIN + [(5, "istek", {"metin": "önerinle yap"})])
        self.assertEqual(s["bekleyen"], "claude")
        self.assertIn("Claude çalışıyor", s["kapanis"]["eksik"])

    def test_yeni_istekten_sonra_sonuc_yazilirsa_bitti(self):
        s = self._gorunum(self.SAKIN + [(5, "istek", {"metin": "önerinle yap"}), (1, "sonuc", {"sonuc": "tamam"})])
        self.assertEqual(s["bekleyen"], "bitti")

    def test_hepsi_saglaninca_kapatilabilir(self):
        is_id, klasor = self._is_ac()
        self._kart("G-001", "teslim", is_id)
        self._todo_mtime(klasor, 10)  # son_zaman (40 dk önce) sonrası güncellenmiş
        s = self._gorunum(self.SAKIN)
        self.assertEqual(self._eksik(s), "")
        self.assertIs(s["kapanis"]["kapatilabilir"], True)
        self.assertEqual(s["kapanis"]["eksik"], [])

    def test_bagli_is_yoksa_todo_kosulu_saglanmis(self):
        s = self._gorunum(self.SAKIN)
        self.assertEqual(s["isler"], [])
        self.assertIs(s["kapanis"]["kapatilabilir"], True)
        self.assertEqual(s["kapanis"]["eksik"], [])

    def test_acik_kart_eksik_ve_sayi(self):
        is_id, klasor = self._is_ac()
        self._kart("G-001", "isleniyor", is_id)
        self._kart("G-002", "denetimde", is_id)
        self._kart("G-003", "teslim", is_id)  # kapalı: sayılmaz
        self._todo_mtime(klasor, 10)
        s = self._gorunum(self.SAKIN)
        e = self._eksik(s)
        self.assertIs(s["kapanis"]["kapatilabilir"], False)
        self.assertTrue(any("açık kart" in m and "2" in m for m in s["kapanis"]["eksik"]), e)

    def test_tek_acik_kart_reddedildi_da_sayilir(self):
        is_id, klasor = self._is_ac()
        self._kart("G-001", "reddedildi", is_id)
        self._todo_mtime(klasor, 10)
        s = self._gorunum(self.SAKIN)
        self.assertTrue(any("açık kart" in m and "1" in m for m in s["kapanis"]["eksik"]), self._eksik(s))
        self.assertIs(s["kapanis"]["kapatilabilir"], False)

    def test_kapali_kartlar_acik_kart_eksigi_uretmez(self):
        is_id, klasor = self._is_ac()
        self._kart("G-001", "teslim", is_id)
        self._kart("G-002", "iptal", is_id)
        self._todo_mtime(klasor, 10)
        s = self._gorunum(self.SAKIN)
        self.assertNotIn("açık kart", self._eksik(s))

    def test_denetci_ajani_suruyor(self):
        self._ajan("a1", "orkestra:denetci")
        s = self._gorunum(self.SAKIN)
        self.assertIn("denetçi sürüyor", s["kapanis"]["eksik"])
        self.assertNotIn("alt ajan sürüyor", self._eksik(s))
        self.assertIs(s["kapanis"]["kapatilabilir"], False)

    def test_diger_ajan_alt_ajan_suruyor(self):
        self._ajan("a2", "orkestra:isci-t2")
        s = self._gorunum(self.SAKIN)
        self.assertIn("alt ajan sürüyor", s["kapanis"]["eksik"])
        self.assertNotIn("denetçi sürüyor", self._eksik(s))
        self.assertIs(s["kapanis"]["kapatilabilir"], False)

    def test_baska_oturumun_ajan_kaydi_sayilmaz(self):
        self._ajan("a3", "orkestra:denetci", oturum=DIGER)
        s = self._gorunum(self.SAKIN)
        self.assertEqual(self._eksik(s), "")
        self.assertIs(s["kapanis"]["kapatilabilir"], True)

    def test_sonuc_yok(self):
        s = self._gorunum([(60, "istek", {"metin": "iş"}), (59, "niyet", {"ne": "x", "neden": "y"}), (50, "tur", {})])
        self.assertIn("niyet sonucu yok", s["kapanis"]["eksik"])
        self.assertIs(s["kapanis"]["kapatilabilir"], False)

    def test_sonuc_bos_metin_sayilir_yok(self):
        s = self._gorunum([(60, "istek", {"metin": "iş"}), (59, "niyet", {"ne": "x"}), (50, "tur", {}),
                           (40, "sonuc", {"sonuc": ""})])
        self.assertIn("niyet sonucu yok", s["kapanis"]["eksik"])
        self.assertIs(s["kapanis"]["kapatilabilir"], False)

    def test_todo_eski_ise_eksik(self):
        is_id, klasor = self._is_ac()
        self._kart("G-001", "teslim", is_id)
        self._todo_mtime(klasor, 300)  # son_zaman'dan (40 dk önce) eski
        s = self._gorunum(self.SAKIN)
        self.assertIn(f"todo güncel değil ({is_id})", s["kapanis"]["eksik"])
        self.assertIs(s["kapanis"]["kapatilabilir"], False)

    def test_todo_guncel_ise_eksik_yok(self):
        is_id, klasor = self._is_ac()
        self._kart("G-001", "teslim", is_id)
        self._todo_mtime(klasor, 1)
        s = self._gorunum(self.SAKIN)
        self.assertNotIn("todo güncel değil", self._eksik(s))

    def test_todo_buyuk_harf_dosya_adi(self):
        is_id, klasor = self._is_ac()
        self._kart("G-001", "teslim", is_id)
        eski, yeni = os.path.join(klasor, "todo.md"), os.path.join(klasor, "TODO.md")
        os.rename(eski, yeni)
        t = _ts(300)
        os.utime(yeni, (t, t))
        s = self._gorunum(self.SAKIN)
        self.assertIn(f"todo güncel değil ({is_id})", s["kapanis"]["eksik"])

    def test_claude_calisiyor(self):
        s = self._gorunum([(5, "tur", {}), (2, "istek", {"metin": "devam"})])
        self.assertEqual(s["bekleyen"], "claude")
        self.assertIn("Claude çalışıyor", s["kapanis"]["eksik"])
        self.assertIs(s["kapanis"]["kapatilabilir"], False)

    def test_birden_cok_eksik_birlikte(self):
        is_id, klasor = self._is_ac()
        self._kart("G-001", "isleniyor", is_id)
        self._todo_mtime(klasor, 300)
        self._ajan("a4", "orkestra:denetci")
        s = self._gorunum([(60, "istek", {"metin": "iş"}), (59, "niyet", {"ne": "x"}), (50, "tur", {})])
        e = s["kapanis"]["eksik"]
        self.assertGreaterEqual(len(e), 4, e)
        self.assertTrue(all(isinstance(m, str) and 0 < len(m) <= 40 for m in e), e)  # kısa metin

    def test_kapandi_sohbette_kapanis_alani_yok(self):
        s = self._gorunum([(60, "istek", {"metin": "iş"}), (50, "tur", {}), (40, "kapandi", {})])
        self.assertEqual(s["bekleyen"], "kapandi")
        self.assertNotIn("kapanis", s)


class IslerHtmlKapanis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(KOK, "assets", "isler.html"), encoding="utf-8") as f:
            cls.html = f.read()
        m = re.search(r"function sohbetKarti\(r\)\s*\{", cls.html)
        assert m, "sohbetKarti bulunamadı"
        bas, derin, i = m.end(), 1, m.end()
        while derin and i < len(cls.html):
            derin += {"{": 1, "}": -1}.get(cls.html[i], 0)
            i += 1
        cls.govde = cls.html[bas:i]

    def test_sohbet_karti_kapanis_kullanir(self):
        self.assertIn("kapanis", self.govde)
        self.assertIn("kapatilabilir", self.govde)

    def test_kapatilabilir_rozeti_metni(self):
        self.assertIn("Kapatılabilir", self.govde)

    def test_eksikler_cizilir(self):
        self.assertRegex(self.govde, r"kapanis\W+eksik|\.eksik")
        self.assertRegex(self.govde, r"eksik[^;]*\.map\(|dizi\([^)]*eksik")

    def test_kapanis_yoksa_cizim_cokmez(self):
        # kapanis alanı olmayan (kapandi) satırda güvenli erişim: doğrudan r.kapanis.xxx kullanılmamalı
        self.assertNotRegex(self.govde, r"r\.kapanis\.(kapatilabilir|eksik)")

    def test_html_eksik_metin_kacisli(self):
        # eksik metinleri esc()/metin() ile basılmalı
        self.assertRegex(self.govde, r"(esc|metin)\([^;\n]*eksik|eksik[^;\n]*(esc|metin)\(")


if __name__ == "__main__":
    unittest.main()
