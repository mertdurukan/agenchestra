"""I-297 P2: eşitleme kopyayı yazdıysa değişen kural özeti SessionStart bağlamına girer (bayat kopya vakası).
`py -3.13 -m pytest plugins/orkestra/tests/test_kural_kopya_gecikme.py`
"""
import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import hook  # noqa: E402
import onay  # noqa: E402
import ork_lib as L  # noqa: E402
import perspektif  # noqa: E402

ESKI = "- Eski K-004 metni. (K-004, 2026-10-16)\n- Sabit kural. (K-005, 2026-10-16)\n"
YENI = "- Yeni K-004 metni. (K-004, 2026-10-16)\n- Sabit kural. (K-005, 2026-10-16)\n- Eklenen. (P-040, 2026-10-31)\n"


class KuralFarkiTest(unittest.TestCase):
    def test_fark_eklenen_degisen_kalkan(self):
        self.assertEqual(onay.kural_farki(ESKI, YENI), ["P-040 (eklendi)", "K-004 (değişti)"])
        self.assertEqual(onay.kural_farki(YENI, ESKI), ["K-004 (değişti)", "P-040 (kalktı)"])
        self.assertEqual(onay.kural_farki(ESKI, ESKI), [])


class SessionStartBaglamTest(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_kgec_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        self.tr = os.path.join(self.proje, "tr.jsonl")
        open(self.tr, "w").close()

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)

    def _baglam(self, yaz_eski):
        yol = onay._kural_dosya_yolu(self.sd)
        if yaz_eski:
            os.makedirs(os.path.dirname(yol), exist_ok=True)
            with open(yol, "w", encoding="utf-8", newline="") as f:
                f.write(ESKI)
        rapor = {"okunmamis_rapor": None, "zamani_geldi": False, "calisiyor": False}
        g = {"session_id": "kgec-1234567890", "cwd": self.proje, "transcript_path": self.tr, "source": "startup"}
        buf = io.StringIO()
        with mock.patch.object(L, "bayatlik", return_value=None), mock.patch.object(perspektif, "durum", return_value=rapor), \
                mock.patch.object(onay, "_kural_dosya_metni", return_value=YENI), contextlib.redirect_stdout(buf):
            try:
                hook.session_start(g)
            except SystemExit:
                pass
        return buf.getvalue()

    def test_bayat_kopya_yakalanir(self):
        cikti = self._baglam(yaz_eski=True)
        self.assertIn("KURAL KOPYASI GÜNCELLENDİ", cikti)
        self.assertIn("K-004 (değişti)", cikti)

    def test_guncel_kopya_uyari_vermez(self):
        self._baglam(yaz_eski=True)  # ilk koşu kopyayı yeniler
        self.assertNotIn("KURAL KOPYASI GÜNCELLENDİ", self._baglam(yaz_eski=False))


if __name__ == "__main__":
    unittest.main()
