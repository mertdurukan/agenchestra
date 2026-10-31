"""Toast bildirimi. `python -m pytest plugins/orkestra/tests/test_bildirim.py -q`

(a) Kısa tur toast atmaz; uzun tur atar; soruyla biten mesaj 'yanıt bekleniyor' başlığı alır.
(b) Tur toast'ından sonra 'idle_prompt' tekrarlanmaz; 'permission_prompt' her zaman gider.
(c) ORKESTRA_BILDIRIM=0 hepsini kapatır; metin tek satıra indirilir ve sır maskelenir.
(d) tur_sonu: arka plan görevi açıkken 'iş bitti' gitmez; görev bitince çalışmanın başından ölçülen süreyle gider;
    süre önceki duraktan değil kullanıcı isteğinden ölçülür; idle_prompt arka plan sürerken susar.
Gerçek PowerShell çalışmaz; gonder() yerine sahte kullanılır, geçici dizine yazılır.
"""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import bildirim  # noqa: E402


class BildirimTesti(unittest.TestCase):
    def setUp(self):
        self.sd = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.sd, True)
        env = mock.patch.dict(os.environ, {"ORKESTRA_BILDIRIM": "1"})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("ORKESTRA_PERSPEKTIF", None)
        self.pl = mock.patch.object(sys, "platform", "win32")
        self.pl.start()
        self.addCleanup(self.pl.stop)

    def test_kisa_tur_sessiz_uzun_tur_toast(self):
        with mock.patch.object(bildirim, "gonder", return_value=True) as g:
            self.assertFalse(bildirim.tur_bitti(self.sd, "o1", 5000, "bitti"))
            g.assert_not_called()
            self.assertTrue(bildirim.tur_bitti(self.sd, "o1", 90000, "Tamamlandı."))
            self.assertEqual(g.call_args[0][0], "Orkestra: iş bitti")

    def test_soru_basligi(self):
        with mock.patch.object(bildirim, "gonder", return_value=True) as g:
            bildirim.tur_bitti(self.sd, "o1", 90000, "Hangisini seçelim?")
            self.assertEqual(g.call_args[0][0], "Orkestra: yanıtınız bekleniyor")

    def test_idle_tekrar_yok_izin_her_zaman(self):
        with mock.patch.object(bildirim, "gonder", return_value=True) as g:
            bildirim.tur_bitti(self.sd, "o1", 90000, "bitti")
            g.reset_mock()
            self.assertFalse(bildirim.bildirim_olayi(self.sd, "o1", {"notification_type": "idle_prompt", "message": "m"}))
            g.assert_not_called()
            self.assertTrue(bildirim.bildirim_olayi(self.sd, "o1", {"notification_type": "permission_prompt", "message": "izin?"}))
            self.assertEqual(g.call_args[0][0], "Orkestra: onayınız gerekiyor")
            # başka oturumun idle bildirimi engellenmez
            self.assertTrue(bildirim.bildirim_olayi(self.sd, "o2", {"notification_type": "idle_prompt", "message": "m"}))

    def test_kapatma_ve_metin(self):
        with mock.patch.dict(os.environ, {"ORKESTRA_BILDIRIM": "0"}):
            self.assertFalse(bildirim.gonder("b", "m"))
            self.assertFalse(bildirim.tur_bitti(self.sd, "o1", 90000, "x"))
        s = bildirim.tek_satir("a\n\n  b" + "x" * 300, 20)
        self.assertNotIn("\n", s)
        self.assertLessEqual(len(s), 20)


    def test_tur_sonu_arka_plan_aciksa_erteler_bitince_gonderir(self):
        with mock.patch.object(bildirim, "gonder", return_value=True) as g:
            # 10:00 isteği, 10:02'de test takımı arka plana düştü → çalışma sürüyor, toast yok
            self.assertFalse(bildirim.tur_sonu(self.sd, "o1", "2026-10-31T10:00:00Z", "2026-10-31T10:02:00Z", True, "arka planda koşuyor"))
            g.assert_not_called()
            self.assertEqual(bildirim.calisma_oku(self.sd, "o1"), "2026-10-31T10:00:00Z")
            # görev bitti, uyandıran bildirim turu 10:12'de kısa sürdü; süre çalışmanın başından (12 dk) ölçülür
            self.assertTrue(bildirim.tur_sonu(self.sd, "o1", "2026-10-31T10:12:00Z", "2026-10-31T10:12:05Z", False, "Tamamlandı."))
            self.assertEqual(g.call_args[0][0], "Orkestra: iş bitti")
            self.assertIsNone(bildirim.calisma_oku(self.sd, "o1"))

    def test_tur_sonu_bekleme_tur_suresi_sayilmaz(self):
        with mock.patch.object(bildirim, "gonder", return_value=True) as g:
            # istek 10:00:20'de geldi, tur 10:00:29'da bitti (9 sn); önceki duraktan beri geçen süre önemsiz
            self.assertFalse(bildirim.tur_sonu(self.sd, "o1", "2026-10-31T10:00:20Z", "2026-10-31T10:00:29Z", False, "kısa cevap"))
            g.assert_not_called()

    def test_tur_sonu_bildirimi_gelmeyen_gorev_sonsuza_dek_susturmaz(self):
        with mock.patch.object(bildirim, "gonder", return_value=True) as g:
            bildirim.tur_sonu(self.sd, "o1", "2026-10-31T10:00:00Z", "2026-10-31T10:01:00Z", True, "x")
            g.assert_not_called()
            self.assertTrue(bildirim.tur_sonu(self.sd, "o1", "2026-10-31T10:30:00Z", "2026-10-31T13:00:00Z", True, "x"))

    def test_idle_prompt_arka_plan_surerken_susar(self):
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        with open(os.path.join(self.sd, "oturumlar", "o1.json"), "w", encoding="utf-8") as f:
            f.write('{"acik_gorevler": ["toolu_1"]}')
        with mock.patch.object(bildirim, "gonder", return_value=True) as g:
            self.assertFalse(bildirim.bildirim_olayi(self.sd, "o1", {"notification_type": "idle_prompt", "message": "m"}))
            g.assert_not_called()
            self.assertTrue(bildirim.bildirim_olayi(self.sd, "o1", {"notification_type": "permission_prompt", "message": "izin?"}))


if __name__ == "__main__":
    unittest.main()
