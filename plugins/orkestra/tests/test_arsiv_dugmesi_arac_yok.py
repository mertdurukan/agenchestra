"""I-455 / ADR-0180: kapanış aracı oturumda yoksa arşiv düğmesi Stop kapısı susar; varsa ya da bilinmiyorsa eski sonuç."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import arsiv_dugmesi as AD  # noqa: E402

WRAP = "mcp__ccd_turn__wrap_up"
PLAN = "mcp__ccd_turn__update_plan"


def _transkript(klasor, araclar, liste):
    """liste: None (liste kaydı yok), ya da yüklü araç adları (api-request-shape)."""
    yol = os.path.join(klasor, "t.jsonl")
    satirlar = []
    if liste is not None:
        satirlar.append({"type": "api-request-shape", "shape": {"tools": [{"name": a} for a in liste]}})
    satirlar.append({"type": "user", "message": {"content": "iş yap"}})
    for ad in araclar:
        satirlar.append({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": ad, "input": {}}]}})
    with open(yol, "w", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(s, ensure_ascii=False) for s in satirlar))
    return yol


class AracYoksaSusar(unittest.TestCase):
    def setUp(self):
        self.sd = tempfile.mkdtemp()
        self.addCleanup(os.environ.__setitem__, "ORKESTRA_ARSIV_DUGMESI", os.environ.get("ORKESTRA_ARSIV_DUGMESI", "0"))
        os.environ["ORKESTRA_ARSIV_DUGMESI"] = "1"

    def test_arac_yoksa_bos(self):  # S2
        t = _transkript(self.sd, [PLAN, "Edit"], ["Read", "Edit", PLAN])
        self.assertEqual(AD.stop_tetik(t, "Bitti.", self.sd, "o1"), "")
        self.assertEqual(AD.stop_karar(t, "Bitti.", self.sd, "o1"), ("", "arac_yok"))

    def test_arac_varsa_eski_sonuc(self):  # S2
        t = _transkript(self.sd, [PLAN, "Edit"], ["Read", "Edit", PLAN, WRAP])
        self.assertEqual(AD.stop_tetik(t, "Bitti.", self.sd, "o1"), "plan_acik")
        self.assertEqual(AD.stop_karar(t, "Bitti.", self.sd, "o1"), ("plan_acik", ""))

    def test_liste_kaydi_yoksa_eski_sonuc(self):  # S2: bilinmiyor
        t = _transkript(self.sd, ["Edit"], None)
        self.assertEqual(AD.stop_tetik(t, "Bitti.", self.sd, "o1"), "degisiklik")
        self.assertEqual(AD.stop_karar(t, "Bitti.", self.sd, "o1"), ("degisiklik", ""))

    def test_aday_yoksa_atlandi_yazilmaz(self):
        t = _transkript(self.sd, ["Read"], ["Read"])
        self.assertEqual(AD.stop_karar(t, "Cevap.", self.sd, "o1"), ("", ""))

    def test_okuyucu_hata_verirse_eski_sonuc(self):  # K-006: yanlış "yok" gerçek ihlali gizlemesin
        t = _transkript(self.sd, ["Edit"], ["Read"])
        with mock.patch("arac_listesi.var_mi", side_effect=RuntimeError("x")):
            self.assertEqual(AD.stop_tetik(t, "Bitti.", self.sd, "o1"), "degisiklik")

    def test_arac_adi_bos_ise_susturmaz(self):  # ad bilinmiyorsa "yok" denemez
        t = _transkript(self.sd, ["Edit"], ["Read"])
        with open(os.path.join(self.sd, "arsiv_dugmesi.json"), "w", encoding="utf-8") as f:
            json.dump({"arac": ""}, f)
        self.assertEqual(AD.stop_tetik(t, "Bitti.", self.sd, "o1"), "degisiklik")

    def test_arac_adi_ayardan_gelir(self):
        self.assertEqual(AD.arac_adi(self.sd), "wrap_up")
        with open(os.path.join(self.sd, "arsiv_dugmesi.json"), "w", encoding="utf-8") as f:
            json.dump({"arac": "kapat"}, f)
        self.assertEqual(AD.arac_adi(self.sd), "kapat")
        t = _transkript(self.sd, ["Edit"], ["Read", WRAP])  # artık "kapat" aranır, yok
        self.assertEqual(AD.stop_tetik(t, "Bitti.", self.sd, "o1"), "")


class HookGunlugu(unittest.TestCase):
    def setUp(self):
        import hook
        self.hook = hook
        self.sd = tempfile.mkdtemp()
        self.addCleanup(os.environ.__setitem__, "ORKESTRA_ARSIV_DUGMESI", os.environ.get("ORKESTRA_ARSIV_DUGMESI", "0"))
        os.environ["ORKESTRA_ARSIV_DUGMESI"] = "1"

    def _gunluk(self):
        yol = os.path.join(self.sd, "gunluk.jsonl")
        if not os.path.exists(yol):
            return []
        with open(yol, encoding="utf-8") as f:
            return [json.loads(s) for s in f if s.strip()]

    def test_arac_yok_block_yok_kural_atlandi_yazilir(self):  # S2
        t = _transkript(self.sd, [PLAN, "Edit"], ["Read", "Edit", PLAN])
        inp = {"transcript_path": t, "last_assistant_message": "Bitti."}
        with mock.patch.object(self.hook.L, "hook_cikti") as c:
            self.hook._arsiv_dugmesi_yanit(self.sd, "o1", inp)
        c.assert_not_called()
        kayitlar = self._gunluk()
        self.assertEqual([k["tur"] for k in kayitlar], ["kural_atlandi"])
        self.assertEqual((kayitlar[0]["kural"], kayitlar[0]["neden"]), ("arsiv_dugmesi", "arac_yok"))

    def test_arac_varsa_ihlal_yazilir_ve_block(self):
        t = _transkript(self.sd, [PLAN, "Edit"], ["Read", "Edit", PLAN, WRAP])
        inp = {"transcript_path": t, "last_assistant_message": "Bitti."}
        with mock.patch.object(self.hook.L, "hook_cikti", side_effect=SystemExit) as c:
            with self.assertRaises(SystemExit):
                self.hook._arsiv_dugmesi_yanit(self.sd, "o1", inp)
        self.assertEqual(c.call_args[0][0]["decision"], "block")
        self.assertEqual([k["tur"] for k in self._gunluk()], ["kural_ihlal"])


if __name__ == "__main__":
    unittest.main()
