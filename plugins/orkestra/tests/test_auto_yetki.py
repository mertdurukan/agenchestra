"""/auto yetkisi ve soru yasağı (ADR-0086, I-233): mod-duyarlı izin kapısı, soru reddi, özerklik sözleşmesi, karar kaydı.

`auto` modu yalnız bağlı işin is.json `mod` alanından okunur; her yolda `plan` davranışı değişmez.
"""
import base64
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
sys.path.insert(0, os.path.join(KOK, "scripts", "komutlar"))
import hook as H  # noqa: E402
import is_onay  # noqa: E402
import izin_politikasi as IP  # noqa: E402
from komutlar import isler  # noqa: E402

MCP_YAZ = "mcp__github__create_pull_request"
MCP_JIRA = "mcp__73d9f9eb-9d44-4ce4-b615-490c4b090ae4__createJiraIssue"
MCP_YIKICI = "mcp__73d9f9eb-9d44-4ce4-b615-490c4b090ae4__executeDestructive"


def kabuk(komut, auto, arac="Bash"):
    with mock.patch.object(IP, "_auto_modu", return_value=auto), \
            mock.patch.object(IP, "_onay_kaydi_var", return_value=False):
        return IP.karar(arac, {"command": komut}, sd="x", oturum="o")[0]


def mcp(arac, auto):
    with mock.patch.object(IP, "_auto_modu", return_value=auto):
        return IP.karar(arac, {}, sd="x", oturum="o")[0]


class IzinKapisi(unittest.TestCase):
    def setUp(self):
        self._ort = os.environ.get("ORKESTRA_IZIN")
        os.environ["ORKESTRA_IZIN"] = "genis"

    def tearDown(self):
        if self._ort is None:
            os.environ.pop("ORKESTRA_IZIN", None)
        else:
            os.environ["ORKESTRA_IZIN"] = self._ort

    def test_auto_askleri_acar(self):
        for k in ("git push origin main", "gh pr create --title x", "gh issue comment 3 --body y"):
            self.assertEqual(kabuk(k, True), "allow", k)
        self.assertEqual(mcp(MCP_YAZ, True), "allow")
        self.assertEqual(mcp(MCP_JIRA, True), "allow")

    def test_plan_modu_degismez(self):
        for k in ("git push origin main", "gh pr create --title x"):
            self.assertEqual(kabuk(k, False), "ask", k)
        self.assertEqual(mcp(MCP_YAZ, False), "ask")
        self.assertEqual(mcp(MCP_JIRA, False), "ask")

    def test_deny_sinifi_auto_da_kalir(self):
        for k in ("git push --force", "git push -f origin main", "git push origin --delete eski", "git push --mirror"):
            self.assertEqual(kabuk(k, True), "deny", k)

    def test_kalici_silme_auto_da_reddedilir(self):
        self.assertEqual(mcp(MCP_YIKICI, True), "deny")
        self.assertEqual(kabuk("gh repo delete x/y --yes", True), "deny")
        self.assertEqual(kabuk("gh release delete v1", True), "deny")

    def test_kodlanmis_powershell(self):
        def enc(s):
            return "powershell -EncodedCommand " + base64.b64encode(s.encode("utf-16-le")).decode()
        self.assertEqual(kabuk(enc("Get-Date"), True, "PowerShell"), "allow")
        self.assertEqual(kabuk(enc("git push --force origin main"), True, "PowerShell"), "deny")
        self.assertEqual(kabuk("powershell -EncodedCommand ####", True, "PowerShell"), "deny")
        self.assertEqual(kabuk(enc("Get-Date"), False, "PowerShell"), "ask")

    def test_okuma_araci_etkilenmez(self):
        self.assertIsNone(mcp("mcp__github__list_issues", True))
        self.assertEqual(kabuk("git status", True), "allow")


class ModOkuma(unittest.TestCase):
    def _mod(self, kayit, is_id="I-1", **kw):
        with mock.patch.object(is_onay, "_bagli_is_id", return_value=is_id), \
                mock.patch("is_kaydi.is_al", return_value=kayit):
            return IP._auto_modu("sd", "oturum", **kw)

    def test_auto_isi_true(self):
        self.assertTrue(self._mod({"mod": "auto"}))

    def test_plan_ve_modsuz_false(self):
        self.assertFalse(self._mod({"mod": "plan"}))
        self.assertFalse(self._mod({}))

    def test_bagli_is_yoksa_false(self):
        self.assertFalse(self._mod({"mod": "auto"}, is_id=None))

    def test_okunamayinca_false(self):
        with mock.patch.object(is_onay, "_bagli_is_id", side_effect=OSError):
            self.assertFalse(IP._auto_modu("sd", "oturum"))

    def test_oturum_yok_false(self):
        self.assertFalse(IP._auto_modu("sd", None))
        self.assertFalse(IP._auto_modu(None, "o"))

    def test_baska_oturumun_isi_sizmaz(self):
        # oturum A auto işe bağlı, oturum B bağsız: B için False
        def bagli(sd, oturum):
            return "I-1" if oturum == "A" else None
        with mock.patch.object(is_onay, "_bagli_is_id", side_effect=bagli), \
                mock.patch("is_kaydi.is_al", return_value={"mod": "auto"}):
            self.assertTrue(IP._auto_modu("sd", "A"))
            self.assertFalse(IP._auto_modu("sd", "B"))

    def test_kapatma_degiskeni(self):
        with mock.patch.dict(os.environ, {"ORKESTRA_AUTO_YETKI": "0"}):
            self.assertFalse(self._mod({"mod": "auto"}))


