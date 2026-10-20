"""Sistem haritası `teknolojiler` katmanı (ADR-0017): proje bulma, kategori, md üretimi, sır, çalışma ağacı, eskime. Geçici projede koşar."""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import harita as H  # noqa: E402
import harita_teknoloji as T  # noqa: E402

DEGER = "supersecretvalue123"


class Teknolojiler(unittest.TestCase):
    def setUp(self):
        self.kok = tempfile.mkdtemp()
        self.sd = os.path.join(self.kok, ".claude", "orkestra")
        os.makedirs(self.sd)
        self.yaz("api/requirements.txt", "fastapi==0.1.0\nlangchain-openai>=1.0\nbilinmeyen-paket==2.0\n# yorum\n-r baska.txt\n")
        self.yaz("api/pyproject.toml", '[project]\nrequires-python = ">=3.11"\ndependencies = [\n "sqlalchemy>=2",\n]\n'
                 '[project.optional-dependencies]\ndev = [\n "pytest>=8",\n "ruff",\n]\n')
        self.yaz("api/Dockerfile", "FROM python:3.11-slim AS taban\nFROM taban AS son\nRUN echo ok\n")
        self.yaz("api/.env", f"API_KEY={DEGER}\n")
        self.yaz("api/terraform/main.tf", 'terraform {\n  required_version = ">= 1.5"\n  required_providers {\n'
                 '    azurerm = {\n      source  = "hashicorp/azurerm"\n      version = "~> 3.0"\n    }\n  }\n}\n')
        self.yaz("ui/package.json", json.dumps({"dependencies": {"react": "^19.0.0", "@radix-ui/react-dialog": "^1"},
                                                "devDependencies": {"@types/node": "^20", "jest": "^29"},
                                                "engines": {"node": ">=18"}}))
        self.yaz(".github/workflows/ci.yml", "jobs:\n  b:\n    steps:\n      - uses: actions/checkout@v4\n      - uses: ./yerel\n")
        self.yaz("calisma/.git", "gitdir: /baska/yer\n")
        self.yaz("calisma/package.json", '{"dependencies": {"express": "^4"}}')
        self.yaz("sadece-py/uygulama.py", "print('manifest yok')\n")

    def tearDown(self):
        shutil.rmtree(self.kok, ignore_errors=True)

    def yaz(self, rel, metin):
        yol = os.path.join(self.kok, rel)
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with open(yol, "w", encoding="utf-8", newline="\n") as f:
            f.write(metin)

    def kayit(self):
        return {r["id"]: r for r in H.oku(self.kok, self.sd, "teknolojiler")}

    def test_katman_tanimli(self):
        self.assertIn("teknolojiler", H.KATMANLAR)
        self.assertIn("teknolojiler", H.ADAY)
        self.assertIn("teknolojiler", H.TARAYICI)

    def test_kategoriler(self):
        k = self.kayit()
        self.assertEqual(k["teknoloji:api:fastapi"]["kategori"], "backend")
        self.assertEqual(k["teknoloji:api:langchain-openai"]["kategori"], "llm")
        self.assertEqual(k["teknoloji:api:sqlalchemy"]["kategori"], "veri")
        self.assertEqual(k["teknoloji:api:pytest"]["kategori"], "test_arac")
        self.assertEqual(k["teknoloji:api:bilinmeyen-paket"]["kategori"], "diger")
        self.assertEqual(k["teknoloji:ui:react"]["kategori"], "ui")
        self.assertEqual(k["teknoloji:ui:@radix-ui/react-dialog"]["kategori"], "ui")
        self.assertEqual(k["teknoloji:ui:@types/node"]["kategori"], "test_arac")

    def test_surum_ve_kaynak(self):
        k = self.kayit()
        self.assertEqual(k["teknoloji:api:fastapi"]["surum"], "==0.1.0")
        self.assertEqual(k["teknoloji:api:python"]["surum"], "3.11-slim")
        self.assertEqual(k["teknoloji:api:azurerm"]["surum"], "~>3.0")
        self.assertIn("api/requirements.txt", k["teknoloji:api:fastapi"]["yer"])
        self.assertEqual(k["teknoloji:ui:node"]["surum"], ">=18")

    def test_altyapi_ve_is_akisi(self):
        k = self.kayit()
        self.assertEqual(k["teknoloji:api:terraform"]["kategori"], "altyapi")
        self.assertEqual(k["teknoloji:api:azurerm"]["kategori"], "altyapi")
        self.assertIn("teknoloji:.:actions/checkout", k)  # iş akışı kökte, manifest atası yok
        self.assertNotIn("teknoloji:.:./yerel", k)

    def test_calisma_agaci_ve_manifestsiz_proje_sayilmaz(self):
        k = self.kayit()
        self.assertNotIn("teknoloji:calisma:express", k)
        self.assertIn("teknoloji-haric:calisma", k)
        self.assertFalse([i for i in k if i.startswith("teknoloji-proje:sadece-py")])

    def test_markdown_uretilir(self):
        H.yenile(self.kok, self.sd)
        klasor = os.path.join(H.klasor_yolu(self.sd), "teknolojiler")
        kok_md = os.path.basename(self.kok) + ".md"  # kökteki iş akışı manifestsiz proje olur
        self.assertEqual(sorted(os.listdir(klasor)), sorted(["README.md", "api.md", "ui.md", kok_md]))
        with open(os.path.join(klasor, "README.md"), encoding="utf-8") as f:
            readme = f.read()
        self.assertIn("[api](api.md)", readme)
        self.assertIn("1 çalışma ağacı proje sayılmadı", readme)
        self.assertIn("`fastapi`", readme)
        with open(os.path.join(klasor, "ui.md"), encoding="utf-8") as f:
            ui = f.read()
        self.assertIn("## 1. UI (arayüz)", ui)
        self.assertNotIn("`fastapi`", ui)

    def test_sir_degeri_yazilmaz(self):
        H.yenile(self.kok, self.sd)
        for dizin, _, dosyalar in os.walk(H.klasor_yolu(self.sd)):
            for ad in dosyalar:
                with open(os.path.join(dizin, ad), encoding="utf-8") as f:
                    self.assertNotIn(DEGER, f.read(), ad)

    def test_manifest_degisince_katman_eskir_ve_md_yenilenir(self):
        H.yenile(self.kok, self.sd)
        self.assertNotIn("teknolojiler", H.denetle(self.kok, self.sd)["eskimis"])
        self.yaz("ui/package.json", json.dumps({"dependencies": {"vue": "^3"}}))
        self.assertIn("teknolojiler", H.denetle(self.kok, self.sd)["eskimis"])
        H.yenile(self.kok, self.sd)
        with open(os.path.join(H.klasor_yolu(self.sd), "teknolojiler", "ui.md"), encoding="utf-8") as f:
            self.assertIn("`vue`", f.read())

    def test_kimlik_plan_kapisi_icin_kullanilabilir(self):
        H.yenile(self.kok, self.sd)
        self.assertIn("teknoloji:api:fastapi", H.kayit_kimlikleri(self.sd))

    def test_silinen_md_yeniden_uretilir(self):
        H.yenile(self.kok, self.sd)
        readme = os.path.join(H.klasor_yolu(self.sd), "teknolojiler", "README.md")
        os.remove(readme)
        H.yenile(self.kok, self.sd)
        self.assertTrue(os.path.exists(readme))

    def test_kategori_oncelik(self):
        ayar = {"paketler": {"x": "ui"}, "onekler": {"x-": "ai", "x-ek-": "llm"}}
        self.assertEqual(T.kategori("x", ayar=ayar), "ui")
        self.assertEqual(T.kategori("x-ek-1", ayar=ayar), "llm")
        self.assertEqual(T.kategori("x-baska", ayar=ayar), "ai")
        self.assertEqual(T.kategori("y", "altyapi", ayar=ayar), "altyapi")


if __name__ == "__main__":
    unittest.main()
