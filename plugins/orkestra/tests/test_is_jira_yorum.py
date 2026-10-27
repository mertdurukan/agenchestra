"""ADR-0091 (P4): `orkestra is jira-yorum` çalışma özetinden altı alanlı Jira Done yorumunu model çağırmadan türetir.

Fixture PE-640 B1 + Teslim metnidir (test_sef_ozeti). CLI ic_kos ile süreç içinde koşar.
"""
import ast
import datetime
import json
import os
import socket
import sys
import tempfile
import unittest
from unittest import mock

AD = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(AD, "..", "scripts")
ORKESTRA = os.path.join(SCRIPTS, "orkestra.py")
sys.path.insert(0, AD)
sys.path.insert(0, SCRIPTS)

import ic_kos  # noqa: E402
import is_jira_yorum as JY  # noqa: E402
import test_sef_ozeti as SO  # noqa: E402  (fixture sabitleri; sınıflar bu modüle alınmaz)

PE640 = SO.YENI_B1 + SO.HARITA + SO.TESLIM_B1
BEKLENEN = (
    "- **Sonuç:** Kısmen. Kod, test ve ölçüm tamam; entegrasyon testi VPN kapalı olduğu için koşulmadı ve sütun anlamı "
    "platform sahibinden teyit bekliyor. [Doğrulandı] Araç `fact_replenishment_report.forecast_quantity_1/2` ve "
    "`replenishment_quantity` alanlarını okur; model alanları kaldırıldı. 3912 test geçti.\n"
    "- **Değişiklik:** PR açılmadı; push ve PR kararı kullanıcıda.\n"
    "- **Test:** `pytest tests/unit tests/contract` 3912 passed, 1 skipped; entegrasyon testi çalışmadı.\n"
    "- **Deploy:** çıkmadı; PR ve sütun anlamı teyidi bekliyor.\n"
    "- **Geri alma:** canlıya değişiklik çıkmadı.\n"
    "- **Not:** Entegrasyon testi: kopya sunucuya bağlanılamadı (VPN). Sütun anlamı teyidi: platform sahibi; "
    "ADR-0011 bu teyide kadar Önerildi.\n"
)
BOS_TESLIM = "\n**Teslim:**\n\n<!-- doldur -->\n\n- **Değişiklik:** \n- **Test:** \n- **Deploy:** \n- **Geri alma:** \n"


def _ag_yasak(*a, **k):
    raise AssertionError("ağ çağrısı yapıldı")


class Uret(unittest.TestCase):
    def test_pe640_alti_alan_birebir(self):
        yorum, neden = JY.uret(PE640)
        self.assertIsNone(neden)
        self.assertEqual(yorum, BEKLENEN)

    def test_acik_kalanlar_bos_not_yok(self):
        metin = PE640.replace("- Entegrasyon testi: kopya sunucuya bağlanılamadı (VPN).\n", "").replace(
            "- Sütun anlamı teyidi: platform sahibi; ADR-0011 bu teyide kadar Önerildi.\n", "")
        yorum, _ = JY.uret(metin)
        self.assertTrue(yorum.endswith("- **Not:** Yok\n"), yorum)

    def test_teslim_bos_eksik_alanlar_adiyla(self):
        yorum, neden = JY.uret(SO.YENI_B1 + SO.HARITA + BOS_TESLIM)
        self.assertIsNone(yorum)
        self.assertEqual(neden, "eksik: Değişiklik, Test, Deploy, Geri alma")

    def test_teslim_yok_eksik_alanlar_adiyla(self):
        yorum, neden = JY.uret(SO.YENI_B1 + SO.HARITA)
        self.assertIsNone(yorum)
        self.assertEqual(neden, "eksik: Değişiklik, Test, Deploy, Geri alma")

    def test_alt_satir_bos_yalniz_o_adlandirilir(self):
        metin = PE640.replace("- **Test:** `pytest tests/unit tests/contract` 3912 passed, 1 skipped; entegrasyon testi "
                              "çalışmadı.\n", "- **Test:** \n").replace(
            "- **Deploy:** çıkmadı; PR ve sütun anlamı teyidi bekliyor.\n", "")
        yorum, neden = JY.uret(metin)
        self.assertIsNone(yorum)
        self.assertEqual(neden, "eksik: Test, Deploy")

    def test_durum_yok_yorum_uretilmez(self):
        satir = next(s for s in PE640.splitlines() if s.startswith("**Durum:**"))
        yorum, neden = JY.uret(PE640.replace(satir + "\n", ""))
        self.assertIsNone(yorum)
        self.assertIn("Durum", neden)
        self.assertIn("üretilmedi", neden)

    def test_model_ve_ag_kutuphanesi_ice_aktarilmaz(self):
        with open(JY.__file__, encoding="utf-8") as f:
            agac = ast.parse(f.read())
        adlar = {a.name.split(".")[0] for d in ast.walk(agac) if isinstance(d, ast.Import) for a in d.names}
        adlar |= {(d.module or "").split(".")[0] for d in ast.walk(agac) if isinstance(d, ast.ImportFrom)}
        self.assertEqual(adlar & {"anthropic", "openai", "requests", "httpx", "urllib", "socket", "http",
                                  "subprocess", "ork_lib", "llm"}, set())


