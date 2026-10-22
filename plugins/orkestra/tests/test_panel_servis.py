"""ADR-0033: panel Task Scheduler görevi olarak çalışır (panel_servis.py + panel.baslat servis dalı).
`py -3.13 -m pytest plugins/orkestra/tests/test_panel_servis.py`
schtasks ve süreç başlatma taklit edilir; gerçek görev, ~/.claude ya da süreçler etkilenmez.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import doktor  # noqa: E402
import panel  # noqa: E402
import panel_servis  # noqa: E402


def _cp(kod=0, cikti=""):
    return subprocess.CompletedProcess([], kod, cikti, "")


class GorevXmlTest(unittest.TestCase):
    def test_xml_oturum_acilisi_ve_yeniden_baslatma(self):
        x = panel_servis.gorev_xml(8765, python="C:/py/pythonw.exe", betik="C:/k/panel.py", calisma_dizini="C:/g")
        self.assertIn("<LogonTrigger>", x)
        self.assertIn("<RestartOnFailure>", x)
        self.assertIn("<TimeTrigger><Repetition><Interval>PT1M</Interval></Repetition>", x)
        self.assertIn("<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>", x)
        self.assertIn("<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>", x)
        self.assertIn('"C:/k/panel.py" _kos 8765', x)


class KurKaldirTest(unittest.TestCase):
    def setUp(self):
        self.nt = mock.patch.object(panel_servis.os, "name", "nt")
        self.nt.start()
        self.addCleanup(self.nt.stop)
        self.isaret = mock.patch.object(panel_servis, "ISARET", os.path.join(tempfile.mkdtemp(prefix="ork_psrv_"), "p.json"))
        self.isaret.start()
        self.addCleanup(self.isaret.stop)

    def test_kur_gorevi_xml_ile_olusturur_ve_calistirir(self):
        with mock.patch.object(panel_servis, "_schtasks", return_value=_cp()) as st, \
                mock.patch.object(panel_servis, "_eski_paneli_durdur") as dur:
            s = panel_servis.kur(8765)
        cagrilar = [c.args for c in st.call_args_list]
        self.assertEqual(cagrilar[0][:3], ("/Create", "/TN", panel_servis.GOREV))
        self.assertIn("/XML", cagrilar[0])
        self.assertEqual(cagrilar[-1], ("/Run", "/TN", panel_servis.GOREV))
        dur.assert_called_once()
        self.assertEqual(s["port"], 8765)

    def test_kur_basarisizsa_hata(self):
        with mock.patch.object(panel_servis, "_schtasks", return_value=_cp(1, "")):
            with self.assertRaises(SystemExit):
                panel_servis.kur(8765)

    def test_kaldir_gorevi_durdurup_siler(self):
        with mock.patch.object(panel_servis, "_schtasks", return_value=_cp()) as st:
            self.assertTrue(panel_servis.kaldir()["kaldirildi"])
        self.assertEqual([c.args[0] for c in st.call_args_list], ["/End", "/Delete"])

    def test_durum_kurulu_bilgisi(self):
        with mock.patch.object(panel_servis, "_schtasks", return_value=_cp(0)):
            self.assertTrue(panel_servis.kurulu())
        with mock.patch.object(panel_servis, "_schtasks", return_value=_cp(1)):
            self.assertFalse(panel_servis.kurulu())

    def test_windows_disinda_acik_hata(self):
        with mock.patch.object(panel_servis.os, "name", "posix"):
            self.assertFalse(panel_servis.kurulu())
            with self.assertRaises(SystemExit):
                panel_servis.kur(8765)


class OtomatikKurTest(unittest.TestCase):
    """ADR-0034: SessionStart'ta görev yoksa kurulur; kullanıcı kaldırdıysa, opt-out varsa ya da aynı yolla hata aldıysa dokunulmaz."""

    def setUp(self):
        self.isaret = os.path.join(tempfile.mkdtemp(prefix="ork_psrv_"), "panel_servis.json")
        self.yamalar = [mock.patch.object(panel_servis, "ISARET", self.isaret),
                        mock.patch.object(panel_servis.os, "name", "nt"),
                        mock.patch.dict(os.environ, {}, clear=False)]
        for y in self.yamalar:
            y.start()
            self.addCleanup(y.stop)
        os.environ.pop("ORKESTRA_PANEL_SERVIS", None)

    def _isaret(self, durum, betik=None):
        with open(self.isaret, "w", encoding="utf-8") as f:
            json.dump({"durum": durum, "betik": betik or panel_servis.PANEL_BETIGI}, f)

    def test_gorev_yoksa_kurar(self):
        with mock.patch.object(panel_servis, "kurulu", return_value=False), \
                mock.patch.object(panel_servis, "kur") as kur:
            self.assertEqual(panel_servis.otomatik_kur(), "kuruldu")
        kur.assert_called_once()

    def test_opt_out_dokunmaz(self):
        os.environ["ORKESTRA_PANEL_SERVIS"] = "0"
        with mock.patch.object(panel_servis, "kur") as kur:
            self.assertIsNone(panel_servis.otomatik_kur())
        kur.assert_not_called()

    def test_kullanici_kaldirdiysa_yeniden_kurmaz(self):
        self._isaret("kaldirildi", betik="baska")
        with mock.patch.object(panel_servis, "kur") as kur:
            self.assertIsNone(panel_servis.otomatik_kur())
        kur.assert_not_called()

    def test_kurulu_ve_ayni_yolsa_schtasks_cagrilmaz(self):
        self._isaret("kuruldu")
        with mock.patch.object(panel_servis, "_schtasks") as st:
            self.assertIsNone(panel_servis.otomatik_kur())
        st.assert_not_called()

    def test_eklenti_yolu_degistiyse_yeniden_kaydeder(self):
        self._isaret("kuruldu", betik="C:/eski/panel.py")
        with mock.patch.object(panel_servis, "kurulu", return_value=True), \
                mock.patch.object(panel_servis, "_gorev_betigi_guncel", return_value=False), \
                mock.patch.object(panel_servis, "kur") as kur:
            self.assertEqual(panel_servis.otomatik_kur(), "kuruldu")
        kur.assert_called_once()

    def test_hata_isaretlenir_ve_ayni_yolla_tekrarlanmaz(self):
        with mock.patch.object(panel_servis, "kurulu", return_value=False), \
                mock.patch.object(panel_servis, "kur", side_effect=SystemExit("erişim engellendi")) as kur:
            self.assertIsNone(panel_servis.otomatik_kur())
            self.assertIsNone(panel_servis.otomatik_kur())
        kur.assert_called_once()
        with open(self.isaret, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["durum"], "hata")

    def test_windows_disinda_dokunmaz(self):
        with mock.patch.object(panel_servis.os, "name", "posix"), mock.patch.object(panel_servis, "kur") as kur:
            self.assertIsNone(panel_servis.otomatik_kur())
        kur.assert_not_called()


