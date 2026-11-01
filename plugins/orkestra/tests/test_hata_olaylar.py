"""I-329 P3: PermissionDenied ve StopFailure hata defterine yazılır; hook-red ile çift sayım olmaz (ADR-0141).
Olay yükü şeması canlı doğrulanmadı (belge kaynaklı): alan adları satıra düşer."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

AD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AD, "..", "scripts"))

import hata_kayit as HK  # noqa: E402
import hook  # noqa: E402


def satirlar(sd):
    yol = os.path.join(sd, "hata.jsonl")
    if not os.path.exists(yol):
        return []
    with open(yol, encoding="utf-8") as f:
        return [json.loads(s) for s in f if s.strip()]


class Olaylar(unittest.TestCase):
    def _calistir(self, sd, isleyici, **inp):
        girdi = {"cwd": sd, "session_id": "t", "tool_name": "AskUserQuestion"}
        girdi.update(inp)
        with mock.patch.object(hook.L, "durum_dizini", return_value=sd), \
                mock.patch.object(hook, "gec", side_effect=SystemExit(0)):
            with self.assertRaises(SystemExit):
                isleyici(girdi)

    def test_izin_reddi_yazilir(self):
        with tempfile.TemporaryDirectory() as sd:
            self._calistir(sd, hook.permission_denied, reason="auto modu")
            (s,) = satirlar(sd)
        self.assertEqual((s["kaynak"], s["tur"], s["arac"]), ("arac", "izin-reddi", "AskUserQuestion"))
        self.assertEqual(s["kok"]["kaynak"], "kural")
        self.assertIn("cwd", s["baglam"]["alanlar"])

    def test_hook_red_varken_cift_yazilmaz(self):
        with tempfile.TemporaryDirectory() as sd:
            HK.kaydet(sd, "hook", "hook-red", "P-016 ret", arac="AskUserQuestion")
            self._calistir(sd, hook.permission_denied)
            self.assertEqual([s["tur"] for s in satirlar(sd)], ["hook-red"])

    def test_farkli_arac_hook_redi_yazmayi_engellemez(self):
        with tempfile.TemporaryDirectory() as sd:
            HK.kaydet(sd, "hook", "hook-red", "P-016 ret", arac="Bash")
            self._calistir(sd, hook.permission_denied)
            self.assertEqual([s["tur"] for s in satirlar(sd)], ["hook-red", "izin-reddi"])

    def test_eski_hook_red_pencere_disi(self):
        with tempfile.TemporaryDirectory() as sd:
            HK.kaydet(sd, "hook", "hook-red", "ret", arac="AskUserQuestion")
            yol = os.path.join(sd, "hata.jsonl")
            k = satirlar(sd)[0]
            k["zaman"] = "2000-01-01T00:00:00"
            with open(yol, "w", encoding="utf-8") as f:
                f.write(json.dumps(k) + "\n")
            self._calistir(sd, hook.permission_denied)
            self.assertEqual(len(satirlar(sd)), 2)

    def test_stop_failure_yazilir(self):
        with tempfile.TemporaryDirectory() as sd:
            self._calistir(sd, hook.stop_failure, error="rate_limit")
            (s,) = satirlar(sd)
        self.assertEqual((s["tur"], s["kok"]["kaynak"]), ("tur-api-hatasi", "belirsiz"))
        self.assertIn("rate_limit", s["ileti"])

    def test_yazici_patlarsa_cikis_0(self):
        with tempfile.TemporaryDirectory() as sd, mock.patch.object(HK, "arac_hatasi", side_effect=RuntimeError("x")):
            self._calistir(sd, hook.permission_denied)
            self._calistir(sd, hook.stop_failure)

    def test_hooks_json_olaylari_kayitli(self):
        with open(os.path.join(AD, "..", "hooks", "hooks.json"), encoding="utf-8") as f:
            olaylar = json.load(f)["hooks"]
        for o in ("PermissionDenied", "StopFailure"):
            self.assertIn(o, olaylar)
            self.assertIn(o, hook.OLAYLAR)


if __name__ == "__main__":
    unittest.main()
