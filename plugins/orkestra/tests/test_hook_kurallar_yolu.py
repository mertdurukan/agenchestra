"""G-092: SessionStart bağlamı KURALLAR.md'nin mutlak yolunu tek satırda verir.
`py -3.13 -m pytest plugins/orkestra/tests/test_hook_kurallar_yolu.py`
"""
import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import hook  # noqa: E402
import ork_lib as L  # noqa: E402
import perspektif  # noqa: E402


class KurallarYoluTest(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_kyol_")
        os.makedirs(os.path.join(self.proje, ".claude", "orkestra", "oturumlar"))
        self.tr = os.path.join(self.proje, "tr.jsonl")
        open(self.tr, "w").close()

    def tearDown(self):
        shutil.rmtree(self.proje, ignore_errors=True)

    def baglam(self):
        rapor = {"okunmamis_rapor": None, "zamani_geldi": False, "calisiyor": False}
        g = {"session_id": "kyol-1234567890", "cwd": self.proje, "transcript_path": self.tr, "source": "startup"}
        buf = io.StringIO()
        with mock.patch.object(L, "bayatlik", return_value=None), mock.patch.object(perspektif, "durum", return_value=rapor), \
                contextlib.redirect_stdout(buf):
            try:
                hook.session_start(g)
            except SystemExit:
                pass
        return json.loads(buf.getvalue())["hookSpecificOutput"]["additionalContext"]

    def test_tek_satir_var_olan_mutlak_yol(self):
        satirlar = [x for x in self.baglam().splitlines() if "KURALLAR.md" in x]
        self.assertEqual(len(satirlar), 1)
        m = re.search(r"Kurallar: (.+KURALLAR\.md)\.", satirlar[0])
        self.assertTrue(m, satirlar[0])
        self.assertTrue(os.path.isabs(m.group(1)))
        self.assertTrue(os.path.isfile(m.group(1)))
        self.assertEqual(os.path.normcase(m.group(1)), os.path.normcase(os.path.join(KOK, "KURALLAR.md")))

    def test_dosya_yoksa_satir_yok(self):
        with mock.patch.object(hook.os.path, "isfile", return_value=False):
            self.assertNotIn("KURALLAR.md", self.baglam())

    def test_kodda_sabit_kisisel_yol_yok(self):
        with open(os.path.join(KOK, "scripts", "hook.py"), encoding="utf-8") as f:
            kod = f.read()
        for yasak in ("C:/Users", "C:" + chr(92) + "Users", "Mert", "Desktop"):
            self.assertNotIn(yasak, kod)


if __name__ == "__main__":
    unittest.main()
