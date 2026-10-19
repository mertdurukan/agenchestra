"""P-009 tetik anı: son todo maddesi bitince özet+kapatma atlanamaz (mesaj + Stop kapısı). Geçici projede koşar."""
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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hook  # noqa: E402
import ic_kos  # noqa: E402
import is_kaydi  # noqa: E402

CLI = os.path.join(KOK, "scripts", "orkestra.py")
OTURUM = "kapanis123456-oturum"


class KapanisKapisi(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_kapanis_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for k in ("ORKESTRA_RUYA", "ORKESTRA_PERSPEKTIF", "ORKESTRA_KAPANIS_KAPISI"):
            os.environ.pop(k, None)
        os.environ["CLAUDE_PROJECT_DIR"] = self.proje
        os.environ["ORKESTRA_OZET_KAPISI"] = "1"
        self.klasor = os.path.join(self.proje, "isler", "001-is")
        self.kayit = is_kaydi.is_ac(self.sd, "Deneme isi", self.klasor, dogrulama=False)
        self.id = self.kayit["id"]
        with open(os.path.join(self.sd, "oturumlar", OTURUM + ".json"), "w", encoding="utf-8") as f:
            json.dump({"is": self.id}, f)
        is_kaydi.todo_ekle(self.klasor, "tek madde")

    def tearDown(self):
        self._env.stop()
        shutil.rmtree(self.proje, ignore_errors=True)

    def bitir(self):
        return ic_kos.kos([CLI, "is", "todo", self.id, "--bitti", "1", "--not", "kanıt: test"], cwd=self.proje, env=dict(os.environ, PYTHONUTF8="1", CLAUDE_CODE_SESSION_ID=OTURUM))

    def stop(self, **ek):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                hook.stop({"cwd": self.proje, "session_id": OTURUM, **ek})
            except SystemExit:
                pass
        ham = buf.getvalue().strip()
        return json.loads(ham.splitlines()[-1]) if ham else {}

    def test_son_madde_mesaji_emir_ve_komutlar(self):
        r = self.bitir()
        cikti = r.stdout + r.stderr
        self.assertIn("ZORUNLU", cikti)
        self.assertIn(f"orkestra is belge {self.id} ozet", cikti)
        self.assertIn(f"orkestra is kapat {self.id}", cikti)

    def test_stop_todo_tamam_is_aciksa_bloklar(self):
        self.bitir()
        c = self.stop()
        self.assertEqual(c.get("decision"), "block")
        self.assertIn(f"orkestra is kapat {self.id}", c["reason"])
        self.assertIn("ozet", c["reason"])

    def test_stop_hook_active_dongu_kirar(self):
        self.bitir()
        self.assertNotEqual(self.stop(stop_hook_active=True).get("decision"), "block")

    def test_acik_madde_varken_bloklamaz(self):
        is_kaydi.todo_ekle(self.klasor, "ikinci madde")
        self.assertNotEqual(self.stop().get("decision"), "block")

    def test_kapi_kapaliyken_bloklamaz(self):
        self.bitir()
        os.environ["ORKESTRA_KAPANIS_KAPISI"] = "0"
        self.assertNotEqual(self.stop().get("decision"), "block")

    def test_is_kapaninca_bloklamaz(self):
        self.bitir()
        is_kaydi.is_durum(self.sd, self.id, "kapandi")
        self.assertNotEqual(self.stop().get("decision"), "block")


if __name__ == "__main__":
    unittest.main()
