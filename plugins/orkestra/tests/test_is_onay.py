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
        for m in ("onaylıyorum", "tamam", "Yap", "evet başla", "/onay", "olur, yapalım", "devam et", "Tamam, başla",
                  "y", "Y", "o", "e", "q", "Q", "E.", "onay", "onalıyorum", "evet",
                  "başla", "kabul", "uygula", "yap", "onaylıyorum"):
            self.assertTrue(is_onay.onay_mesaji_mi(m), m)

    def test_onay_degil(self):
        for m in ("handle etmek istiyorum", "tamam mı?", "hayır yapma", "evet ama bekle", "", "x" * 300,
                  "<task-notification>tamam</task-notification>", "planın 2. maddesi neden böyle",
                  "o bir sorun", "e-posta gönder", "yeni iş", "y?", "oo"):
            self.assertFalse(is_onay.onay_mesaji_mi(m), m)


class OnayFiiliCumleIci(unittest.TestCase):
    """I-154: onay fiili cümle içinde geçen doğal söyleyiş onaydır; ret, koşul ve soru değildir."""

    def test_cumle_ici_onay(self):
        for m in ("Planı (P1-P10) onaylıyorum, K3 ve K5 önerildiği gibi; I-149'dan sonra uygula.",
                  "Planı onaylıyorum", "K3 ve K5 önerildiği gibi, onaylıyorum", "Planı onayladım",
                  "Plana onay veriyorum", "Planı kabul ediyorum"):
            self.assertTrue(is_onay.onay_mesaji_mi(m), m)

    def test_cumle_ici_onay_degil(self):
        for m in ("Planı onaylamıyorum", "Planı onaylıyorum ama K3 değişsin", "Planı onaylıyor musun?",
                  "Planı onaylıyorum, fakat P2 eksik", "Planı henüz onaylamadım", "Plan neden böyle"):
            self.assertFalse(is_onay.onay_mesaji_mi(m), m)


class YazmaKapisi(_Onay):
    def test_kod_yazimi_reddedilir(self):
        deny, neden = self.pre("Write", self.kod())
        self.assertTrue(deny)
        self.assertIn("P-016", neden)

    def test_is_belgeleri_serbest(self):
        for ad in ("plan.md", "todo.md", "mevcut_durum_20261018.md"):
            deny, neden = self.pre("Write", os.path.join(self.klasor, ad))
            self.assertNotIn("P-016", neden, ad)  # plan/todo sırası (P-005) ayrı kapıdır

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
        for komut in ("git commit -m x", "git add -A", "git -c safe.directory=* commit -m x",
                      "pip install requests", "pip install -r requirements.txt", "npm install lodash",
                      "python -m pip install x", "uv add httpx", "orkestra is onayla I-001",
                      "echo {} > isler/001-fatura/is.json"):
            self.assertTrue(self.pre("Bash", komut=komut)[0], komut)

    def test_push_regex(self):
        self.assertTrue(is_onay.kabuk_engeli("git push origin main"))

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


class KutuOncesiBaglanti(_Onay):
    """K-003 kaynakta: turu bitiren araçtan önce belge bağlantıları hazır verilir."""

    def belgeler(self):
        for ad in ("plan.md", "todo.md"):
            with open(os.path.join(self.klasor, ad), "w", encoding="utf-8") as f:
                f.write("# x\n")

    def test_hatirlatma_sira_ve_komut_icerir(self):
        m = self.mesaj("handle etmek istiyorum")
        self.assertIn("wrap_up", m)
        self.assertIn("is baglanti " + self.kayit["id"], m)

    def test_ilk_kutu_cagrisi_reddedilir_ve_satir_verir(self):
        self.belgeler()
        deny, neden = self.pre("mcp__ccd_turn__wrap_up", komut="x")
        self.assertTrue(deny)
        self.assertIn("plan dosyası: [plan.md]", neden)
        self.assertIn("to-do dosyası: [todo.md]", neden)

    def test_ikinci_cagri_gecer(self):
        self.belgeler()
        self.pre("mcp__ccd_turn__wrap_up", komut="x")
        self.assertFalse(self.pre("mcp__ccd_turn__wrap_up", komut="x")[0])

    def test_belge_degisince_yeniden_reddedilir(self):
        self.belgeler()
        self.pre("AskUserQuestion", komut="x")
        yol = os.path.join(self.klasor, "plan.md")
        os.utime(yol, (os.path.getmtime(yol) + 10, os.path.getmtime(yol) + 10))
        self.assertTrue(self.pre("AskUserQuestion", komut="x")[0])

    def test_baska_arac_ve_alt_ajan_etkilenmez(self):
        self.belgeler()
        self.assertFalse(self.pre("Bash", komut="ls")[0])
        self.assertFalse(self.pre("mcp__ccd_turn__wrap_up", komut="x", agent_id="a1")[0])

    def test_kapi_kapaliyken_serbest(self):
        self.belgeler()
        os.environ["ORKESTRA_ONAY_KAPISI"] = "0"
        self.assertFalse(self.pre("mcp__ccd_turn__wrap_up", komut="x")[0])


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


