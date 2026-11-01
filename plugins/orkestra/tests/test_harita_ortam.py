"""Sistem haritası `ortamlar` katmanı (I-249, ADR-0001): codebase bulma, kilit seçimi, ortam yolu, haric, sır, eskime. Geçici projede koşar."""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import harita as H  # noqa: E402
import harita_ortam as O  # noqa: E402

DEGER = "supersecretvalue123"


class Ortamlar(unittest.TestCase):
    def setUp(self):
        self.kok = tempfile.mkdtemp()
        self.sd = os.path.join(self.kok, ".claude", "orkestra")
        os.makedirs(self.sd)
        self.koku = os.path.join(self.kok, "_venvs")
        self.eski = os.environ.get("ORKESTRA_ORTAM_KOKU")
        os.environ["ORKESTRA_ORTAM_KOKU"] = self.koku
        self.yaz("api/requirements.txt", "fastapi==0.1.0\n")
        self.yaz("api/uv.lock", "version = 1\n")
        self.yaz("api/.env", f"API_KEY={DEGER}\n")
        self.yaz("ui/package.json", json.dumps({"dependencies": {"react": "^19"}}))
        self.yaz("ui/package-lock.json", "{}")
        self.yaz("eski/pyproject.toml", '[project]\ndependencies = ["x"]\n')
        self.yaz("calisma/.git", "gitdir: /baska\n")
        self.yaz("calisma/package.json", "{}")
        self.yaz("yayin/package.json", "{}")
        self.yaz("sadece-py/uygulama.py", "print(1)\n")

    def tearDown(self):
        if self.eski is None:
            os.environ.pop("ORKESTRA_ORTAM_KOKU", None)
        else:
            os.environ["ORKESTRA_ORTAM_KOKU"] = self.eski
        shutil.rmtree(self.kok, ignore_errors=True)

    def yaz(self, rel, metin):
        yol = os.path.join(self.kok, rel)
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with open(yol, "w", encoding="utf-8", newline="\n") as f:
            f.write(metin)

    def kayit(self):
        return {r["id"]: r for r in H.oku(self.kok, self.sd, "ortamlar")}

    def test_katman_tanimli(self):
        for sozluk in (H.ADAY, H.TARAYICI):
            self.assertIn("ortamlar", sozluk)
        self.assertIn("ortamlar", H.KATMANLAR)

    def test_codebase_bulunur_calisma_agaci_ve_manifestsiz_yok(self):
        k = self.kayit()
        self.assertEqual(sorted(k), ["ortam:api", "ortam:eski", "ortam:ui", "ortam:yayin"])

    def test_kilit_turleri_ve_yollar(self):
        k = self.kayit()
        self.assertEqual(k["ortam:api"]["kilit_turu"], "uv")
        self.assertEqual(k["ortam:api"]["kilit_dosyasi"], "uv.lock")
        self.assertEqual(k["ortam:eski"]["kilit_turu"], "pip-pyproject")
        self.assertEqual(k["ortam:ui"]["kilit_turu"], "npm-ci")
        self.assertEqual(k["ortam:yayin"]["kilit_turu"], "kilitsiz")
        pad = O.proje_adi(self.kok, O.ayar_oku(self.sd))
        self.assertEqual(k["ortam:api"]["ortam_yolu"], os.path.join(self.koku, pad, "api"))
        self.assertTrue(k["ortam:ui"]["ortam_yolu"].endswith("node_modules"))

    def test_haric_projeden(self):
        with open(os.path.join(self.sd, "ortam.json"), "w", encoding="utf-8") as f:
            json.dump({"haric": ["yayin"], "codebase_veri": {"api": ["demoapp_pg"]}}, f)
        k = self.kayit()
        self.assertNotIn("ortam:yayin", k)
        self.assertEqual(k["ortam:api"]["veri_kaynaklari"], ["demoapp_pg"])

    def test_sir_degeri_yok(self):
        self.kayit()
        for kok, _, dosyalar in os.walk(os.path.join(self.sd, H.KLASOR_ADI)):
            for ad in dosyalar:
                with open(os.path.join(kok, ad), encoding="utf-8") as f:
                    self.assertNotIn(DEGER, f.read())

    def test_ayar_degisince_eskir_ve_yenileme_tutarli(self):
        H.oku(self.kok, self.sd, "ortamlar")
        ilk = H.oku(self.kok, self.sd, "ortamlar")
        with open(os.path.join(self.sd, "ortam.json"), "w", encoding="utf-8") as f:
            json.dump({"haric": ["ui"]}, f)
        self.assertNotIn("ortam:ui", {r["id"] for r in H.oku(self.kok, self.sd, "ortamlar")})
        self.assertIn("ortam:ui", {r["id"] for r in ilk})


if __name__ == "__main__":
    unittest.main()
