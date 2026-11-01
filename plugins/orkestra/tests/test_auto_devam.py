"""/auto tur sonu devam denetimi (ADR-0132): auto + açık iş + özet yok -> gölge kaydı; özet varken ya da auto değilken susar."""
import os
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import auto_devam as AD  # noqa: E402
import is_kaydi  # noqa: E402
import is_onay  # noqa: E402
import izin_politikasi as IP  # noqa: E402
import kapi_mod as KM  # noqa: E402
import ork_lib as L  # noqa: E402

OZET_BOS = "# Özet\n\n**Ne yapıldı?**\n\n<!-- doldur -->\n\n**Ana sayı:**\n"
OZET_DOLU = "# Özet\n\n**Ne yapıldı?**\n\n- skill güncellendi\n\n**Ana sayı:**\n"


class Devam(unittest.TestCase):
    def setUp(self):
        self.klasor = tempfile.mkdtemp()

    def _kos(self, auto=True, durum="acik", mod="golge", stop_aktif=False):
        kayit = {"durum": durum, "klasor": self.klasor}
        with mock.patch.object(IP, "_auto_modu", return_value=auto), \
                mock.patch.object(is_onay, "_bagli_is_id", return_value="I-1"), \
                mock.patch.object(is_kaydi, "is_al", return_value=kayit), \
                mock.patch.object(KM, "mod", return_value=mod), \
                mock.patch.object(KM, "kaydet", return_value=True) as kaydet, \
                mock.patch.object(L, "hook_cikti") as cikti:
            AD.kontrol("sd", "oturum", {"stop_hook_active": stop_aktif})
        return kaydet, cikti

    def _ozet(self, metin):
        with open(os.path.join(self.klasor, "calisma_ozeti_20261101.md"), "w", encoding="utf-8") as f:
            f.write(metin)

    def test_ozet_yok_golgede_kaydeder_engellemez(self):
        kaydet, cikti = self._kos()
        self.assertEqual(kaydet.call_args[0][1], AD.KAPI)
        cikti.assert_not_called()

    def test_bos_sablon_ozet_sayilmaz(self):
        self._ozet(OZET_BOS)
        kaydet, _ = self._kos()
        kaydet.assert_called_once()

    def test_dolu_ozet_susar(self):
        self._ozet(OZET_DOLU)
        kaydet, cikti = self._kos()
        kaydet.assert_not_called()
        cikti.assert_not_called()

    def test_auto_degilse_susar(self):
        kaydet, cikti = self._kos(auto=False)
        kaydet.assert_not_called()
        cikti.assert_not_called()

    def test_kapali_is_susar(self):
        kaydet, _ = self._kos(durum="kapali")
        kaydet.assert_not_called()

    def test_ihlal_modunda_bir_kez_block(self):
        _, cikti = self._kos(mod="ihlal")
        self.assertEqual(cikti.call_args[0][0]["decision"], "block")
        _, cikti2 = self._kos(mod="ihlal", stop_aktif=True)
        cikti2.assert_not_called()

    def test_kapatma_ortam_degiskeni(self):
        with mock.patch.dict(os.environ, {"ORKESTRA_AUTO_DEVAM_KAPISI": "0"}):
            kaydet, _ = self._kos()
        kaydet.assert_not_called()

    def test_hata_sessiz_gecer(self):
        with mock.patch.object(IP, "_auto_modu", side_effect=RuntimeError):
            AD.kontrol("sd", "oturum", {})

    def test_varsayilan_mod_golge(self):
        self.assertEqual(KM.mod(AD.KAPI), "golge")


if __name__ == "__main__":
    unittest.main()
