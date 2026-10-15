"""SessionStart: ana ajan modeli proje ayarından sapıyorsa tek satır uyarı (G-132).

Kaynak kanıtı (K3): SessionStart girdisinde `model` alanı resmi belgede isteğe bağlıdır
(https://code.claude.com/docs/en/hooks; örnek `"model": "claude-opus-5"`; /clear ve oturum kurtarmada gelmeyebilir).
orkestra gunluk.jsonl SessionStart girdisini kaydetmediği için yerelde örnek yok; alan yoksa yedek kaynak
transcript_path'teki son assistant satırının `message.model` değeridir (gerçek örnek: ~/.claude/projects/.../*.jsonl satırı
`"type":"assistant"` ... `"model":"claude-sonnet-5-5"`). İkisi de aşağıda testlidir.
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

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import hook  # noqa: E402
import ork_lib as L  # noqa: E402
import perspektif  # noqa: E402

ETIKET = "UYARI: ana ajan modeli ayar dışı"


class ModelSapma(unittest.TestCase):
    def setUp(self):
        self.proje = tempfile.mkdtemp(prefix="ork_msapma_")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(os.path.join(self.sd, "oturumlar"))
        self.tr = os.path.join(self.proje, "tr.jsonl")
        open(self.tr, "w").close()
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for k in ("CLAUDE_PROJECT_DIR", "ORKESTRA_RUYA", "ORKESTRA_PERSPEKTIF"):
            os.environ.pop(k, None)

    def tearDown(self):
        self._env.stop()
        shutil.rmtree(self.proje, ignore_errors=True)

    def ayar(self, model="claude-sonnet-5-5", ham=None):
        with open(os.path.join(self.proje, ".claude", "settings.json"), "w", encoding="utf-8") as f:
            f.write(ham if ham is not None else json.dumps({"model": model} if model else {}))

    def transkript(self, *modeller):
        with open(self.tr, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "user", "message": {"role": "user", "content": "x"}}) + "\n")
            for m in modeller:
                f.write(json.dumps({"type": "assistant", "message": {"role": "assistant", "model": m}}) + "\n")

    def baglam(self, **girdi):
        rapor = {"okunmamis_rapor": None, "zamani_geldi": False, "calisiyor": False}
        buf = io.StringIO()
        with contextlib.ExitStack() as st:
            st.enter_context(mock.patch.object(L, "bayatlik", return_value=None))
            st.enter_context(mock.patch.object(perspektif, "durum", return_value=rapor))
            st.enter_context(mock.patch.object(hook, "_panel_ac_satiri", return_value=""))
            st.enter_context(contextlib.redirect_stdout(buf))
            try:
                hook.session_start(dict({"session_id": "s1", "cwd": self.proje, "transcript_path": self.tr, "source": "startup"}, **girdi))
            except SystemExit:
                pass
        return json.loads(buf.getvalue())["hookSpecificOutput"]["additionalContext"]

    def sapma_satirlari(self, c):
        return [s for s in c.splitlines() if ETIKET in s]

    # K1
    def test_k1_aile_farkli_tam_bir_satir(self):
        self.ayar("claude-sonnet-5-5")
        s = self.sapma_satirlari(self.baglam(model="claude-opus-5"))
        self.assertEqual(len(s), 1)
        self.assertLessEqual(len(s[0]), 250)
        self.assertIn("claude-opus-5", s[0])
        self.assertIn("claude-sonnet-5-5", s[0])
        self.assertIn("model menüsünden ayar modelini seç", s[0])

    # K2 negatifler
    def test_k2_aile_ayni_tam_kimlik_farkli(self):
        self.ayar("claude-sonnet-5-5")
        self.assertEqual(self.sapma_satirlari(self.baglam(model="claude-sonnet-4-6")), [])

    def test_k2_ayar_yok(self):
        self.assertEqual(self.sapma_satirlari(self.baglam(model="claude-opus-5")), [])

    def test_k2_ayarda_model_alani_yok(self):
        self.ayar(model=None)
        self.assertEqual(self.sapma_satirlari(self.baglam(model="claude-opus-5")), [])

    def test_k2_model_bilgisi_yok(self):
        self.ayar()
        self.assertEqual(self.sapma_satirlari(self.baglam()), [])

    def test_k2_settings_bozuk(self):
        self.ayar(ham="{bozuk json")
        self.assertEqual(self.sapma_satirlari(self.baglam(model="claude-opus-5")), [])

    def test_k2_tanimsiz_aile(self):
        self.ayar("claude-sonnet-5-5")
        self.assertEqual(self.sapma_satirlari(self.baglam(model="baska-model-x")), [])

    # K3 yedek kaynak
    def test_k3_yedek_transkript_son_assistant(self):
        self.ayar("claude-sonnet-5-5")
        self.transkript("claude-sonnet-5-5", "claude-opus-5")
        s = self.sapma_satirlari(self.baglam())
        self.assertEqual(len(s), 1)
        self.assertIn("claude-opus-5", s[0])

    def test_k3_yedek_transkript_ayni_aile(self):
        self.ayar("claude-sonnet-5-5")
        self.transkript("claude-opus-5", "claude-sonnet-5-5")
        self.assertEqual(self.sapma_satirlari(self.baglam()), [])

    def test_k3_girdi_modeli_transkripte_oncelikli(self):
        self.ayar("claude-sonnet-5-5")
        self.transkript("claude-opus-5")
        self.assertEqual(self.sapma_satirlari(self.baglam(model="claude-sonnet-5-5")), [])

    def test_k3_transkript_bozuk_satirlar(self):
        self.ayar("claude-sonnet-5-5")
        with open(self.tr, "w", encoding="utf-8") as f:
            f.write("bozuk\n[1,2]\n")
        self.assertEqual(self.sapma_satirlari(self.baglam()), [])


if __name__ == "__main__":
    unittest.main()
