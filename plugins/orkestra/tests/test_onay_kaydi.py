"""Tek onay kaydı (ADR-0033): kayıt modülü, oturum izni cümlesi, izin politikasının kayda bakması, deny önceliği."""
import os
import shutil
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import is_onay  # noqa: E402
import izin_politikasi as IP  # noqa: E402
import onay_kaydi as OK  # noqa: E402

OTURUM = "kayit-oturum"


class _Sd(unittest.TestCase):
    def setUp(self):
        self.sd = tempfile.mkdtemp()
        self._ort = os.environ.get("ORKESTRA_IZIN")
        os.environ["ORKESTRA_IZIN"] = "genis"

    def tearDown(self):
        shutil.rmtree(self.sd, ignore_errors=True)
        if self._ort is None:
            os.environ.pop("ORKESTRA_IZIN", None)
        else:
            os.environ["ORKESTRA_IZIN"] = self._ort

    def karar(self, komut, oturum=OTURUM):
        return IP.karar("Bash", {"command": komut}, self.sd, oturum=oturum)


class Kayit(_Sd):
    def test_tur_kaydi_sonraki_mesajda_silinir(self):
        OK.ekle(self.sd, OTURUM, "git", "tur")
        self.assertTrue(OK.var(self.sd, OTURUM, "git"))
        OK.tur_temizle(self.sd, OTURUM)
        self.assertFalse(OK.var(self.sd, OTURUM, "git"))

    def test_oturum_kaydi_kalir(self):
        OK.ekle(self.sd, OTURUM, "git", "oturum")
        OK.tur_temizle(self.sd, OTURUM)
        self.assertTrue(OK.var(self.sd, OTURUM, "git"))

    def test_oturumsuz_kayit_yok(self):
        OK.ekle(self.sd, None, "git", "tur")
        self.assertFalse(OK.var(self.sd, None, "git"))

    def test_baska_oturum_gormez(self):
        OK.ekle(self.sd, OTURUM, "git", "tur")
        self.assertFalse(OK.var(self.sd, "baska", "git"))


class MesajdanKayit(_Sd):
    def test_pushla_tur_kaydi_yazar_sonraki_mesaj_siler(self):
        self.assertTrue(is_onay.git_izni_isle(self.sd, OTURUM, "pushla"))
        self.assertTrue(is_onay.git_izni_var(self.sd, OTURUM))
        self.assertFalse(is_onay.git_izni_isle(self.sd, OTURUM, "tamam"))
        self.assertFalse(is_onay.git_izni_var(self.sd, OTURUM))

    def test_push_serbest_oturum_boyu_kalir(self):
        self.assertTrue(is_onay.git_izni_isle(self.sd, OTURUM, "bu oturumda push serbest"))
        is_onay.git_izni_isle(self.sd, OTURUM, "başka bir mesaj")
        self.assertTrue(is_onay.git_izni_var(self.sd, OTURUM))

    def test_oturum_izni_degil(self):
        for m in ("push serbest mi?", "pushu serbest bırakma", "hayır push serbest değil", "", "x" * 300,
                  "commit mesajı nasıl olmalı"):
            self.assertFalse(is_onay.git_oturum_izni_mi(m), m)


class IzinKarari(_Sd):
    def test_kayit_yokken_secenekli_ask(self):
        k, neden = self.karar("git push origin main")
        self.assertEqual(k, "ask")
        for parca in ("Allow once", "push serbest", "vazgeç"):
            self.assertIn(parca, neden)

    def test_kayit_varken_allow(self):
        OK.ekle(self.sd, OTURUM, "git", "tur")
        for komut in ("git push", "git -C repo push -u origin b", "cd x && git push"):
            self.assertEqual(self.karar(komut)[0], "allow", komut)

    def test_zorla_push_kayda_ragmen_deny(self):
        OK.ekle(self.sd, OTURUM, "git", "oturum")
        for komut in ("git push --force", "git push -f origin main", "git push origin +main", "git push --delete origin b"):
            self.assertEqual(self.karar(komut)[0], "deny", komut)

    def test_diger_kapilar_kayittan_etkilenmez(self):
        OK.ekle(self.sd, OTURUM, "git", "oturum")
        self.assertEqual(self.karar("gh pr merge 5")[0], "ask")

    def test_oturum_verilmezse_ask(self):
        OK.ekle(self.sd, OTURUM, "git", "oturum")
        self.assertEqual(self.karar("git push", oturum=None)[0], "ask")


if __name__ == "__main__":
    unittest.main()
