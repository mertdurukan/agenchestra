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


class SureGunluguTest(unittest.TestCase):
    """P3: SessionStart süresi gunluk.jsonl'a yazılır; eşik aşımı gölge uyarıdır."""

    def setUp(self):
        self.sd = tempfile.mkdtemp(prefix="ork_sure_")
        import hook
        self.hook = hook

    def _satirlar(self):
        with open(os.path.join(self.sd, "gunluk.jsonl"), encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]

    def test_hizli_acilis_yalniz_sure_satiri_yazar(self):
        self.hook._sure_yaz(self.sd, "o1", 350.4)
        s = self._satirlar()
        self.assertEqual([x["tur"] for x in s], ["hook_sure"])
        self.assertEqual(s[0]["sure_ms"], 350)

    def test_esik_asimi_kapi_golge_yazar(self):
        self.hook._sure_yaz(self.sd, "o1", 2500)
        s = self._satirlar()
        self.assertEqual([x["tur"] for x in s], ["hook_sure", "kapi_golge"])
        self.assertEqual(s[1]["kapi"], "sessionstart_sure")


class WorktreeAlgilamaTest(unittest.TestCase):
    """P1/S2: devral ipucu ana depoda git alt süreci açmaz; yalnız `.git` DOSYASI (worktree) git'e düşer."""

    def test_git_klasoru_ana_depo_dosyasi_worktree(self):
        import is_kaydi
        k = tempfile.mkdtemp(prefix="ork_wt_")
        os.makedirs(os.path.join(k, "ana", ".git"))
        os.makedirs(os.path.join(k, "wt", "alt"))
        with open(os.path.join(k, "wt", ".git"), "w", encoding="utf-8") as f:
            f.write("gitdir: x")
        self.assertFalse(is_kaydi._worktree_icinde_mi(os.path.join(k, "ana")))
        self.assertTrue(is_kaydi._worktree_icinde_mi(os.path.join(k, "wt", "alt")))
        self.assertFalse(is_kaydi._worktree_icinde_mi(k))


if __name__ == "__main__":
    unittest.main()
