"""I-157 P4/P5: onay.esitle girdi parmak izi. Girdi değişmediyse kilit almaz; her girdi değişince yeni kaydı açar.
`py -3.13 -m pytest plugins/orkestra/tests/test_onay_esitle_izi.py`
"""
import json
import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_onay import Temel  # noqa: E402
import onay  # noqa: E402


def _ileri(yol, sn=2):
    """mtime çözünürlüğünden bağımsız: dosyanın zamanını ileri alır."""
    t = time.time() + sn
    os.utime(yol, (t, t))


class EsitleIzi(Temel):
    def setUp(self):
        super().setUp()
        self.kilit_sayisi = 0
        orijinal = onay.L.kilit

        def say(yol, *a, **k):
            self.kilit_sayisi += 1
            return orijinal(yol, *a, **k)

        p = mock.patch.object(onay.L, "kilit", say)
        p.start()
        self.addCleanup(p.stop)

    def anahtarlar(self):
        return {k["anahtar"] for k in onay.liste(self.sd)}

    def test_degismeyen_girdide_ikinci_esitle_kilit_almaz(self):
        self.rapor()
        onay.esitle(self.sd)      # kayıt yazar: izi saklanmaz
        onay.esitle(self.sd)      # kararlı izi saklar
        sayi = self.kilit_sayisi
        onay.esitle(self.sd)
        onay.esitle(self.sd)
        self.assertEqual(self.kilit_sayisi, sayi)

    def test_yeni_rapor_kayit_acar(self):
        onay.esitle(self.sd)
        onay.esitle(self.sd)
        self.assertEqual(self.anahtarlar(), set())
        self.rapor()
        onay.esitle(self.sd)
        self.assertEqual(len(self.anahtarlar()), 9)

    def test_ayni_adli_raporun_icerigi_degisince_kayit_acar(self):
        yol = self.rapor(metin="## 1. Öneriler\n\n1. Birinci\n\nGövde\n")
        onay.esitle(self.sd)
        onay.esitle(self.sd)
        once = self.anahtarlar()
        with open(yol, "w", encoding="utf-8") as f:
            f.write("## 1. Öneriler\n\n1. Birinci\n\nGövde\n\n2. İkinci\n\nGövde 2\n")
        _ileri(yol)
        onay.esitle(self.sd)
        self.assertGreater(len(self.anahtarlar()), len(once))

    def test_skill_klasoru_once_dosya_sonra_gelince_kayit_acar(self):
        onay.esitle(self.sd)
        onay.esitle(self.sd)
        d = os.path.join(self.sd, "onerilen_skill", "yeni-skill")
        os.makedirs(d)
        onay.esitle(self.sd)      # SKILL.md yok: kayıt yok, izi kaydedilir
        onay.esitle(self.sd)
        self.assertNotIn("skill:yeni-skill", self.anahtarlar())
        with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("---\nname: yeni-skill\n---\nGövde")
        _ileri(d)                 # alt dosya eklemek klasör mtime'ını değiştirir; çözünürlük payı
        onay.esitle(self.sd)
        self.assertIn("skill:yeni-skill", self.anahtarlar())

    def test_kural_onerisi_kayit_acar(self):
        onay.esitle(self.sd)
        onay.esitle(self.sd)
        yol = os.path.join(self.sd, "kurallar", "kurallar.json")
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with open(yol, "w", encoding="utf-8") as f:
            json.dump({"kurallar": [{"id": "K-900", "durum": "oneri", "metin": "Deneme kuralı", "neden": "test"}]}, f)
        onay.esitle(self.sd)
        self.assertIn("kural:K-900", self.anahtarlar())

    def test_proje_skills_klasoru_skill_i_eler(self):
        self.skill("var-olan")
        os.makedirs(os.path.join(self.proje, ".claude", "skills", "var-olan"))
        onay.esitle(self.sd)
        onay.esitle(self.sd)
        self.assertNotIn("skill:var-olan", self.anahtarlar())


if __name__ == "__main__":
    unittest.main()
