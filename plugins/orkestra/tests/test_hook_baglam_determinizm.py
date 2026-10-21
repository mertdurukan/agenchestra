"""I-139 P3 (bce F24): aynı girdi, aynı hook bağlamı. İki çalıştırmanın çıktısı baytı baytına eşit olmalı; aksi halde
istemin önbelleği her turda kırılır. Sabit örnek durum test_hook_baglam_boyut.py'deki gibi kurulur."""
import os
import sys
import unittest

TESTLER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TESTLER)
sys.path.insert(0, os.path.join(os.path.dirname(TESTLER), "scripts"))
import test_hook_baglam_boyut as TB  # noqa: E402


class BaglamDeterminizmi(unittest.TestCase):
    def setUp(self):
        self.h = TB.BaglamBoyutu("test_kriter1_tablo_her_olay_icin_onceki_sonraki")
        self.h.setUp()
        self.addCleanup(self.h.tearDown)

    def test_session_start_iki_kosu_ayni(self):
        a, b = self.h.session_start(), self.h.session_start()
        self.assertTrue(a)
        self.assertEqual(a.encode("utf-8"), b.encode("utf-8"))

    def test_user_prompt_submit_iki_kosu_ayni(self):
        a, b = self.h.ups(), self.h.ups()
        self.assertTrue(a)
        self.assertEqual(a.encode("utf-8"), b.encode("utf-8"))


if __name__ == "__main__":
    unittest.main()
