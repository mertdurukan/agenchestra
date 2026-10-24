"""ork_lib.maskele: kapatma bayrağı / tanımlayıcı korunur, gerçek sır biçimleri maskelenir (I-224 P3a).

Kök neden: _UZUN_ANAHTAR karakter sınıfı '=' içeriyordu; 'ORKESTRA_..._KAPISI=0' ad + '=0' ile tek
32+ karakterlik belirteç oluyor, rakam koşulunu '0' sağlıyor ve tamamı <gizli-anahtar> oluyordu.
"""
import os
import sys
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import ork_lib as L  # noqa: E402


class TanimlayiciKorunur(unittest.TestCase):
    def test_kapatma_bayragi_metni_degismez(self):
        metin = ("Zorlama: is_sirasi.paralellik_eksikleri; ORKESTRA_PARALELLIK_KAPISI=0 ve "
                 "ORKESTRA_PARALELLIK_KAPANIS_KAPISI=0 kapatır. (ADR-0080) (P-035, 2026-10-24)")
        self.assertEqual(L.maskele(metin), metin)

    def test_uzun_ortam_degiskeni_adlari(self):
        for ad in ("ORKESTRA_KALITE_KAPISI_V2_GOLGE_MODU=1", "ORKESTRA_HAFIZA_DUZELTME_ESIGI_2026=0",
                   "ORKESTRA_SECIM_EKRANI_HATIRLATMA_BLOK2"):
            self.assertEqual(L.maskele(ad), ad)

    def test_snake_case_ve_yol(self):
        for s in ("test_uretim_noktasi_kapisi_2026_10_24_golge", "plugins/orkestra/tests/test_ork_lib_maske2.py",
                  "kapi_golge_ret_sayaci_v3_ilk_30_plan", "129-20261024-orkestra-denetimleri-kok-neden-analizi"):
            self.assertEqual(L.maskele(s), s)


class GercekSirMaskelenir(unittest.TestCase):
    # Değerler sahte; tarayıcılar yakalamasın diye parçalı kurulur.
    ORNEKLER = [
        "sk-ant-api03-" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        "sk-" + "proj-Xy7Qw2Lk9Tz4Rb6Nm1Pv8Hs3Jd5Fc0Ga",
        "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8",
        "github_pat_" + "11ABCDEFG0aBcDeFgHiJkL_mNoPqRsTuVwXyZ0123456789abcdefABCDEF",
        "AKIA" + "IOSFODNN7EXAMPLE",
        "xoxb-" + "123456789012-1234567890123-AbCdEfGhIjKlMnOp",
        "dGhpcyBpcyBhIHNlY3JldCB2YWx1ZSBmb3IgdGVzdA" + "==",   # base64, dolgulu
        "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",  # hex
        "AbC9dEf8GhI7jKl6MnO5pQr4StU3vWx2YzA1",              # karışık rastgele
    ]

    def test_token_bicimleri_maskelenir(self):
        for sir in self.ORNEKLER:
            cikti = L.maskele(f"anahtar {sir} sızdı")
            self.assertNotIn(sir, cikti, sir[:6])
            self.assertIn("<gizli-anahtar>", cikti)

    def test_bayrak_yaninda_sir_yine_maskelenir(self):
        sir = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
        cikti = L.maskele(f"ORKESTRA_URETIM_KAPISI=0 ve {sir}")
        self.assertIn("ORKESTRA_URETIM_KAPISI=0", cikti)
        self.assertNotIn(sir, cikti)

    def test_anahtar_deger_bearer_postgres_eposta(self):
        cikti = L.maskele("password: Gizli123! Bearer abcdEFGH1234ijkl postgres://u:Pw9x@h/db a.b@c.com")
        for sir in ("Gizli123!", "abcdEFGH1234ijkl", "Pw9x", "a.b@c.com"):
            self.assertNotIn(sir, cikti)


if __name__ == "__main__":
    unittest.main()


class AltCizgiliOnek(unittest.TestCase):
    def test_stripe_tarzi_anahtar_maskelenir(self):
        # I-224 denetçi kusuru 2: sk_live_ öneki sk- listesinde yoktu
        self.assertNotIn("abcdefghijklmnop1234", L.maskele("anahtar sk_live_abcdefghijklmnop1234 bitti"))
