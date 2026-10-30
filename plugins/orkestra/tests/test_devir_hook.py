"""ADR-0099: devir hatırlatmasının hook.pre_tool_use bağlantısı. Geçici projede koşar.
`py -3.13 -m pytest -q plugins/orkestra/tests/test_devir_hook.py`
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
import ork_lib as L  # noqa: E402

OTURUM = "devirhook-oturum-1"


class DevirHook(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_dh_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        with open(os.path.join(self.sd, "devir_hatirlatma.json"), "w", encoding="utf-8") as f:
            json.dump({"kontrol_orani": 0}, f)
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ["CLAUDE_PROJECT_DIR"] = self.proje
        for k in ("ORKESTRA_DEVIR_HATIRLATMA", "ORKESTRA_IS_KAPISI"):
            os.environ.pop(k, None)
        for k in ("ORKESTRA_SIRA_KAPISI", "ORKESTRA_ONAY_KAPISI", "ORKESTRA_IS_KAPISI"):
            os.environ[k] = "0"
        L.istek_id_yeni(self.sd, OTURUM)

    def tearDown(self):
        self._env.stop()
        shutil.rmtree(self.proje, ignore_errors=True)

    def pre(self, arac, girdi, **ek):
        g = {"tool_name": arac, "cwd": self.proje, "session_id": OTURUM, "tool_input": girdi}
        g.update(ek)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                hook.pre_tool_use(g)
            except SystemExit:
                pass
        ham = buf.getvalue().strip()
        if not ham:
            return "", ham
        h = json.loads(ham.splitlines()[-1]).get("hookSpecificOutput", {})
        return h.get("additionalContext", ""), h.get("permissionDecision")

    def yaz(self, ad, **ek):
        return self.pre("Write", {"file_path": os.path.join(self.proje, ad), "content": "x"}, **ek)

    def test_ana_ajan_ucuncu_dosyada_baglam_alir_engellenmez(self):
        self.assertEqual(self.yaz("a.py")[0], "")
        self.assertEqual(self.yaz("b.py")[0], "")
        ek, karar = self.yaz("c.py")
        self.assertIn("devir", ek)
        self.assertNotEqual(karar, "deny")

    def test_agent_id_li_cagri_hatirlatma_almaz(self):
        for ad in ("a.py", "b.py", "c.py"):
            self.assertEqual(self.yaz(ad, agent_id="alt1")[0], "")

    def test_kapali_ortam_degiskeni(self):
        os.environ["ORKESTRA_DEVIR_HATIRLATMA"] = "0"
        for ad in ("a.py", "b.py", "c.py"):
            self.assertEqual(self.yaz(ad)[0], "")

    def test_hatirlatma_hatasi_araci_bozmaz(self):
        import devir_hatirlatma as DH
        with mock.patch.object(DH, "izle", side_effect=RuntimeError("x")):
            for ad in ("a.py", "b.py", "c.py"):
                self.assertNotEqual(self.yaz(ad)[1], "deny")


if __name__ == "__main__":
    unittest.main()
