"""Konu defteri: hook (UserPromptSubmit, Stop) ve `orkestra konu` CLI uçtan uca (ADR-0116)."""
import json
import os
import sys
import unittest

import test_cekirdek as TC

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import konu_defteri as KD  # noqa: E402

ILK = "konu defteri hook testleri yazalım hemen şimdi"
FARKLI = "yarınki toplantı için sunum slaytlarını hazırla ve müşteriye gönder lütfen"


class KonuHook(unittest.TestCase):
    setUp = TC.Cekirdek.setUp
    tearDown = TC.Cekirdek.tearDown
    cli = TC.Cekirdek.cli
    hook = TC.Cekirdek.hook

    def defter(self):
        return KD.oku(self.sd)

    def test_ajansiz_ilk_istek_bir_konu(self):
        self.hook("UserPromptSubmit", {"prompt": ILK})
        ol = self.defter()
        self.assertEqual([(k["tur"], k.get("kaynak")) for k in ol], [("ac", "hook"), ("tur", None)])
        self.assertEqual(ol[0]["oturum"], TC.OTURUM)

    def test_her_istek_tur_sayar(self):
        for _ in range(3):
            self.hook("UserPromptSubmit", {"prompt": ILK})
        self.assertEqual(sum(1 for k in self.defter() if k["tur"] == "tur"), 3)
        self.assertEqual(sum(1 for k in self.defter() if k["tur"] == "ac"), 1)

    def test_farkli_konu_aday_ve_hatirlatma(self):
        self.hook("UserPromptSubmit", {"prompt": ILK})
        cikti = self.hook("UserPromptSubmit", {"prompt": FARKLI})
        self.assertIn("orkestra konu ac", json.dumps(cikti, ensure_ascii=False))
        self.assertEqual([k["tip"] for k in self.defter() if k["tur"] == "aday"], ["ortusme"])

    def test_alt_ajan_yazmaz(self):
        self.hook("UserPromptSubmit", {"prompt": ILK, "agent_id": "a1"})
        self.assertEqual([k for k in self.defter() if k["tur"] == "ac"], [])

    def test_kapali_bayrak(self):
        os.environ["ORKESTRA_KONU_DEFTERI"] = "0"
        try:
            self.hook("UserPromptSubmit", {"prompt": ILK})
        finally:
            del os.environ["ORKESTRA_KONU_DEFTERI"]
        self.assertEqual(self.defter(), [])

    def test_resume_ayni_oturum_yeni_konu_acmaz(self):
        self.hook("UserPromptSubmit", {"prompt": ILK})
        self.hook("SessionStart", {"source": "resume"})
        self.hook("SessionStart", {"source": "compact"})
        self.hook("UserPromptSubmit", {"prompt": ILK})
        self.assertEqual(sum(1 for k in self.defter() if k["tur"] == "ac"), 1)

    def test_stop_aday_sonrasi_golge_yazar(self):
        self.hook("UserPromptSubmit", {"prompt": ILK})
        self.hook("UserPromptSubmit", {"prompt": FARKLI})
        self.hook("Stop", {"stop_hook_active": False, "last_assistant_message": "tamam"})
        g = [json.loads(s) for s in open(os.path.join(self.sd, "gunluk.jsonl"), encoding="utf-8")]
        self.assertEqual([x["kapi"] for x in g if x["tur"] == "kapi_golge" and x.get("kapi") == "konu_defteri"], ["konu_defteri"])

    # ---- CLI
    def cli_env(self, *args):
        return self.cli(*args)

    def test_cli_ac_liste_rapor(self):
        env = {"CLAUDE_CODE_SESSION_ID": TC.OTURUM}
        r = TC.kos([TC.CLI, "konu", "ac", "Sunum hazırlığı", "--neden", "toplantı"], self.proje, ortam=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("K1 açıldı", r.stdout)
        r = TC.kos([TC.CLI, "konu", "liste"], self.proje, ortam=env)
        self.assertIn("Sunum hazırlığı", r.stdout)
        r = TC.kos([TC.CLI, "konu", "rapor", "--json"], self.proje, ortam=env)
        d = json.loads(r.stdout)
        self.assertEqual((d["sohbet"], d["konu"]), (1, 1))
        r = TC.kos([TC.CLI, "konu", "rapor", "--gun", "7"], self.proje, ortam=env)
        self.assertIn("# Sohbet konu raporu", r.stdout)

    def test_cli_rapor_dosyaya_ve_etiket(self):
        env = {"CLAUDE_CODE_SESSION_ID": TC.OTURUM}
        self.hook("UserPromptSubmit", {"prompt": ILK})
        hedef = os.path.join(self.proje, "rapor.md")
        r = TC.kos([TC.CLI, "konu", "rapor", "--yaz", hedef], self.proje, ortam=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.getsize(hedef) > 0)
        r = TC.kos([TC.CLI, "konu", "rapor", "--etiket"], self.proje, ortam=env)
        self.assertIn("etiket:", r.stdout)

    def test_cli_bos_baslik_reddedilir(self):
        r = TC.kos([TC.CLI, "konu", "ac", "  "], self.proje, ortam={"CLAUDE_CODE_SESSION_ID": TC.OTURUM})
        self.assertNotEqual(r.returncode, 0)

    def test_cli_tum_calisma_alanlari(self):
        from unittest import mock
        import ork_lib as L
        KD.ac(self.sd, "o1", "a")
        with mock.patch.object(L, "calisma_alanlari", return_value=[{"yol": self.proje}]):
            self.assertEqual(KD.rapor(__import__("komutlar.konu", fromlist=["x"])._sdler(True))["konu"], 1)


if __name__ == "__main__":
    unittest.main()