class Reddedildi(Exception):
    pass


def soru(arac, girdi, auto, aid=None, oturum="o"):
    def rd(neden):
        raise Reddedildi(neden)
    with mock.patch.object(IP, "_auto_modu", return_value=auto), mock.patch.object(H, "reddet", side_effect=rd):
        H._auto_soru_kapisi(arac, girdi, "sd", oturum, aid)


class SoruYasagi(unittest.TestCase):
    def test_auto_askuserquestion_reddedilir(self):
        with self.assertRaises(Reddedildi):
            soru("AskUserQuestion", {"questions": []}, True)

    def test_plan_askuserquestion_gecer(self):
        soru("AskUserQuestion", {"questions": []}, False)

    def test_auto_wrap_up_ask_reddedilir_asksiz_gecer(self):
        with self.assertRaises(Reddedildi):
            soru("mcp__ccd_turn__wrap_up", {"recap": "x", "ask": "Push?"}, True)
        with self.assertRaises(Reddedildi):
            soru("wrap_up", {"recap": "x", "ask": "Push?"}, True)
        soru("mcp__ccd_turn__wrap_up", {"recap": "x"}, True)
        soru("mcp__ccd_turn__wrap_up", {"recap": "x", "ask": "  "}, True)

    def test_plan_wrap_up_ask_gecer(self):
        soru("mcp__ccd_turn__wrap_up", {"recap": "x", "ask": "Push?"}, False)

    def test_alt_ajan_ve_oturumsuz_muaf(self):
        soru("AskUserQuestion", {}, True, aid="alt1")
        soru("AskUserQuestion", {}, True, oturum=None)

    def test_ilgisiz_arac_gecer(self):
        soru("Bash", {"command": "ls"}, True)

    def test_mod_hatasinda_serbest(self):
        with mock.patch.object(IP, "_auto_modu", side_effect=RuntimeError):
            H._auto_soru_kapisi("AskUserQuestion", {}, "sd", "o", None)


class Sozlesme(unittest.TestCase):
    def test_mod_mesaji_auto_ve_plan(self):
        self.assertEqual(is_onay.mod_mesaji("/auto bir iş yap"), "auto")
        self.assertEqual(is_onay.mod_mesaji("/orkestra:auto bir iş yap"), "auto")
        self.assertEqual(is_onay.mod_mesaji("/plan bir iş yap"), "plan")
        self.assertIsNone(is_onay.mod_mesaji("sıradan mesaj"))

    def test_sozlesme_metni(self):
        for s in ("ADR-0086", "Otomatik kararlar", "Kullanıcıya kalanlar", "soru sorma"):
            self.assertIn(s, H._AUTO_SOZLESME)

    def test_user_prompt_submit_kaynagi_yalniz_autoda_ekler(self):
        kaynak = open(os.path.join(KOK, "scripts", "hook.py"), encoding="utf-8").read()
        self.assertIn('if yeni_mod == "auto":\n                        parcalar.append(_AUTO_SOZLESME)', kaynak)


class KararKaydi(unittest.TestCase):
    def setUp(self):
        self.klasor = tempfile.mkdtemp()
        with open(os.path.join(self.klasor, "is.json"), "w", encoding="utf-8") as f:
            json.dump({"mod": "auto"}, f)

    def test_eksik_bolum_golgede_engellemez(self):
        metin = "## Plandan sapmalar\nYok\n\n## Kullanıcıya kalanlar\nYok\n"
        self.assertIsNone(isler._auto_ozet_eksigi(self.klasor, metin))
        with open(os.path.join(self.klasor, "gunluk.jsonl"), encoding="utf-8") as f:
            self.assertIn("auto_kararlar", f.read())

    def test_bolum_varsa_gunluk_yazilmaz(self):
        metin = "## Plandan sapmalar\nYok\n\n## Kullanıcıya kalanlar\nYok\n\n## Otomatik kararlar\n- push edildi\n"
        self.assertIsNone(isler._auto_ozet_eksigi(self.klasor, metin))
        self.assertFalse(os.path.exists(os.path.join(self.klasor, "gunluk.jsonl")))

    def test_ihlal_modunda_engeller(self):
        import kapi_mod as KM
        with mock.patch.object(KM, "mod", return_value="ihlal"):
            sonuc = isler._auto_ozet_eksigi(self.klasor, "## Plandan sapmalar\nYok\n\n## Kullanıcıya kalanlar\nYok\n")
        self.assertIn("Otomatik kararlar", sonuc or "")

    def test_plan_isi_muaf(self):
        with open(os.path.join(self.klasor, "is.json"), "w", encoding="utf-8") as f:
            json.dump({"mod": "plan"}, f)
        self.assertIsNone(isler._auto_ozet_eksigi(self.klasor, "## Özet\nx\n"))


if __name__ == "__main__":
    unittest.main()
