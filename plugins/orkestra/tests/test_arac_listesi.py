"""I-455: oturumun araç listesini transkriptten okuyan ortak okuyucu (scripts/arac_listesi.py).

Karar üçlüdür: True (var), False (yok), None (bilinmiyor). Yalnız False kapıyı susturur.
"""
import json
import os
import sys
import tempfile
import unittest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import arac_listesi as AL  # noqa: E402

WRAP = "mcp__ccd_turn__wrap_up"


def _shape(*adlar):
    return {"type": "api-request-shape", "shape": {"system": [], "tools": [{"name": a} for a in adlar]}}


def _delta(ekle=(), cikar=(), tekrar=()):
    return {"type": "attachment", "attachment": {
        "type": "deferred_tools_delta", "addedNames": list(ekle), "removedNames": list(cikar),
        "readdedNames": list(tekrar)}}


def _cagri(ad, yan=False):
    return {"type": "assistant", "isSidechain": yan,
            "message": {"content": [{"type": "tool_use", "name": ad, "input": {}}]}}


class Okuyucu(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def _yaz(self, kayitlar, ham=()):
        yol = os.path.join(self.d, "t.jsonl")
        with open(yol, "w", encoding="utf-8") as f:
            for k in kayitlar:
                f.write(json.dumps(k, ensure_ascii=False) + "\n")
            for h in ham:
                f.write(h + "\n")
        return yol

    def test_yuklu_listede_var(self):  # S1
        yol = self._yaz([_shape("Read", WRAP)])
        self.assertTrue(AL.var_mi(yol, "wrap_up"))

    def test_yuklu_listede_yok(self):  # S1
        yol = self._yaz([_shape("Read", "mcp__ccd_turn__update_plan")])
        self.assertFalse(AL.var_mi(yol, "wrap_up"))

    def test_ertelenmiste_var(self):  # S1
        yol = self._yaz([_shape("Read"), _delta(ekle=[WRAP])])
        self.assertTrue(AL.var_mi(yol, "wrap_up"))

    def test_ertelenmisten_cikarilmis(self):  # S1
        yol = self._yaz([_shape("Read"), _delta(ekle=[WRAP]), _delta(cikar=[WRAP])])
        self.assertFalse(AL.var_mi(yol, "wrap_up"))

    def test_silinip_yeniden_eklenen_arac_var(self):  # S1: denetçi bulgusu
        yol = self._yaz([_shape("Read"), _delta(ekle=[WRAP]), _delta(cikar=[WRAP]), _delta(tekrar=[WRAP])])
        self.assertTrue(AL.var_mi(yol, "wrap_up"))

    def test_cagrilmis_arac_var(self):  # S1
        yol = self._yaz([_shape("Read"), _cagri(WRAP)])
        self.assertTrue(AL.var_mi(yol, "wrap_up"))

    def test_alt_ajan_cagrisi_sayilmaz(self):
        yol = self._yaz([_shape("Read"), _cagri(WRAP, yan=True)])
        self.assertFalse(AL.var_mi(yol, "wrap_up"))

    def test_liste_kaydi_yoksa_bilinmiyor(self):  # S1
        yol = self._yaz([{"type": "user", "message": {"content": "merhaba"}}])
        self.assertIsNone(AL.var_mi(yol, "wrap_up"))

    def test_yuklu_liste_gorulmeden_yok_denmez(self):  # S1: yalnız ertelenmiş liste, yüklü liste kaydı yok
        yol = self._yaz([_delta(ekle=["Read"])])
        self.assertIsNone(AL.var_mi(yol, "wrap_up"))
        self.assertTrue(AL.var_mi(yol, "Read"))

    def test_dosya_yok_ya_da_bos_yol_bilinmiyor(self):
        self.assertIsNone(AL.var_mi(os.path.join(self.d, "yok.jsonl"), "wrap_up"))
        self.assertIsNone(AL.var_mi("", "wrap_up"))
        self.assertIsNone(AL.var_mi(None, "wrap_up"))

    def test_bozuk_satir_atlanir(self):
        yol = self._yaz([_shape("Read")], ham=["{bozuk api-request-shape", "deferred_tools_delta ["])
        self.assertFalse(AL.var_mi(yol, "wrap_up"))

    def test_son_liste_oncekini_ezer(self):
        yol = self._yaz([_shape("Read", WRAP), _shape("Read")])
        self.assertFalse(AL.var_mi(yol, "wrap_up"))

    def test_son_ad_parcasiyla_karsilastirir(self):
        yol = self._yaz([_shape("wrap_up")])
        self.assertTrue(AL.var_mi(yol, "mcp__x__wrap_up"))
        self.assertTrue(AL.var_mi(yol, "wrap_up"))
        self.assertFalse(AL.var_mi(yol, "wrap_up_baska"))

    def test_boyut_siniri_asilirsa_bilinmiyor(self):  # S1: denetçi bulgusu
        yol = self._yaz([_shape("Read")])
        eski = AL._SINIR
        AL._SINIR = 10
        try:
            self.assertIsNone(AL.var_mi(yol, "wrap_up"))
        finally:
            AL._SINIR = eski

    def test_buyuk_shape_satiri_okunur(self):  # S1: ~162 KB'lık gerçek satır boyutu
        buyuk = _shape(*(f"arac_{i}" for i in range(3000)), WRAP)
        yol = self._yaz([buyuk])
        self.assertGreater(os.path.getsize(yol), 40_000)
        self.assertTrue(AL.var_mi(yol, "wrap_up"))


if __name__ == "__main__":
    unittest.main()
