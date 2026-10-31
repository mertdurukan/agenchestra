"""I-297 P4: kayma sınıflayıcısı. Bağlı oturumda bilgi sorusu kesin farklı konuysa yönerge gelir (S1); ilişki ölçütü iş
belgesinin gövdesine bağlı değildir (S2).
`py -3.13 -m pytest plugins/orkestra/tests/test_konu_kaymasi.py`
"""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import hook  # noqa: E402
import is_kaydi  # noqa: E402
import is_yonlendirme as IY  # noqa: E402
import niyet  # noqa: E402

IS = {"id": "I-021", "baslik": "Langfuse izleme entegrasyonu PE-612", "klasor": "05-langfuse-izleme-entegrasyonu"}
KAYMA = "Azure OpenAI fiyatlandırması nasıl hesaplanıyor, aylık kota ve token maliyeti nedir?"
AYNI = "Langfuse izleme entegrasyonu nasıl çalışıyor, trace kayıtları nerede tutuluyor?"


class KaymaMiTest(unittest.TestCase):
    def test_ihlal_vakasi_kayma(self):
        self.assertTrue(IY.kayma_mi(KAYMA, IS))

    def test_kontrol_vakasi_ayni_konu(self):
        self.assertFalse(IY.kayma_mi(AYNI, IS))

    def test_acik_gonderme_kayma_degil(self):
        self.assertFalse(IY.kayma_mi("I-021 için Azure OpenAI fiyatlandırması nasıl hesaplanıyor, aylık kota nedir?", IS))

    def test_kisa_mesaj_kayma_sayilmaz(self):
        self.assertFalse(IY.kayma_mi("Bu ne demek?", IS))

    def test_guncel_niyet_ilgiyi_kurar(self):
        self.assertFalse(IY.kayma_mi(KAYMA, IS, guncel_konu="Azure OpenAI fiyatlandırması ve token maliyeti incelemesi"))


class GovdeBagimsizTest(unittest.TestCase):
    """S2: farklı konunun sözcüklerini taşıyan iş belgesi mesajı 'ilgili' yapmaz."""

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="ork_kayma_")
        with open(os.path.join(self.d, "todo.md"), "w", encoding="utf-8") as f:
            f.write("Azure OpenAI fiyatlandırması aylık kota token maliyeti hesaplama " * 20)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_govde_okunmaz(self):
        g = {"id": "I-021", "baslik": IS["baslik"], "klasor": self.d}
        self.assertNotIn("Azure", hook._bagli_is_kaydi(g)["metin"])
        with mock.patch.object(is_kaydi, "is_liste", return_value=[g]):
            self.assertFalse(hook._bagli_isle_ilgili("sd", "I-021", KAYMA))


class HookYonergeTest(unittest.TestCase):
    def _ipucu(self, mesaj, mod="etkin"):
        g = {"id": "I-021", "baslik": IS["baslik"], "klasor": IS["klasor"]}
        with mock.patch.object(hook, "_otomatik_yonlendirme", return_value=""), \
                mock.patch.object(hook, "_oturum_isi", return_value="I-021"), \
                mock.patch.object(hook, "_ayar_dosyasi", return_value={"mod": mod}), \
                mock.patch.object(is_kaydi, "is_liste", return_value=[g]), \
                mock.patch.object(niyet, "son_niyet", return_value=None):
            return hook._yonlendirme_ipucu("sd", "oturum-1", mesaj)

    def test_bilgi_sorusu_farkli_konu_yonerge_alir(self):
        self.assertIn("start_session", self._ipucu(KAYMA))

    def test_bilgi_sorusu_ayni_konu_susar(self):
        self.assertEqual(self._ipucu(AYNI), "")

    def test_kapali_mod_eski_davranis(self):
        self.assertEqual(self._ipucu(KAYMA, mod="kapali"), "")

    def test_onay_mesaji_muaf(self):
        self.assertEqual(self._ipucu("tamam, devam et"), "")


if __name__ == "__main__":
    unittest.main()
