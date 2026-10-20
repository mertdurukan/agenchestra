"""ADR-0009: /plan ve /auto çalışma modları. Hepsi geçici projede koşar."""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_is_onay import OTURUM, _Onay, hook, is_kaydi, is_onay  # noqa: E402

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
from komutlar import isler  # noqa: E402


class ModYazimi(_Onay):
    def mod(self):
        return is_kaydi.is_al(self.sd, self.kayit["id"]).get("mod")

    def test_auto_mesaji_mod_yazar(self):
        self.mesaj("/auto bu işi bitir")
        self.assertEqual(self.mod(), "auto")

    def test_plan_mesaji_mod_yazar(self):
        self.mesaj("/auto x")
        self.mesaj("/plan x")
        self.assertEqual(self.mod(), "plan")

    def test_alansiz_is_plan_sayilir(self):
        self.assertEqual(is_onay.mod(is_kaydi.is_al(self.sd, self.kayit["id"])), "plan")

    def test_sozcuk_ortasi_mod_degil(self):
        self.assertIsNone(is_onay.mod_mesaji("autopilot kur"))
        self.assertIsNone(is_onay.mod_mesaji("bu /auto değil"))

    def test_kapi_kapaliyken_mod_yok(self):
        os.environ["ORKESTRA_MOD_KAPISI"] = "0"
        self.assertIsNone(is_onay.mod_mesaji("/auto x"))

    def test_bekleyen_mod_is_baglaninca_uygulanir(self):
        is_onay.bekleyen_mod_yaz(self.sd, "yeni-oturum", "auto")
        is_kaydi.is_oturum_bagla(self.sd, self.kayit["id"], "yeni-oturum")
        self.assertEqual(self.mod(), "auto")
        self.assertIsNone(is_onay.bekleyen_mod_al(self.sd, "yeni-oturum"))


class OtomatikOnay(_Onay):
    def auto_yap(self):
        self.mesaj("/auto devam")

    def test_auto_belgeler_hazirsa_onay_kendiliginden(self):
        self.auto_yap()
        with mock.patch.object(is_onay, "belge_eksikleri", return_value=[]):
            self.assertFalse(self.pre("Write", self.kod())[0])
        self.assertEqual(self.durum(), "verildi")
        olaylar = [g["olay"] for g in is_kaydi.is_al(self.sd, self.kayit["id"])["gecmis"]]
        self.assertIn("onay:auto", olaylar)

    def test_auto_belgeler_eksikse_yazma_reddedilir(self):
        self.auto_yap()
        self.assertTrue(self.pre("Write", self.kod())[0])
        self.assertEqual(self.durum(), "bekliyor")

    def test_plan_modunda_belgeler_hazir_olsa_da_bekler(self):
        self.mesaj("/plan x")
        with mock.patch.object(is_onay, "belge_eksikleri", return_value=[]):
            self.assertTrue(self.pre("Write", self.kod())[0])
        self.assertEqual(self.durum(), "bekliyor")

    def test_auto_altinda_ajan_onayla_calistiramaz(self):
        self.auto_yap()
        self.assertTrue(self.pre("Bash", komut="orkestra is onayla I-001")[0])

    def test_auto_altinda_is_json_yazilamaz(self):
        self.auto_yap()
        self.assertTrue(self.pre("Write", os.path.join(self.klasor, "is.json"))[0])
        self.assertTrue(self.pre("Bash", komut="echo '{}' > " + os.path.join(self.klasor, "is.json"))[0])

    def test_auto_onayi_commit_kapisini_gevsetmez_belge_eksikken(self):
        self.auto_yap()
        self.assertTrue(self.pre("Bash", komut="git commit -m x")[0])


class AutoOzet(_Onay):
    def yaz_is(self, mod):
        yol = os.path.join(self.klasor, "is.json")
        with open(yol, encoding="utf-8") as f:
            k = json.load(f)
        if mod:
            k["mod"] = mod
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(k, f)

    def test_auto_bolum_eksikse_ret(self):
        self.yaz_is("auto")
        self.assertIn("Plandan sapmalar", isler._auto_ozet_eksigi(self.klasor, "## Özet\nx\n"))

    def test_auto_bolum_bosken_ret(self):
        self.yaz_is("auto")
        metin = "## Plandan sapmalar\n\n## Kullanıcıya kalanlar\nYok\n"
        self.assertIn("Plandan sapmalar", isler._auto_ozet_eksigi(self.klasor, metin))

    def test_auto_bolumler_dolu_gecer(self):
        self.yaz_is("auto")
        metin = "## Plandan sapmalar\nYok\n\n## Kullanıcıya kalanlar\nYok\n"
        self.assertIsNone(isler._auto_ozet_eksigi(self.klasor, metin))

    def test_plan_modunda_bolum_istenmez(self):
        self.yaz_is(None)
        self.assertIsNone(isler._auto_ozet_eksigi(self.klasor, "## Özet\nx\n"))


if __name__ == "__main__":
    unittest.main()