class OnayIlkCumlecik(unittest.TestCase):
    """I-138 P15: ret kalıbı yalnız ilk cümlecikte aranır."""

    def test_ornek_onay_true(self):
        self.assertTrue(is_onay.onay_mesaji_mi(
            "Onaylıyorum, yap; ama boş işler otomatik kapanmasın, yalnız listelensin. G-125 yeniden dağıtılsın, G-020 iptal edilsin."))

    def test_ret_ilk_cumlecikte_false(self):
        for m in ("Onaylamıyorum", "Hayır", "evet ama dur"):
            self.assertFalse(is_onay.onay_mesaji_mi(m), m)


class GitEmriKalibi(unittest.TestCase):
    """ADR-0031: commit/push emri tanınır; ad kullanımı, soru ve ret tanınmaz."""

    def test_emirler(self):
        for m in ("commitle pushla", "orkestraya commitle pushla", "commitle pusha", "pusha", "pushla", "commit et",
                  "Commit'le ve push yap", "pushlayalım", "commitleyip pushla"):
            self.assertTrue(is_onay.git_emri_mi(m), m)

    def test_emir_degil(self):
        for m in ("commit mesajı nasıl olmalı", "push yapma", "pushlama", "commitleri göster", "commitler neden çok",
                  "pushla mı?", "hayır commit etme", "", "x" * 300, "<task-notification>commit et</task-notification>",
                  "tamam", "evet"):
            self.assertFalse(is_onay.git_emri_mi(m), m)


class GitIzniKapisi(_Onay):
    def test_emir_turunda_git_kayit_komutlari_gecer(self):
        self.mesaj("commitle pushla")
        for komut in ("git add a.py", "git commit -m x", "git push origin main", "git -c safe.directory=* reset --soft HEAD~2",
                      "git add a.py && git commit -m x"):
            self.assertFalse(self.pre("Bash", komut=komut)[0], komut)

    def test_emir_turunda_diger_yasaklar_kalir(self):
        self.mesaj("commitle pushla")
        for komut in ("git rebase main", "git stash", "pip install x", "orkestra is onayla I-001",
                      "git commit -m x && pip install y", "echo {} > isler/001-fatura/is.json"):
            self.assertTrue(self.pre("Bash", komut=komut)[0], komut)

    def test_emir_is_onayi_vermez_ve_dosya_yazimini_acmaz(self):
        self.mesaj("commitle pushla")
        self.assertEqual(self.durum(), "bekliyor")
        self.assertTrue(self.pre("Write", self.kod())[0])

    def test_sonraki_mesajda_izin_soner(self):
        self.mesaj("commitle pushla")
        self.mesaj("bu ne demek")
        self.assertTrue(self.pre("Bash", komut="git commit -m x")[0])

    def test_emir_yokken_git_reddedilir(self):
        self.mesaj("planı anlat")
        self.assertTrue(self.pre("Bash", komut="git commit -m x")[0])

    def test_kapi_fonksiyonu_izinsiz_eskisi_gibi(self):
        self.assertTrue(is_onay.kabuk_engeli("git commit -m x"))
        self.assertFalse(is_onay.kabuk_engeli("git commit -m x", True))


if __name__ == "__main__":
    unittest.main()
