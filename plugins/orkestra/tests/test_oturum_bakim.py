"""I-255 P1 (ADR-0092): SessionStart bakım işleri ayrık, kilitli, aralıklı koşucuda çalışır; hook alt süreç başlatmaz.
`py -3.13 -m pytest plugins/orkestra/tests/test_oturum_bakim.py`
Alt süreç, git ve schtasks taklit edilir; gerçek depo, Task Scheduler ve ~/.claude etkilenmez.
"""
import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import oturum_bakim  # noqa: E402


class BaslatTest(unittest.TestCase):
    def setUp(self):
        self.sd = tempfile.mkdtemp(prefix="ork_bakim_")
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        os.environ.pop("ORKESTRA_OTURUM_BAKIM", None)

    def _baslat(self):
        with mock.patch.object(oturum_bakim.subprocess, "Popen") as po:
            return oturum_bakim.baslat(self.sd, self.sd), po

    def test_ilk_cagri_ayrik_surec_baslatir(self):
        ok, po = self._baslat()
        self.assertTrue(ok)
        po.assert_called_once()
        self.assertEqual(po.call_args.kwargs["stdin"], oturum_bakim.subprocess.DEVNULL)

    def test_aralik_dolmadan_ikinci_surec_baslamaz(self):
        self._baslat()
        ok, po = self._baslat()
        self.assertFalse(ok)
        po.assert_not_called()

    def test_aralik_dolunca_yeniden_baslar(self):
        self._baslat()
        eski = time.time() - oturum_bakim.ARA - 5
        os.utime(os.path.join(self.sd, oturum_bakim.ISARET), (eski, eski))
        ok, po = self._baslat()
        self.assertTrue(ok)
        po.assert_called_once()

    def test_opt_out_surec_baslatmaz(self):
        os.environ["ORKESTRA_OTURUM_BAKIM"] = "0"
        ok, po = self._baslat()
        self.assertFalse(ok)
        po.assert_not_called()

    def test_popen_hatasi_hook_dusurmez(self):
        with mock.patch.object(oturum_bakim.subprocess, "Popen", side_effect=OSError("yok")):
            self.assertFalse(oturum_bakim.baslat(self.sd, self.sd))


class CalistirTest(unittest.TestCase):
    def setUp(self):
        self.sd = tempfile.mkdtemp(prefix="ork_bakim_")

    def _adimlar(self):
        return [mock.patch.object(oturum_bakim, "_adimlar", return_value=[("a", lambda: None), ("b", lambda: {"x": 1})])]

    def test_adimlar_calisir_ve_onbellek_yazilir(self):
        with mock.patch.object(oturum_bakim, "_adimlar", return_value=[("a", lambda: None), ("bayatlik", lambda: {"farkli": 3})]):
            self.assertTrue(oturum_bakim.calistir(self.sd, self.sd))
        self.assertEqual(oturum_bakim.onbellek(self.sd)["bayatlik"], {"farkli": 3})

    def test_bir_adim_hata_verirse_digerleri_kosar_ve_hata_yazilir(self):
        def kotu():
            raise RuntimeError("git yok")
        sonra = mock.Mock(return_value=None)
        with mock.patch.object(oturum_bakim, "_adimlar", return_value=[("kotu", kotu), ("sonra", sonra)]), \
                mock.patch.object(oturum_bakim, "_hata_yaz") as hy:
            oturum_bakim.calistir(self.sd, self.sd)
        sonra.assert_called_once()
        hy.assert_called_once()

    def test_kilit_baskasindaysa_ikinci_kopya_calismaz(self):
        adim = mock.Mock(return_value=None)
        with mock.patch.object(oturum_bakim, "_adimlar", return_value=[("a", adim)]), \
                mock.patch.object(oturum_bakim, "_kilit_al", return_value=None):
            self.assertFalse(oturum_bakim.calistir(self.sd, self.sd))
        adim.assert_not_called()

    def test_onbellek_yoksa_bos_doner(self):
        self.assertEqual(oturum_bakim.onbellek(self.sd), {})


if __name__ == "__main__":
    unittest.main()
