"""I-224 P6 (R6): iş bağlıyken SessionStart/UserPromptSubmit bağlamına giren tek satırlık durum özeti.
K2: satır en çok 200 karakter; K3: ayar (durum_satiri.json mod) ve ORKESTRA_DURUM_SATIRI=0 kapatır."""
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
import niyet  # noqa: E402
import ork_lib as L  # noqa: E402
import perspektif  # noqa: E402

OTURUM = "durum-satiri-oturum-0001"


class DurumSatiri(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_durum_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for k in ("CLAUDE_PROJECT_DIR", "ORKESTRA_RUYA", "ORKESTRA_PERSPEKTIF", "ORKESTRA_DURUM_SATIRI"):
            os.environ.pop(k, None)
        yol = os.path.join(self.proje, "niyet", "niyet.jsonl")
        os.makedirs(os.path.dirname(yol))
        self._p = [mock.patch.object(niyet, "NIYET_YOLU", yol), mock.patch.object(niyet, "GENEL_DIZIN", os.path.dirname(yol)),
                   mock.patch.object(niyet, "_gecici", return_value=False)]
        for p in self._p:
            p.start()
        # başlık çok uzun ve "ad" içerir: satıra girmemeli
        self.g = is_kaydi.is_ac(self.sd, "Gizli Kişi Adı " + "x" * 300, os.path.join(self.proje, "is0"))
        with open(os.path.join(self.g["klasor"], "todo.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("# T\n\n- [x] P1: a\n- [ ] **P2** Gizli Kişi Adı ile görüş " + "y" * 300 + "\n- [ ] P3: c\n")

    def tearDown(self):
        for p in self._p:
            p.stop()
        self._env.stop()
        shutil.rmtree(self.proje, ignore_errors=True)

    def _bagla(self):
        with open(os.path.join(self.sd, "oturumlar", OTURUM + ".json"), "w", encoding="utf-8") as f:
            json.dump({"is": self.g["id"], "is_baglanma": L.simdi()}, f)

    def _calistir(self, fn, girdi):
        buf = io.StringIO()
        rapor = {"okunmamis_rapor": None, "zamani_geldi": False, "calisiyor": False}
        with contextlib.ExitStack() as st:
            st.enter_context(mock.patch.object(L, "bayatlik", return_value=None))
            st.enter_context(mock.patch.object(perspektif, "durum", return_value=rapor))
            st.enter_context(mock.patch.object(hook, "_yonlendirme_ipucu", return_value=""))
            st.enter_context(mock.patch.object(hook, "_panel_ac_satiri", return_value=""))
            st.enter_context(contextlib.redirect_stdout(buf))
            try:
                fn(dict({"session_id": OTURUM, "cwd": self.proje, "source": "startup"}, **girdi))
            except SystemExit:
                pass
        c = buf.getvalue()
        return json.loads(c)["hookSpecificOutput"]["additionalContext"] if c.strip() else ""

    # ---- satırın kendisi
    def test_bagli_iste_tek_satir_en_cok_200_karakter_ve_ad_yok(self):
        self._bagla()
        s = hook._durum_satiri(self.sd, OTURUM)
        self.assertTrue(s.startswith(f"Durum: {self.g['id']} · "), s)
        self.assertNotIn("\n", s)
        self.assertLessEqual(len(s), hook.DURUM_SATIRI_SINIR)
        self.assertEqual(hook.DURUM_SATIRI_SINIR, 200)
        self.assertNotIn("Gizli", s)  # başlık ve todo metni girmez
        self.assertIn("sıradaki: uygulama P2 (todo 1/3)", s)

    def test_uzun_is_kimliginde_de_200_karakteri_asmaz(self):
        uzun = "I-" + "9" * 400
        with mock.patch.object(hook, "_bagli_is", return_value=uzun), \
                mock.patch.object(is_kaydi, "is_al", return_value={"klasor": self.g["klasor"], "onay": "bekliyor", "mod": "plan"}):
            s = hook._durum_satiri(self.sd, OTURUM)
        self.assertTrue(s.startswith("Durum: I-99"))
        self.assertEqual(len(s), 200)

    def test_onay_bekliyorsa_sirada_kullanici_onayi(self):
        self._bagla()
        if not is_onay.kapi_acik():
            self.skipTest("onay kapısı kapalı")
        is_onay.yaz(self.sd, self.g["id"], is_onay.BEKLIYOR, "test")
        s = hook._durum_satiri(self.sd, OTURUM)
        self.assertIn("onay bekliyor", s)
        self.assertIn("sıradaki: kullanıcı onayı", s)

    def test_bagsiz_oturumda_satir_yok(self):
        self.assertEqual(hook._durum_satiri(self.sd, OTURUM), "")
        self.assertEqual(hook._durum_satiri(self.sd, None), "")

    def test_hata_olursa_bos_doner(self):
        self._bagla()
        with mock.patch.object(is_kaydi, "is_al", side_effect=RuntimeError("bozuk")):
            self.assertEqual(hook._durum_satiri(self.sd, OTURUM), "")

    # ---- kapatma (K3)
    def test_ortam_degiskeni_kapatir(self):
        self._bagla()
        os.environ["ORKESTRA_DURUM_SATIRI"] = "0"
        self.assertEqual(hook._durum_satiri(self.sd, OTURUM), "")

    def test_proje_ayari_kapali_kapatir_acik_acar(self):
        self._bagla()
        yol = os.path.join(self.sd, "durum_satiri.json")
        with open(yol, "w", encoding="utf-8") as f:
            json.dump({"mod": "kapali"}, f)
        self.assertEqual(hook._durum_satiri(self.sd, OTURUM), "")
        with open(yol, "w", encoding="utf-8") as f:
            json.dump({"mod": "acik"}, f)
        self.assertTrue(hook._durum_satiri(self.sd, OTURUM))

    def test_eklenti_ayari_varsayilan_acik(self):
        with open(os.path.join(KOK, "ayarlar", "durum_satiri.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["mod"], "acik")

    # ---- bağlam enjeksiyonu
    def test_user_prompt_submit_baglaminda_satir_var_kapaliyken_yok(self):
        self._bagla()
        up = self._calistir(hook.user_prompt_submit, {"prompt": "devam edelim"})
        satir = [x for x in up.splitlines() if x.startswith("Durum: ")]
        self.assertEqual(len(satir), 1, up)
        self.assertLessEqual(len(satir[0]), 200)
        os.environ["ORKESTRA_DURUM_SATIRI"] = "0"
        up = self._calistir(hook.user_prompt_submit, {"prompt": "devam edelim"})
        self.assertNotIn("Durum: ", up)

    def test_session_start_birinci_satira_eklenir_kapaliyken_yok(self):
        self._bagla()
        ss = self._calistir(hook.session_start, {})
        ilk = ss.splitlines()[0]
        self.assertIn(f"Durum: {self.g['id']} · ", ilk)
        self.assertEqual(sum(x.count("Durum: ") for x in ss.splitlines()), 1)
        os.environ["ORKESTRA_DURUM_SATIRI"] = "0"
        ss = self._calistir(hook.session_start, {})
        self.assertNotIn("Durum: ", ss)


if __name__ == "__main__":
    unittest.main()