class BaslatServisTest(unittest.TestCase):
    def setUp(self):
        self.gecici = tempfile.mkdtemp(prefix="ork_psrv_")
        self.durum = os.path.join(self.gecici, "panel.json")
        with open(self.durum, "w", encoding="utf-8") as f:
            json.dump({"port": 8765, "pid": 1}, f)
        self.yamalar = [mock.patch.object(panel, "DURUM", self.durum),
                        mock.patch.object(panel.time, "sleep")]
        for y in self.yamalar:
            y.start()
            self.addCleanup(y.stop)

    def test_servis_varken_surum_uyusmazliginda_oldurme_ve_popen_yok(self):
        saglik = iter(["ok eski", "ok eski", f"ok {panel.SURUM}"])
        with mock.patch.object(panel.panel_servis, "kurulu", return_value=True), \
                mock.patch.object(panel.panel_servis, "yeniden_baslat", return_value=True) as yb, \
                mock.patch.object(panel, "_saglik", side_effect=lambda p: next(saglik)), \
                mock.patch.object(panel, "_durdur") as dur, \
                mock.patch.object(panel, "_bos_port") as bos, \
                mock.patch.object(panel.subprocess, "Popen") as popen:
            adres = panel.baslat(8765)
        yb.assert_called_once()
        dur.assert_not_called()
        bos.assert_not_called()
        popen.assert_not_called()
        self.assertTrue(adres.startswith("http://127.0.0.1:8765/"))

    def test_servis_yokken_eski_davranis(self):
        with mock.patch.object(panel.panel_servis, "kurulu", return_value=False), \
                mock.patch.object(panel, "_saglik", side_effect=["ok eski", "ok eski", f"ok {panel.SURUM}"]), \
                mock.patch.object(panel, "_durdur") as dur, \
                mock.patch.object(panel, "_bos_port", return_value=8765), \
                mock.patch.object(panel.subprocess, "Popen") as popen:
            panel.baslat(8765)
        dur.assert_called_once()
        popen.assert_called_once()


class DoktorServisTest(unittest.TestCase):
    def test_servis_yokken_mesaj_degismez(self):
        with mock.patch.object(doktor, "_panel_servisi_kurulu", return_value=False), \
                mock.patch.object(doktor.socket.socket, "connect_ex", return_value=0):
            self.assertIn("orkestra paneli çalışıyorsa normal", doktor.k_panel_port(mock.Mock(proje=None)).mesaj)

    def test_servis_kuruluyken_gorev_belirtilir(self):
        with mock.patch.object(doktor, "_panel_servisi_kurulu", return_value=True), \
                mock.patch.object(doktor.socket.socket, "connect_ex", return_value=0):
            self.assertIn("Orkestra Panel", doktor.k_panel_port(mock.Mock(proje=None)).mesaj)


if __name__ == "__main__":
    unittest.main()
