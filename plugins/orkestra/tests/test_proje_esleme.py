"""I-215 P4: perspektif başka projenin hafızasından üretilip bu projenin durumuna yazılamaz (S5)."""
import json
import os
import re
import sys
import unittest
from unittest import mock

AD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AD, "..", "scripts"))
sys.path.insert(0, AD)
import onay  # noqa: E402
import perspektif  # noqa: E402
from test_onay import ORKESTRA, Temel  # noqa: E402
import ic_kos  # noqa: E402


def hafiza_yolu(proje):
    """Uygulamanın kullandığı biçim: ~/.claude/projects/<kodlu proje adı>/memory."""
    kodlu = re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(proje))
    return os.path.join(os.path.expanduser("~"), ".claude", "projects", kodlu, "memory")


class EslemeTest(Temel):
    def baska_proje(self):
        return hafiza_yolu(os.path.join(os.path.dirname(self.proje), "baska-proje"))

    def girdi_json(self, klasor):
        os.makedirs(os.path.join(self.sd, "perspektif"), exist_ok=True)
        with open(os.path.join(self.sd, "perspektif", "girdi.json"), "w", encoding="utf-8") as f:
            json.dump({"hafiza": {"klasor": klasor}}, f)

    def test_kendi_hafizasi_ve_alt_klasor_oturumu_kabul_edilir(self):
        self.assertTrue(perspektif.hafiza_projeye_ait(self.proje, hafiza_yolu(self.proje)))
        alt = os.path.join(self.proje, "alt", "klasor")
        self.assertTrue(perspektif.hafiza_projeye_ait(alt, hafiza_yolu(self.proje)))

    def test_baska_projenin_hafizasi_reddedilir(self):
        self.assertFalse(perspektif.hafiza_projeye_ait(self.proje, self.baska_proje()))
        # kodlu ad öneki klasör sınırında olmalı: "C--x-McD" "C--x-McD2"nin sahibi sayılmaz
        self.assertFalse(perspektif.hafiza_projeye_ait(self.proje + "2", hafiza_yolu(self.proje)))

    def test_tanınmayan_yol_ve_kapatma_engellenmez(self):
        self.assertTrue(perspektif.hafiza_projeye_ait(self.proje, os.path.join(self.proje, "ozel", "klasor")))
        with mock.patch.dict(os.environ, {"ORKESTRA_PROJE_ESLEME": "0"}):
            self.assertTrue(perspektif.hafiza_projeye_ait(self.proje, self.baska_proje()))

    def test_s5_girdi_yaz_baska_projenin_hafizasini_reddeder_ve_dosya_yazmaz(self):
        with self.assertRaisesRegex(ValueError, "bu projeye ait değil"):
            perspektif.girdi_yaz(self.sd, self.proje, self.baska_proje())
        self.assertFalse(os.path.exists(os.path.join(self.sd, "perspektif", "girdi.json")))

    def test_s5_cli_girdi_reddeder(self):
        env = dict(os.environ, PYTHONUTF8="1", CLAUDE_PROJECT_DIR=self.proje)
        r = ic_kos.kos([ORKESTRA, "perspektif", "girdi", self.baska_proje()], cwd=self.proje, env=env)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("bu projeye ait değil", r.stderr)

    def test_s5_esitle_baska_projenin_girdisiyle_kayit_acmaz(self):
        self.rapor()
        self.girdi_json(self.baska_proje())
        onay.esitle(self.sd)
        self.assertEqual(onay.liste(self.sd), [])

    def test_s5_esitle_kendi_girdisiyle_ve_girdisiz_eski_yolla_kayit_acar(self):
        self.rapor()
        self.girdi_json(hafiza_yolu(self.proje))
        onay.esitle(self.sd)
        self.assertEqual(len(onay.liste(self.sd)), 9)

    def test_s5_esitle_girdisiz_eski_ruya_yolu_calismaya_devam_eder(self):
        self.rapor()  # sd/ruya/ruya_*.md, girdi.json yok
        onay.esitle(self.sd)
        self.assertEqual(len(onay.liste(self.sd)), 9)

    def test_s5_kapatma_degiskeni_esitlemeyi_acar(self):
        self.rapor()
        self.girdi_json(self.baska_proje())
        with mock.patch.dict(os.environ, {"ORKESTRA_PROJE_ESLEME": "0"}):
            onay.esitle(self.sd)
        self.assertEqual(len(onay.liste(self.sd)), 9)


if __name__ == "__main__":
    unittest.main()
