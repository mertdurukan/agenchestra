"""G-152 P4-P5: bağsız oturum yazma kapısı (pre_tool_use). Hepsi geçici projede koşar.
Kapı yanlış kurulursa tüm yazma durur: her hata yolunda hook açık (fail-open) kalmalıdır.
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

OTURUM = "kapi1234567890-oturum"


class _Kapi(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_kapi_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for k in ("CLAUDE_PROJECT_DIR", "ORKESTRA_RUYA", "ORKESTRA_PERSPEKTIF", "ORKESTRA_IS_KAPISI"):
            os.environ.pop(k, None)
        os.environ["CLAUDE_PROJECT_DIR"] = self.proje
        os.environ["ORKESTRA_SIRA_KAPISI"] = "0"  # sıra kapısı bu testlerin konusu değil
        self.a = is_kaydi.is_ac(self.sd, "Fatura raporlama entegrasyonu", os.path.join(self.proje, "isler", "001-fatura"))
        self.b = is_kaydi.is_ac(self.sd, "Kampanya takvimi düzenleme", os.path.join(self.proje, "isler", "002-kampanya"))

    def tearDown(self):
        self._env.stop()
        shutil.rmtree(self.proje, ignore_errors=True)

    def baglan(self, kayit=None, oid=OTURUM):
        kayit = kayit or self.a
        with open(os.path.join(self.sd, "oturumlar", oid + ".json"), "w", encoding="utf-8") as f:
            json.dump({"is": kayit["id"]}, f)

    def pre(self, arac, yol=None, **ek):
        """(deny_mi, red_metni, ham_çıktı)"""
        girdi = {"tool_name": arac, "cwd": self.proje, "session_id": OTURUM,
                 "tool_input": {"file_path": yol, "content": "x"} if yol else {"command": "echo merhaba"}}
        girdi.update(ek)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                hook.pre_tool_use(girdi)
            except SystemExit:
                pass
        ham = buf.getvalue().strip()
        if not ham:
            return False, "", ham
        o = json.loads(ham.splitlines()[-1])
        h = o.get("hookSpecificOutput", {})
        return h.get("permissionDecision") == "deny", h.get("permissionDecisionReason", ""), ham

    def kod(self, ad="uygulama.py"):
        return os.path.join(self.proje, "src", ad)


class BagsizYazmaReddi(_Kapi):
    def test_bagsiz_write_reddedilir(self):
        deny, neden, _ = self.pre("Write", self.kod())
        self.assertTrue(deny)

    def test_yazan_her_arac_reddedilir(self):
        for arac in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
            with self.subTest(arac=arac):
                self.assertTrue(self.pre(arac, self.kod())[0])

    def test_red_metni_iki_secenegi_ve_en_yakin_isleri_soyler(self):
        deny, neden, _ = self.pre("Write", self.kod())
        self.assertTrue(deny)
        self.assertIn("orkestra is devam", neden)
        self.assertIn("orkestra is ac", neden)
        self.assertIn("--klasor", neden)
        self.assertIn(self.a["id"], neden)
        self.assertIn(self.b["id"], neden)

    def test_oturum_dosyasi_olmayan_oturum_bagsizdir(self):
        self.assertFalse(os.path.exists(os.path.join(self.sd, "oturumlar", OTURUM + ".json")))
        self.assertTrue(self.pre("Write", self.kod())[0])

    def test_oturum_dosyasi_is_alani_bos_bagsizdir(self):
        with open(os.path.join(self.sd, "oturumlar", OTURUM + ".json"), "w", encoding="utf-8") as f:
            json.dump({"is": None}, f)
        self.assertTrue(self.pre("Write", self.kod())[0])

    def test_bagli_yazma_serbest(self):
        self.baglan()
        self.assertFalse(self.pre("Write", self.kod())[0])
        self.assertFalse(self.pre("Edit", self.kod())[0])

    def test_bagli_baska_oturum_bu_oturumu_serbest_birakmaz(self):
        self.baglan(oid="baska-oturum")
        self.assertTrue(self.pre("Write", self.kod())[0])


class Muafiyetler(_Kapi):
    def test_alt_ajan_cagrisi_muaf(self):
        self.assertFalse(self.pre("Write", self.kod(), agent_id="a123456", agent_type="orkestra:isci")[0])

    def test_durum_dizini_alti_muaf(self):
        self.assertFalse(self.pre("Write", os.path.join(self.sd, "notlar", "x.json"))[0])

    def test_salt_okuma_araclari_muaf(self):
        for arac in ("Read", "Grep", "Glob"):
            with self.subTest(arac=arac):
                self.assertFalse(self.pre(arac, self.kod())[0])

    def test_bash_muaf(self):
        self.assertFalse(self.pre("Bash")[0])

    def test_kapi_env_ile_kapatilir(self):
        os.environ["ORKESTRA_IS_KAPISI"] = "0"
        self.assertFalse(self.pre("Write", self.kod())[0])

    def test_kapi_env_baska_degerde_acik_kalir(self):
        os.environ["ORKESTRA_IS_KAPISI"] = "1"
        self.assertTrue(self.pre("Write", self.kod())[0])

    def test_orkestrasiz_proje_serbest(self):
        bos = tempfile.mkdtemp(prefix="ork_bos_")
        try:
            os.environ["CLAUDE_PROJECT_DIR"] = bos
            deny, _, _ = self.pre("Write", os.path.join(bos, "x.py"), cwd=bos)
            self.assertFalse(deny)
        finally:
            shutil.rmtree(bos, ignore_errors=True)


class FailOpen(_Kapi):
    def test_is_listesi_istisnasinda_cagri_serbest(self):
        with mock.patch.object(is_kaydi, "is_liste", side_effect=RuntimeError("patladı")):
            self.assertFalse(self.pre("Write", self.kod())[0])

    def test_bozuk_oturum_dosyasinda_hook_cokmez(self):
        with open(os.path.join(self.sd, "oturumlar", OTURUM + ".json"), "w", encoding="utf-8") as f:
            f.write("{{bozuk")
        # çökmemeli: çıktı ya boş ya geçerli JSON (pre() ayrıştırır)
        self.pre("Write", self.kod())

    def test_bozuk_isler_json_ile_hook_cokmez(self):
        with open(os.path.join(self.sd, "isler.json"), "w", encoding="utf-8") as f:
            f.write("{bozuk")
        self.pre("Write", self.kod())


class PlanTodoYazimi(_Kapi):
    """K6: plan.md / todo.md yazımı da aynı kapıya girer."""

    def _belge(self, ad, klasor=None):
        return os.path.join(klasor or self.a["klasor"], ad)

    def test_bagsiz_plan_yazamaz(self):
        deny, neden, _ = self.pre("Write", self._belge("plan.md"))
        self.assertTrue(deny)
        self.assertIn("orkestra is devam", neden)

    def test_bagsiz_todo_yazamaz(self):
        self.assertTrue(self.pre("Write", self._belge("todo.md"))[0])

    def test_bagsiz_proje_koku_todo_yazamaz(self):
        self.assertTrue(self.pre("Edit", os.path.join(self.proje, "todo.md"))[0])

    def test_bagli_plan_ve_todo_yazabilir(self):
        self.baglan()
        self.assertFalse(self.pre("Write", self._belge("plan.md"))[0])
        self.assertFalse(self.pre("Write", self._belge("todo.md"))[0])

    def test_bagli_baska_isin_klasorune_yazma_kapida_degil(self):
        # bağlı oturumda kapı devre dışı: mevcut davranış (alan uyarısı engellemez) sürer
        self.baglan()
        self.assertFalse(self.pre("Write", self._belge("plan.md", self.b["klasor"]))[0])

    def test_alt_ajan_plan_yazabilir(self):
        self.assertFalse(self.pre("Write", self._belge("plan.md"), agent_id="a123456")[0])


if __name__ == "__main__":
    unittest.main()
