"""ADR-0029: PreToolUse hafıza düzeltme kapısı. 14.10 dizisi: aynı düzeltme notu ayrı Edit'lerle eklenir; ilki geçer, ikincisi reddedilir.
Hepsi geçici projede koşar; kapı hatada serbest (fail-open) kalmalıdır."""
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
import hafiza_duzeltme as HD  # noqa: E402

OTURUM = "hafiza-duzeltme-oturum"
NOT = "(teyidi 13.10'da kapsam daralması olarak düzeltildi)"


class HookHafizaDuzeltme(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_hd_proje_")
        self.ev = tempfile.mkdtemp(prefix="ork_hd_ev_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        self.mem = os.path.join(self.ev, ".claude", "projects", "p", "memory")
        os.makedirs(self.mem)
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for k in ("CLAUDE_PROJECT_DIR", "ORKESTRA_HAFIZA_DUZELTME", "ORKESTRA_IS_KAPISI"):
            os.environ.pop(k, None)
        os.environ["CLAUDE_PROJECT_DIR"] = self.proje
        os.environ["ORKESTRA_SIRA_KAPISI"] = "0"
        os.environ["ORKESTRA_ONAY_KAPISI"] = "0"
        for ad in ("a.md", "b.md", "c.md"):
            self.yaz(ad, f"- ML çöküşü\n- Boyner kapsam\n")

    def tearDown(self):
        self._env.stop()
        shutil.rmtree(self.proje, ignore_errors=True)
        shutil.rmtree(self.ev, ignore_errors=True)

    def yol(self, ad):
        return os.path.join(self.mem, ad)

    def yaz(self, ad, metin):
        with open(self.yol(ad), "w", encoding="utf-8") as f:
            f.write(metin)

    def oku(self, ad):
        with open(self.yol(ad), encoding="utf-8") as f:
            return f.read()

    def pre(self, arac, girdi, **ek):
        g = {"tool_name": arac, "cwd": self.proje, "session_id": OTURUM, "tool_input": girdi}
        g.update(ek)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                hook.pre_tool_use(g)
            except SystemExit:
                pass
        ham = buf.getvalue().strip()
        if not ham:
            return False, "", ham
        h = json.loads(ham.splitlines()[-1]).get("hookSpecificOutput", {})
        return h.get("permissionDecision") == "deny", h.get("permissionDecisionReason", ""), ham

    def duzenle(self, ad, eski, yeni, **ek):
        return self.pre("Edit", {"file_path": self.yol(ad), "old_string": eski, "new_string": yeni}, **ek)

    def uygula(self, ad, eski, yeni):
        self.yaz(ad, self.oku(ad).replace(eski, yeni, 1))

    def test_14_10_dizisi_ilk_edit_gecer_ikinci_reddedilir(self):
        deny1, _, _ = self.duzenle("a.md", "- ML çöküşü", "- ML çöküşü " + NOT)
        self.assertFalse(deny1)
        self.uygula("a.md", "- ML çöküşü", "- ML çöküşü " + NOT)  # ilk Edit uygulandı
        deny2, neden, _ = self.duzenle("b.md", "- ML çöküşü", "- ML çöküşü " + NOT)
        self.assertTrue(deny2)
        self.assertIn("2 kez", neden)

    def test_ret_iletisi_cikis_yolunu_soyler(self):
        self.uygula("a.md", "- ML çöküşü", "- ML çöküşü " + NOT)
        _, neden, _ = self.duzenle("b.md", "- ML çöküşü", "- ML çöküşü " + NOT)
        self.assertIn("ORKESTRA_HAFIZA_DUZELTME=0", neden)
        self.assertIn("[[kaynak]]", neden)

    def test_alt_ajan_ayni_sonuc(self):
        self.uygula("a.md", "- ML çöküşü", "- ML çöküşü " + NOT)
        deny, _, _ = self.duzenle("b.md", "- ML çöküşü", "- ML çöküşü " + NOT, agent_id="agent-1", agent_type="orkestra:hafiza-bakimcisi")
        self.assertTrue(deny)

    def test_kapatma_anahtari(self):
        self.uygula("a.md", "- ML çöküşü", "- ML çöküşü " + NOT)
        os.environ["ORKESTRA_HAFIZA_DUZELTME"] = "0"
        self.assertFalse(self.duzenle("b.md", "- ML çöküşü", "- ML çöküşü " + NOT)[0])

    def test_hafiza_disi_md_etkilenmez(self):
        d = os.path.join(self.proje, "docs", "x.md")
        os.makedirs(os.path.dirname(d))
        with open(d, "w", encoding="utf-8") as f:
            f.write("a\n" + NOT + "\n")
        self.assertFalse(self.pre("Edit", {"file_path": d, "old_string": "a\n", "new_string": "a " + NOT + "\n"})[0])

    def test_write_ile_ikinci_not_reddedilir(self):
        self.uygula("a.md", "- ML çöküşü", "- ML çöküşü " + NOT)
        deny, _, _ = self.pre("Write", {"file_path": self.yol("c.md"), "content": "- ML çöküşü " + NOT + "\n"})
        self.assertTrue(deny)

    def test_multiedit_ayni_dosyada_iki_not(self):
        deny, _, _ = self.pre("MultiEdit", {"file_path": self.yol("a.md"), "edits": [
            {"old_string": "- ML çöküşü", "new_string": "- ML çöküşü " + NOT},
            {"old_string": "- Boyner kapsam", "new_string": "- Boyner kapsam " + NOT}]})
        self.assertTrue(deny)

    def test_tek_not_ve_farkli_not_serbest(self):
        self.assertFalse(self.duzenle("a.md", "- ML çöküşü", "- ML çöküşü (düzeltme: [[klibre-db]])")[0])
        self.uygula("a.md", "- ML çöküşü", "- ML çöküşü (düzeltme: [[klibre-db]])")
        self.assertFalse(self.duzenle("b.md", "- ML çöküşü", "- ML çöküşü (düzeltme: [[baska-kayit]])")[0])

    def test_mevcut_tekrari_artirmayan_duzenleme_serbest(self):
        self.yaz("a.md", "- ML çöküşü " + NOT + "\n")
        self.yaz("b.md", "- ML çöküşü " + NOT + "\n")
        self.assertFalse(self.duzenle("b.md", "- ML çöküşü", "- ML çöküşü kesin")[0])

    def test_eslesmeyen_edit_serbest_birakilir(self):
        self.assertFalse(self.duzenle("a.md", "yok böyle metin", NOT + " " + NOT)[0])

    def test_golge_modu_reddetmez_uyarir(self):
        self.uygula("a.md", "- ML çöküşü", "- ML çöküşü " + NOT)
        with mock.patch.object(HD, "ayar", return_value=dict(HD.ayar(), mod="golge")):
            deny, _, ham = self.duzenle("b.md", "- ML çöküşü", "- ML çöküşü " + NOT)
        self.assertFalse(deny)
        self.assertIn("gölge", ham)

    def test_kapi_istisnasi_serbest(self):
        self.uygula("a.md", "- ML çöküşü", "- ML çöküşü " + NOT)
        with mock.patch.object(HD, "yazim_ihlali", side_effect=RuntimeError("bozuk")):
            self.assertFalse(self.duzenle("b.md", "- ML çöküşü", "- ML çöküşü " + NOT)[0])


class YazimSonrasi(unittest.TestCase):
    def test_edit_tum_gecisler(self):
        self.assertEqual(HD.yazim_sonrasi("Edit", {"old_string": "a", "new_string": "b", "replace_all": True}, "aXa"), "bXb")

    def test_edit_ilk_gecis(self):
        self.assertEqual(HD.yazim_sonrasi("Edit", {"old_string": "a", "new_string": "b"}, "aXa"), "bXa")

    def test_eslesme_yoksa_none(self):
        self.assertIsNone(HD.yazim_sonrasi("Edit", {"old_string": "z", "new_string": "b"}, "aXa"))

    def test_bilinmeyen_arac_none(self):
        self.assertIsNone(HD.yazim_sonrasi("NotebookEdit", {}, "a"))


if __name__ == "__main__":
    unittest.main()
