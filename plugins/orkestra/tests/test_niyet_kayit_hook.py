"""G-091: kayıtlı niyet olan oturumda UserPromptSubmit 'kayıtlı niyet yok' demez.

Kök neden: niyet.son_niyet() niyet+sonuc kayıtlarının SONUNCUSUNU döndürür; `orkestra niyet --sonuc`
yazılmışsa son kayıt tur=sonuc olur ve baglam_metni/son_baglam onu "niyet yok" sayar.
Gerçek niyet.jsonl'a dokunmaz.
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import niyet  # noqa: E402
import hook  # noqa: E402
import ork_lib as L  # noqa: E402

PROJE = "C:/proje_deneme"
YOK = "kayıtlı niyet yok"


class NiyetKayitHook(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.yol = os.path.join(self.t.name, "niyet.jsonl")
        p = mock.patch.object(niyet, "NIYET_YOLU", self.yol)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.t.cleanup)

    def yaz(self, oturum, tur, **alan):
        with open(self.yol, "a", encoding="utf-8") as f:
            f.write(json.dumps({"zaman": "2026-10-15T10:00:00+03:00", "oturum": oturum, "proje": PROJE, "tur": tur, **alan}) + "\n")

    def hook_baglami(self, oturum):
        """user_prompt_submit'in ana ajana verdiği bağlam metni."""
        cikti = []
        sd = os.path.join(self.t.name, "durum")
        os.makedirs(sd, exist_ok=True)
        with mock.patch.object(hook.L, "durum_dizini", return_value=sd), \
                mock.patch.object(hook.L, "hook_cikti", side_effect=cikti.append), \
                mock.patch.object(hook, "asili_uyari", return_value=""), \
                mock.patch.object(hook, "_yonlendirme_ipucu", return_value=""):
            hook.user_prompt_submit({"session_id": oturum, "cwd": PROJE, "prompt": "merhaba"})
        return "\n".join(c["hookSpecificOutput"]["additionalContext"] for c in cikti if c and "hookSpecificOutput" in c)

    def niyetler(self, oturum):
        return [k for k in L.jsonl_oku(self.yol) if k.get("oturum") == oturum and k.get("tur") == "niyet"]

    def test_hook_modele_niyet_talimati_vermez(self):
        # P2: niyet hook içinde yazılır; bağlamda `orkestra niyet` yönergesi ve 'kayıtlı niyet' satırı yoktur
        b = self.hook_baglami("o1")
        self.assertNotIn("orkestra niyet", b)
        self.assertNotIn(YOK, b)
        self.assertNotIn("Kayıtlı niyet:", b)

    def test_niyetsiz_oturumda_hook_niyet_yazar(self):
        self.hook_baglami("o1")
        k = self.niyetler("o1")
        self.assertEqual(len(k), 1)
        self.assertEqual(k[0]["ne"], "merhaba")
        self.assertEqual(k[0]["neden"], "kullanıcı isteği")

    def test_kayitli_oturumda_ikinci_niyet_yazilmaz(self):
        self.yaz("o1", "niyet", ne="iş a", neden="hedef b")
        self.hook_baglami("o1")
        self.assertEqual(len(self.niyetler("o1")), 1)

    def test_sonuc_yazildiktan_sonra_da_niyet_gorunur(self):
        # G-091: niyet → sonuc sırası 'kayıtlı niyet yok' demez (niyet.son_baglam)
        self.yaz("o1", "niyet", ne="iş a", neden="hedef b", baglam="ACMECO/01_x")
        self.yaz("o1", "sonuc", sonuc="bitti")
        self.hook_baglami("o1")
        self.assertEqual(len(self.niyetler("o1")), 1)
        self.assertEqual(niyet.son_baglam("o1"), "ACMECO/01_x")

    def test_yalniz_sonuc_olan_oturumda_yok_satiri_surer(self):
        self.yaz("o2", "sonuc", sonuc="bitti")
        self.assertIn(YOK, niyet.baglam_metni("o2"))


if __name__ == "__main__":
    unittest.main()