class Cli(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.kok = self._t.name
        sd = os.path.join(self.kok, ".claude", "orkestra")
        self.klasor = os.path.join(self.kok, "isler", "640-pe-640-tahmin")
        os.makedirs(sd)
        os.makedirs(self.klasor)
        t = datetime.datetime.now().astimezone().isoformat()
        kayit = {"id": "I-001", "baslik": "PE-640 tahmin", "durum": "acik", "klasor": self.klasor,
                 "olusturma": t, "guncelleme": t, "kartlar": [], "oturumlar": []}
        with open(os.path.join(self.klasor, "is.json"), "w", encoding="utf-8") as f:
            json.dump(kayit, f, ensure_ascii=False)
        with open(os.path.join(sd, "isler.json"), "w", encoding="utf-8") as f:
            json.dump({"sayac": 1, "isler": {"I-001": {k: kayit[k] for k in
                                                       ("klasor", "baslik", "durum", "olusturma", "guncelleme")}}},
                      f, ensure_ascii=False)

    def tearDown(self):
        self._t.cleanup()

    def ozet(self, ad, metin):
        with open(os.path.join(self.klasor, ad), "w", encoding="utf-8", newline="\n") as f:
            f.write(metin)

    def kos(self, *args):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=self.kok, PYTHONUTF8="1")
        with mock.patch.object(socket.socket, "connect", _ag_yasak), \
                mock.patch.object(socket, "create_connection", _ag_yasak):
            return ic_kos.kos([ORKESTRA, "is", "jira-yorum", *args], cwd=self.kok, env=env)

    def test_en_yeni_ozetten_birebir_ve_ag_yok(self):
        self.ozet("calisma_ozeti_20261020.md", SO.YENI_B1 + SO.HARITA)  # eski, Teslim'siz
        self.ozet("calisma_ozeti_20261027.md", PE640)
        p = self.kos("I-001")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(p.stdout, BEKLENEN)

    def test_jira_anahtariyla_cozer(self):
        self.ozet("calisma_ozeti_20261027.md", PE640)
        p = self.kos("PE-640")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(p.stdout, BEKLENEN)

    def test_teslim_bos_cikis_1_eksik_adlari(self):
        self.ozet("calisma_ozeti_20261027.md", SO.YENI_B1 + SO.HARITA + BOS_TESLIM)
        p = self.kos("I-001")
        self.assertEqual(p.returncode, 1)
        self.assertEqual(p.stdout.strip(), "eksik: Değişiklik, Test, Deploy, Geri alma")
        self.assertNotIn("**Sonuç:**", p.stdout)

    def test_durum_yok_cikis_1(self):
        satir = next(s for s in PE640.splitlines() if s.startswith("**Durum:**"))
        self.ozet("calisma_ozeti_20261027.md", PE640.replace(satir + "\n", ""))
        p = self.kos("I-001")
        self.assertEqual(p.returncode, 1)
        self.assertIn("yorum üretilmedi", p.stdout)
        self.assertNotIn("**Sonuç:**", p.stdout)

    def test_ozet_yok_hata(self):
        p = self.kos("I-001")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("calisma_ozeti", p.stdout + p.stderr)

    def test_bilinmeyen_is(self):
        p = self.kos("I-999")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("iş yok", p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
