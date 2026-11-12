"""I-461/P7: onay bekleyen işte teslim bağlantılarının ilki anlatım; kapanışta anlatım yeniden üretilir."""
import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

import test_muhendislik_kontrol as TM

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import belge_gorunum as BG  # noqa: E402
import is_kaydi as IK  # noqa: E402
from komutlar import isler  # noqa: E402


def _onay_yaz(klasor, onay):
    yol = os.path.join(klasor, "is.json")
    with open(yol, encoding="utf-8") as f:
        k = json.load(f)
    k["onay"] = onay
    with open(yol, "w", encoding="utf-8", newline="\n") as f:
        json.dump(k, f)


class AnlatimBaglantisi(TM.Fikstur):
    def test_onay_bekleyen_iste_ilk_baglanti_anlatim(self):
        k = self.is_kur()
        _onay_yaz(k, "bekliyor")
        s = IK.belge_baglantilari(k, self.proje)
        self.assertTrue(s[0].startswith("anlatım: [00-Anlatim.md]"), s)
        self.assertTrue(os.path.isfile(os.path.join(k, BG.ANLATIM)))
        self.assertEqual(sum(1 for x in s if "00-Anlatim.md" in x), 1, s)

    def test_onayli_iste_sira_degismez(self):
        k = self.is_kur()
        _onay_yaz(k, "verildi")
        s = IK.belge_baglantilari(k, self.proje)
        self.assertTrue(s[0].startswith("mevcut durum:"), s)
        self.assertFalse(any(x.startswith("anlatım:") for x in s), s)
        self.assertFalse(os.path.isfile(os.path.join(k, BG.ANLATIM)))

    def test_bekleyen_iste_imza_kararli(self):
        import is_onay
        k = self.is_kur()
        _onay_yaz(k, "bekliyor")
        i1, s1 = is_onay.teslim_imzasi(k, self.proje)
        time.sleep(1.2)
        i2, s2 = is_onay.teslim_imzasi(k, self.proje)
        self.assertTrue(i1)
        self.assertEqual(i1, i2)
        self.assertEqual(s1, s2)

    def test_kaynak_degisince_anlatim_yeniden_uretilir(self):
        k = self.is_kur()
        _onay_yaz(k, "bekliyor")
        IK.belge_baglantilari(k, self.proje)
        yol = os.path.join(k, BG.ANLATIM)
        with open(yol, "w", encoding="utf-8", newline="\n") as f:
            f.write("ESKI")
        t = os.path.getmtime(yol)
        os.utime(yol, (t, t))
        IK.belge_baglantilari(k, self.proje)
        with open(yol, encoding="utf-8") as f:
            self.assertEqual(f.read(), "ESKI")  # kaynak değişmedi: dokunulmadı
        with open(os.path.join(k, "plan.md"), "a", encoding="utf-8", newline="\n") as f:
            f.write("\n")
        os.utime(os.path.join(k, "plan.md"), (t + 5, t + 5))
        IK.belge_baglantilari(k, self.proje)
        with open(yol, encoding="utf-8") as f:
            self.assertNotEqual(f.read(), "ESKI")


class KapanistaAnlatim(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.sd = os.path.join(self._t.name, "orkestra")
        os.makedirs(self.sd)
        self.klasor = os.path.join(self._t.name, "isler", "001-a")
        IK.is_ac(self.sd, "Deneme", self.klasor, dogrulama=False)

    def _kapat(self):
        with mock.patch.object(isler, "_etki_kapanis"), mock.patch.object(isler, "_edel_kapanis"), \
                mock.patch.object(isler, "_harita_yenile"), mock.patch.object(isler, "_teknik_detay_yaz"), \
                mock.patch.dict(sys.modules, {"dal_temizle": mock.Mock(kapanis=lambda *a: "")}):
            isler.kapat_uygula(self.sd, "I-001", yol="cli")

    def test_kapanista_anlatim_yeniden_yazilir(self):
        yol = os.path.join(self.klasor, BG.ANLATIM)
        with open(yol, "w", encoding="utf-8", newline="\n") as f:
            f.write("ESKI")
        self._kapat()
        with open(yol, encoding="utf-8") as f:
            self.assertNotEqual(f.read(), "ESKI")
        self.assertEqual(IK.is_al(self.sd, "I-001")["durum"], "kapandi")

    def test_uretim_hatasi_kapanisi_engellemez(self):
        with mock.patch.object(BG, "uret", side_effect=RuntimeError("x")):
            self._kapat()
        self.assertEqual(IK.is_al(self.sd, "I-001")["durum"], "kapandi")


if __name__ == "__main__":
    unittest.main()
