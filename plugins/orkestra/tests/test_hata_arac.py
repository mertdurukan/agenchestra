"""I-329 P1+P2: başarısız araç çağrısı hata.jsonl'e `kaynak: arac` satırı olarak yazılır (ADR-0141)."""
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


class AracHatasiYazici(unittest.TestCase):
    def test_alanlar_ve_ayri_kaynak_adlari(self):
        with tempfile.TemporaryDirectory() as sd:
            HK.arac_hatasi(sd, "Bash", "Exit code 1: komut bulunamadı", "ana")
            (s,) = satirlar(sd)
        self.assertEqual(s["kaynak"], "arac")
        self.assertEqual(s["tur"], "arac-hatasi")
        self.assertEqual(s["arac"], "Bash")
        self.assertEqual(s["ajan"], "ana")
        self.assertEqual(s["sinif"], "arac")
        self.assertEqual(set(s["kok"]), {"kaynak", "onlenebilir", "cozum"})
        self.assertEqual(s["kok"]["kaynak"], "arac")   # kök neden sınıfı, üst düzey kaynaktan ayrı

    def test_sir_maskelenir(self):
        with tempfile.TemporaryDirectory() as sd:
            HK.arac_hatasi(sd, "Bash", "curl -H 'Authorization: Bearer sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789' 401", "ana")
            (s,) = satirlar(sd)
        self.assertNotIn("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", json.dumps(s))

    def test_ayni_hata_ayni_imza_farkli_arac_farkli(self):
        a = HK.imza("arac-hatasi", r"Bash: Exit code 12 at C:\x\y")
        b = HK.imza("arac-hatasi", r"Bash: Exit code 7 at D:\z")
        self.assertEqual(a, b)
        self.assertNotEqual(HK.imza("arac-hatasi", "Bash: x"), HK.imza("arac-hatasi", "Edit: x"))

    def test_yazma_hatasinda_istisna_yok(self):
        with mock.patch.object(HK.L, "jsonl_ekle", side_effect=OSError("disk")):
            HK.arac_hatasi("/yok", "Bash", "x", "ana")   # fırlatmamalı

    def test_gecersiz_ajan_none(self):
        with tempfile.TemporaryDirectory() as sd:
            HK.arac_hatasi(sd, "Edit", "x", "baska")
            (s,) = satirlar(sd)
        self.assertIsNone(s["ajan"])


class FailureHook(unittest.TestCase):
    def _calistir(self, sd, **inp):
        girdi = {"cwd": sd, "session_id": "t", "tool_name": "Bash", "tool_input": {"command": "x"}, "error": "Exit code 1"}
        girdi.update(inp)
        with mock.patch.object(hook.L, "durum_dizini", return_value=sd), \
                mock.patch.object(hook, "gec", side_effect=SystemExit(0)), \
                mock.patch.object(hook.L, "hook_cikti"):
            with self.assertRaises(SystemExit):
                hook.post_tool_use_failure(girdi)

    def test_bash_hatasi_bir_satir_ekler(self):
        with tempfile.TemporaryDirectory() as sd:
            self._calistir(sd)
            self.assertEqual([s["arac"] for s in satirlar(sd)], ["Bash"])

    def test_alt_ajan_isaretlenir(self):
        with tempfile.TemporaryDirectory() as sd:
            self._calistir(sd, agent_id="a1")
            self.assertEqual(satirlar(sd)[0]["ajan"], "alt")

    def test_kesinti_satir_yazmaz(self):
        with tempfile.TemporaryDirectory() as sd:
            self._calistir(sd, is_interrupt=True)
            self.assertEqual(satirlar(sd), [])

    def test_yazici_patlarsa_hook_cikis_0(self):
        with tempfile.TemporaryDirectory() as sd, mock.patch.object(HK, "kaydet", side_effect=RuntimeError("x")):
            self._calistir(sd)   # SystemExit(0) beklenir, başka istisna değil


if __name__ == "__main__":
    unittest.main()
