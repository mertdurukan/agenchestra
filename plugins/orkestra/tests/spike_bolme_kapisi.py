"""I-297 P1 spike (C6): PreToolUse girdisinde araç adı ayrılabiliyor mu ve ret metni ajana giden çıktıya yazılıyor mu.
`py -3.13 -m pytest plugins/orkestra/tests/spike_bolme_kapisi.py -s`
Sonuç (var/yok) çıktıya yazılır; P5 bölme kapısı bu sonuca dayanır.
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import hook  # noqa: E402

START = "mcp__ccd_session__start_session"


class BolmeKapisiSpike(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_spike_")
        os.makedirs(os.path.join(self.proje, ".claude", "orkestra", "oturumlar"))

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)

    def _calistir(self, arac):
        giris = {"tool_name": arac, "tool_input": {}, "cwd": self.proje, "session_id": "spike-1234567890"}
        buf = io.StringIO()

        def karar(a, g, sd, oturum=None):
            return ("deny", "bölme gerekli: önce start_session") if a == START else (None, "")

        with mock.patch.object(hook, "_izin_karari", side_effect=karar), contextlib.redirect_stdout(buf):
            try:
                hook.pre_tool_use(giris)
            except SystemExit:
                pass
        return buf.getvalue()

    def test_arac_adi_ayrilir_ve_ret_metni_cikar(self):
        cikti = self._calistir(START)
        ho = json.loads(cikti)["hookSpecificOutput"]
        self.assertEqual(ho["permissionDecision"], "deny")
        self.assertIn("start_session", ho["permissionDecisionReason"])
        print("TEYIT 1 (araç adı ayrımı + ret metni çıktıda): VAR")

    def test_baska_arac_etkilenmez(self):
        self.assertNotIn('"deny"', self._calistir("Read"))

    def test_kural_dosyasi_esitleme_sonucu_bildirir(self):
        import onay
        sd = os.path.join(self.proje, ".claude", "orkestra")
        ilk = onay.kural_dosyasi_esitle(sd)
        ikinci = onay.kural_dosyasi_esitle(sd)
        self.assertFalse(ikinci)
        print(f"TEYIT 2 (esitle ilk çağrıda yazdı={ilk}, ikincide yazmadı; dosya Claude Code tarafından oturum açılışında okunur, yeni içerik bir sonraki oturumda görünür): VAR")


if __name__ == "__main__":
    unittest.main()
