"""G-081: SessionStart bağlamında 'orkestra panelini aç' satırı (launch.json'a bağlı, oturumda bir kez).
`py -3.13 -m pytest plugins/orkestra/tests/test_hook_panel_ac.py`
Hepsi geçici projede koşar; gerçek ~/.claude ya da proje durum dizinine yazılmaz.
"""
import contextlib
import io
import json
import os
import shutil
import socket
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import hook  # noqa: E402
import niyet  # noqa: E402
import ork_lib as L  # noqa: E402
import panel  # noqa: E402
import perspektif  # noqa: E402

OTURUM = "panelac-1234567890-oturum"
GIRDI_ORIGIN = "http://127.0.0.1:8765"


def _bos_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class PanelAcTest(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_panelac_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        self.genel = os.path.join(self.proje, "genel_panel")
        os.makedirs(self.genel)
        self.durum_yolu = os.path.join(self.genel, "panel.json")
        self.tr = os.path.join(self.proje, "tr.jsonl")
        open(self.tr, "w").close()
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for k in ("CLAUDE_PROJECT_DIR", "ORKESTRA_RUYA", "ORKESTRA_PERSPEKTIF"):
            os.environ.pop(k, None)
        niyet_yolu = os.path.join(self.proje, "niyet", "niyet.jsonl")
        self._p = [mock.patch.object(niyet, "NIYET_YOLU", niyet_yolu),
                   mock.patch.object(niyet, "GENEL_DIZIN", os.path.dirname(niyet_yolu)),
                   mock.patch.object(niyet, "_gecici", return_value=False),
                   mock.patch.object(panel, "DURUM", self.durum_yolu),
                   mock.patch.object(L, "GENEL_DIZIN", self.genel)]
        for p in self._p:
            p.start()
        self.soketler = []

    def tearDown(self):
        for s in self.soketler:
            s.close()
        for p in self._p:
            p.stop()
        self._env.stop()
        shutil.rmtree(self.proje, ignore_errors=True)

    # --- yardımcılar
    def launch_yaz(self, girdiler):
        os.makedirs(os.path.join(self.proje, ".claude"), exist_ok=True)
        with open(os.path.join(self.proje, ".claude", "launch.json"), "w", encoding="utf-8") as f:
            json.dump({"version": "0.0.1", "configurations": girdiler}, f)

    def launch_panelli(self):
        self.launch_yaz([{"name": "orkestra-panel", "url": GIRDI_ORIGIN}])

    def panel_durumu(self, port):
        with open(self.durum_yolu, "w", encoding="utf-8") as f:
            json.dump({"port": port, "pid": 1, "surum": "x", "zaman": "2026-10-15T09:00:00+03:00"}, f)

    def sunucu_ac(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        s.listen(5)
        self.soketler.append(s)
        port = s.getsockname()[1]
        self.panel_durumu(port)
        return port

    def sunucu_kapali(self):
        port = _bos_port()
        self.panel_durumu(port)
        return port

    def acilis(self, oid=OTURUM, rapor_tekrar=0, kaynak="startup"):
        """session_start koş; additionalContext metnini döndür."""
        bayat = None
        rapor = {"okunmamis_rapor": ("ruya_20261013_1500.md" * rapor_tekrar) or None,
                 "zamani_geldi": False, "calisiyor": False}
        g = {"session_id": oid, "cwd": self.proje, "transcript_path": self.tr, "source": kaynak}
        buf = io.StringIO()
        with mock.patch.object(L, "bayatlik", return_value=bayat), mock.patch.object(perspektif, "durum", return_value=rapor), \
                contextlib.redirect_stdout(buf):
            try:
                hook.session_start(g)
            except SystemExit:
                pass
        cikti = buf.getvalue().strip()
        if not cikti:
            return ""
        return json.loads(cikti)["hookSpecificOutput"]["additionalContext"]

    # --- kriter 1
    def test_launch_girdisi_varsa_panel_satiri_gelir(self):
        self.launch_panelli()
        port = self.sunucu_ac()
        ek = self.acilis()
        self.assertIn("preview_start", ek)
        self.assertIn("orkestra-panel", ek)
        self.assertNotIn("/isler", ek)
        self.assertIn(f"http://127.0.0.1:{port}/", ek)

    def test_diger_girdilerle_birlikte_orkestra_panel_bulunur(self):
        self.launch_yaz([{"name": "baska", "url": "http://localhost:3000"},
                         {"name": "orkestra-panel", "url": GIRDI_ORIGIN}])
        self.sunucu_ac()
        self.assertIn("preview_start", self.acilis())

    # --- kriter 2
    def test_ikinci_cagrida_satir_yok_ve_durum_dosyasi_oturum_kimlikli(self):
        self.launch_panelli()
        self.sunucu_ac()
        ilk = self.acilis(kaynak="startup")
        self.assertIn("preview_start", ilk)
        for kaynak in ("resume", "compact", "clear"):
            ek = self.acilis(kaynak=kaynak)
            self.assertNotIn("preview_start", ek, kaynak)
            self.assertNotIn("orkestra-panel", ek, kaynak)
        dosyalar = [f for f in os.listdir(os.path.join(self.sd, "oturumlar")) if OTURUM in f]
        self.assertTrue(dosyalar, "oturum kimlikli bir durum dosyası beklenir")

    def test_farkli_oturumda_satir_yine_gelir(self):
        self.launch_panelli()
        self.sunucu_ac()
        self.assertIn("preview_start", self.acilis(oid="oturum-a-1234567890"))
        self.assertNotIn("preview_start", self.acilis(oid="oturum-a-1234567890"))
        self.assertIn("preview_start", self.acilis(oid="oturum-b-1234567890"))

    # --- kriter 3
    def test_launch_json_yoksa_satir_yok(self):
        self.sunucu_ac()
        ek = self.acilis()
        self.assertNotIn("preview_start", ek)
        self.assertNotIn("orkestra-panel", ek)
        self.assertIn("Orkestra bu projede açık", ek)  # hook yine çalışır

    def test_girdi_yoksa_satir_yok(self):
        self.launch_yaz([{"name": "baska", "url": "http://localhost:3000"}])
        self.sunucu_ac()
        ek = self.acilis()
        self.assertNotIn("preview_start", ek)
        self.assertNotIn("orkestra-panel", ek)

    def test_bozuk_launch_json_hook_dusurmez(self):
        os.makedirs(os.path.join(self.proje, ".claude"), exist_ok=True)
        with open(os.path.join(self.proje, ".claude", "launch.json"), "w", encoding="utf-8") as f:
            f.write("{bozuk json")
        ek = self.acilis()
        self.assertIn("Orkestra bu projede açık", ek)
        self.assertNotIn("preview_start", ek)

    def test_bos_configurations_satir_yok(self):
        self.launch_yaz([])
        self.assertNotIn("preview_start", self.acilis())

    # --- kriter 4
    def test_sunucu_kapaliyken_orkestra_panel_komutu_yazilir(self):
        self.launch_panelli()
        self.sunucu_kapali()
        ek = self.acilis()
        self.assertIn("preview_start", ek)
        self.assertIn("`orkestra panel`", ek)

    def test_sunucu_aciksa_orkestra_panel_komutu_yazilmaz(self):
        self.launch_panelli()
        self.sunucu_ac()
        ek = self.acilis()
        self.assertIn("preview_start", ek)
        self.assertNotIn("`orkestra panel`", ek)

    def test_panel_json_yoksa_sunucu_kapali_sayilir(self):
        self.launch_panelli()
        self.assertFalse(os.path.exists(self.durum_yolu))
        with mock.patch.object(socket.socket, "connect_ex", return_value=10061), \
                mock.patch.object(socket.socket, "connect", side_effect=ConnectionRefusedError):
            ek = self.acilis()
        self.assertIn("preview_start", ek)
        self.assertIn("`orkestra panel`", ek)

    # --- kriter 5
    def test_uzun_baglamda_panel_satiri_kesimde_kaybolmaz(self):
        self.launch_panelli()
        self.sunucu_kapali()
        ek = self.acilis(rapor_tekrar=300)
        self.assertIn("preview_start", ek)
        self.assertNotIn("/isler", ek)
        self.assertIn("`orkestra panel`", ek)

    def test_uzun_baglamda_panel_satiri_ve_onay_birlikte(self):
        self.launch_panelli()
        self.sunucu_ac()
        ek = self.acilis(rapor_tekrar=300)
        self.assertIn("preview_start", ek)
        self.assertLessEqual(len(ek), 1800 + 400)  # kesim hâlâ geçerli (onay/etki satırı payı)


if __name__ == "__main__":
    unittest.main()
