"""P-016: onay gelmeden uygulamaya geçilmez. Hepsi geçici projede koşar.
Kapı fail-open kalmalı: her hata yolunda hook serbest bırakır.
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
import is_kaydi  # noqa: E402
import is_onay  # noqa: E402

OTURUM = "onay1234567890-oturum"


class _Onay(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_onay_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for k in ("CLAUDE_PROJECT_DIR", "ORKESTRA_RUYA", "ORKESTRA_PERSPEKTIF", "ORKESTRA_IS_KAPISI", "ORKESTRA_ONAY_KAPISI"):
            os.environ.pop(k, None)
        os.environ["CLAUDE_PROJECT_DIR"] = self.proje
        os.environ["ORKESTRA_SIRA_KAPISI"] = "1"
        os.environ["ORKESTRA_DOGRULAMA_KAPISI"] = "0"
        self.klasor = os.path.join(self.proje, "isler", "001-fatura")
        self.kayit = is_kaydi.is_ac(self.sd, "Fatura raporlama", self.klasor)
        with open(os.path.join(self.sd, "oturumlar", OTURUM + ".json"), "w", encoding="utf-8") as f:
            json.dump({"is": self.kayit["id"]}, f)

    def tearDown(self):
        self._env.stop()
        shutil.rmtree(self.proje, ignore_errors=True)

    def durum(self):
        return is_kaydi.is_al(self.sd, self.kayit["id"]).get("onay")

    def alani_sil(self):
        yol = os.path.join(self.klasor, "is.json")
        with open(yol, encoding="utf-8") as f:
            k = json.load(f)
        k.pop("onay")
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(k, f)

    def pre(self, arac, yol=None, komut=None, **ek):
        girdi = {"tool_name": arac, "cwd": self.proje, "session_id": OTURUM,
                 "tool_input": {"file_path": yol, "content": "x"} if yol else {"command": komut or "echo merhaba"}}
        girdi.update(ek)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                hook.pre_tool_use(girdi)
            except SystemExit:
                pass
        ham = buf.getvalue().strip()
        if not ham:
            return False, ""
        h = json.loads(ham.splitlines()[-1]).get("hookSpecificOutput", {})
        return h.get("permissionDecision") == "deny", h.get("permissionDecisionReason", "")

    def mesaj(self, metin):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                hook.user_prompt_submit({"prompt": metin, "session_id": OTURUM, "cwd": self.proje})
            except SystemExit:
                pass
        ham = buf.getvalue().strip()
        return json.loads(ham)["hookSpecificOutput"]["additionalContext"] if ham else ""

    def kod(self):
        return os.path.join(self.proje, "src", "uygulama.py")


class Durum(_Onay):
    def test_yeni_sirali_is_bekliyor_dogar(self):
        self.assertEqual(self.durum(), "bekliyor")

    def test_kapi_kapaliyken_alan_yok(self):
        os.environ["ORKESTRA_ONAY_KAPISI"] = "0"
        k = is_kaydi.is_ac(self.sd, "Başka iş", os.path.join(self.proje, "isler", "002-baska"))
        self.assertNotIn("onay", k)

    def test_sirasiz_is_alan_almaz(self):
        os.environ["ORKESTRA_SIRA_KAPISI"] = "0"
        k = is_kaydi.is_ac(self.sd, "Eski tür iş", os.path.join(self.proje, "isler", "003-eski"))
        self.assertNotIn("onay", k)

    def test_ilk_durum_biten_madde_yoksa_bekliyor(self):
        with open(os.path.join(self.klasor, "todo.md"), "w", encoding="utf-8") as f:
            f.write("- [ ] P1: a\n")
        self.assertEqual(is_onay.ilk_durum(self.klasor), "bekliyor")
        with open(os.path.join(self.klasor, "todo.md"), "w", encoding="utf-8") as f:
            f.write("- [x] P1: a\n- [ ] P2: b\n")
        self.assertEqual(is_onay.ilk_durum(self.klasor), "verildi")


class OnayKalibi(unittest.TestCase):
    def test_onaylar(self):
        for m in ("onaylıyorum", "tamam", "Yap", "evet başla", "/onay", "olur, yapalım", "devam et", "Tamam, başla"):
            self.assertTrue(is_onay.onay_mesaji_mi(m), m)

    def test_onay_degil(self):
        for m in ("handle etmek istiyorum", "tamam mı?", "hayır yapma", "evet ama bekle", "", "x" * 300,
                  "<task-notification>tamam</task-notification>", "planın 2. maddesi neden böyle"):
            self.assertFalse(is_onay.onay_mesaji_mi(m), m)


class YazmaKapisi(_Onay):
    def test_kod_yazimi_reddedilir(self):
        deny, neden = self.pre("Write", self.kod())
        self.assertTrue(deny)
        self.assertIn("P-016", neden)

    def test_is_belgeleri_serbest(self):
        for ad in ("plan.md", "todo.md", "mevcut_durum_20261018.md"):
            self.assertFalse(self.pre("Write", os.path.join(self.klasor, ad))[0], ad)

    def test_adr_serbest(self):
        self.assertFalse(self.pre("Write", os.path.join(self.proje, "adr", "ADR-0001-x.md"))[0])

    def test_is_json_yazilamaz(self):
        self.assertTrue(self.pre("Write", os.path.join(self.klasor, "is.json"))[0])

    def test_alt_ajan_da_yazamaz(self):
        self.assertTrue(self.pre("Write", self.kod(), agent_id="a1", agent_type="orkestra:isci-t2")[0])

    def test_verildi_sonrasi_serbest(self):
        is_onay.yaz(self.sd, self.kayit["id"], "verildi", "test")
        self.assertFalse(self.pre("Write", self.kod())[0])

    def test_kapi_kapali_serbest(self):
        os.environ["ORKESTRA_ONAY_KAPISI"] = "0"
        self.assertFalse(self.pre("Write", self.kod())[0])

    def test_alansiz_eski_is_serbest(self):
        self.alani_sil()
        self.assertFalse(self.pre("Write", self.kod())[0])

    def test_genis_klasor_yalniz_md(self):
        k = dict(self.kayit, klasor=self.proje)
        self.assertEqual(is_onay.yazma_engeli(k, self.proje, os.path.join(self.proje, "notlar.md")), "")
        self.assertNotEqual(is_onay.yazma_engeli(k, self.proje, self.kod()), "")

    def test_merkez_kayit_bozuksa_serbest(self):
        with open(is_kaydi._merkez(self.sd), "w", encoding="utf-8") as f:
            f.write("{bozuk")
        self.assertFalse(self.pre("Write", self.kod())[0])


class KabukKapisi(_Onay):
    def test_yasaklar(self):
        for komut in ("git commit -m x", "git add -A", "git push origin main", "git -c safe.directory=* commit -m x",
                      "pip install requests", "pip install -r requirements.txt", "npm install lodash",
                      "python -m pip install x", "uv add httpx", "orkestra is onayla I-001",
                      "echo {} > isler/001-fatura/is.json"):
            self.assertTrue(self.pre("Bash", komut=komut)[0], komut)

    def test_serbest(self):
        for komut in ("git status", "git diff", "git log --oneline", "ls -la", "echo 'git commit yapma'",
                      "python scripts/test.py", "grep install requirements.txt"):
            self.assertFalse(self.pre("Bash", komut=komut)[0], komut)

    def test_verildi_sonrasi_commit_serbest(self):
        is_onay.yaz(self.sd, self.kayit["id"], "verildi", "test")
        self.assertFalse(self.pre("Bash", komut="git commit -m x")[0])


class KullaniciOnayi(_Onay):
    def test_bekleyen_ise_hatirlatma_eklenir(self):
        m = self.mesaj("handle etmek istiyorum")
        self.assertIn("onay bekliyor", m)
        self.assertEqual(self.durum(), "bekliyor")

    def test_onay_belgeler_eksikse_kaydedilmez(self):
        m = self.mesaj("onaylıyorum")
        self.assertIn("kaydedilmedi", m)
        self.assertEqual(self.durum(), "bekliyor")

    def test_onay_belgeler_hazirsa_verildi(self):
        with mock.patch.object(is_onay, "belge_eksikleri", return_value=[]):
            m = self.mesaj("onaylıyorum")
        self.assertIn("onayladı", m)
        self.assertEqual(self.durum(), "verildi")
        self.assertFalse(self.pre("Write", self.kod())[0])

    def test_onay_degil_mesaj_durumu_degistirmez(self):
        with mock.patch.object(is_onay, "belge_eksikleri", return_value=[]):
            self.mesaj("planın 2. maddesi neden böyle?")
        self.assertEqual(self.durum(), "bekliyor")

    def test_belge_eksikleri_gercek(self):
        self.assertTrue(is_onay.belge_eksikleri(self.klasor))


class IsDevam(_Onay):
    def test_is_devam_alansiz_isi_isaretler(self):
        from komutlar import isler
        self.alani_sil()
        with open(os.path.join(self.klasor, "todo.md"), "w", encoding="utf-8") as f:
            f.write("- [x] P1: a\n- [ ] P2: b\n")
        a = mock.Mock(is_id=self.kayit["id"])
        with mock.patch.object(isler, "sd_gerekli", return_value=self.sd), \
                mock.patch.object(isler, "oturum_id", return_value=OTURUM), \
                contextlib.redirect_stdout(io.StringIO()):
            isler.cmd_is_devam(a)
        self.assertEqual(self.durum(), "verildi")


if __name__ == "__main__":
    unittest.main()
