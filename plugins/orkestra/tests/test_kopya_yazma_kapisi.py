"""Eklentinin kopyasına (yayın klonu, Claude Code'un yönettiği marketplaces/cache) yazımda ajan kaynağa yönlendirilir (engellenmez); kaynak depo sessizdir."""
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


class KopyaYazmaKapisi(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp(prefix="ork_kopya_")
        self.kaynak = os.path.join(self.t, "kaynak")
        self.klon = os.path.join(self.t, "klon")
        os.makedirs(os.path.join(self.kaynak, ".git"))
        os.makedirs(os.path.join(self.klon, ".git"))
        with open(os.path.join(self.klon, ".git", "config"), "w", encoding="utf-8") as f:
            f.write(f'[core]\n\tbare = false\n[remote "origin"]\n\turl = {self.kaynak}\n\tfetch = +refs/heads/*:refs/remotes/origin/*\n')
        self.pazar = mock.patch.object(L, "pazar_kaynagi", lambda pazar="claude-orchestration": self.klon)
        self.pazar.start()
        self.env = mock.patch.dict(os.environ, {"ORKESTRA_KOPYA_YAZMA": ""})
        self.env.start()

    def tearDown(self):
        self.pazar.stop()
        self.env.stop()
        shutil.rmtree(self.t, ignore_errors=True)

    def test_klon_kaynagi_gosterir_kaynak_serbest(self):
        self.assertEqual(L.kopyada_mi(os.path.join(self.klon, "plugins", "x.py")), self.kaynak)
        self.assertIsNone(L.kopyada_mi(os.path.join(self.kaynak, "plugins", "x.py")))
        self.assertIsNone(L.kopyada_mi(os.path.join(self.t, "baska", "x.py")))

    def test_yollar_kaynaga_cevrilir(self):
        import onay
        self.assertEqual(L.kaynaga_cevir(os.path.join(self.klon, "plugins", "orkestra", "KURALLAR.md")),
                         os.path.normpath(os.path.join(self.kaynak, "plugins", "orkestra", "KURALLAR.md")))
        ayni = os.path.join(self.kaynak, "x.md")
        self.assertEqual(L.kaynaga_cevir(ayni), ayni)
        with mock.patch.object(L, "PLUGIN_ROOT", os.path.join(self.klon, "plugins", "orkestra")),                 mock.patch.dict(os.environ, {"ORKESTRA_EKLENTI_KURALLARI": ""}):
            self.assertEqual(onay.eklenti_kural_yolu(),
                             os.path.normpath(os.path.join(self.kaynak, "plugins", "orkestra", "kurallar", "eklenti_kurallari.json")))

    def test_origin_yerel_klasor_degilse_kopya_sayilmaz(self):
        with open(os.path.join(self.klon, ".git", "config"), "w", encoding="utf-8") as f:
            f.write('[remote "origin"]\n\turl = https://github.com/x/y.git\n')
        self.assertIsNone(L.kopyada_mi(os.path.join(self.klon, "x.py")))

    def test_ortam_degiskeni_kapiyi_kapatir(self):
        with mock.patch.dict(os.environ, {"ORKESTRA_KOPYA_YAZMA": "1"}):
            self.assertIsNone(L.kopyada_mi(os.path.join(self.klon, "x.py")))

    def hook_cikti(self, yol, arac="Edit"):
        g = {"tool_name": arac, "tool_input": {"file_path": yol}, "cwd": self.t, "session_id": "kopya-1234567890"}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                hook.pre_tool_use(g)
            except SystemExit:
                pass
        return buf.getvalue()

    def test_hook_klona_yazimi_engellemez_uyarir(self):
        for arac in ("Edit", "Write"):
            o = json.loads(self.hook_cikti(os.path.join(self.klon, "plugins", "x.py"), arac))["hookSpecificOutput"]
            self.assertNotEqual(o.get("permissionDecision"), "deny")
            self.assertIn(self.kaynak, o["additionalContext"])

    def test_hook_kaynaga_yazimi_reddetmez(self):
        self.assertNotIn("kopya", self.hook_cikti(os.path.join(self.kaynak, "plugins", "x.py")))


if __name__ == "__main__":
    unittest.main()
