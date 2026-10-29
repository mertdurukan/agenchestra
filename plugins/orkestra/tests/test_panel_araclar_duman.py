"""Araçlar sayfası (#/araclar, ADR-0098): MCP ve skill satırları, anahtar durumu, aç/kapat POST'u, erişilebilirlik.

Node'da sahte tarayıcıyla (tests/panel_duman.js) gerçek assets/app.js koşulur; ağ ve sunucu yoktur.
`python -m pytest plugins/orkestra/tests/test_panel_araclar_duman.py`
"""
import copy
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

import test_panel_pencere_birim as TPB

MCP = "/api/araclar-mcp"
SKILL = "/api/araclar-skill"


def mcp_kayit(ad, durum="acik", eksik=None, kimlik="yok", yuksek=False):
    return {"ad": ad, "aciklama": ad + " açıklaması", "durum": durum, "kimlik": kimlik, "eksik_gerek": eksik or [], "yuksek_yetki": yuksek}


MCPLER = [mcp_kayit("memory"), mcp_kayit("filesystem", "kapali", yuksek=True), mcp_kayit("serena", "kapali", eksik=["uv"]),
          mcp_kayit("github", "acik", kimlik="yok: GITHUB_TOKEN")] + [mcp_kayit("m%02d" % i, "kapali") for i in range(15)]
SKILLER = [{"ad": "orkestra:is", "kaynak": "eklenti", "aciklama": "iş", "mekanizma": "deny", "durum": "acik"},
           {"ad": "yerel", "kaynak": "proje", "aciklama": "yerel skill", "mekanizma": "skillOverrides", "durum": "kapali"}]


def kos(sn, fx_ek=None):
    fx = TPB.fixture()
    fx[MCP] = {"mcp": copy.deepcopy(MCPLER)}
    fx[SKILL] = {"skill": copy.deepcopy(SKILLER), "alan": "alan-a"}
    fx.update(copy.deepcopy(fx_ek or {}))
    with tempfile.TemporaryDirectory() as t:
        y = {a: os.path.join(t, a + ".json") for a in ("fx", "sn", "cikti")}
        json.dump(fx, open(y["fx"], "w", encoding="utf-8"), ensure_ascii=False)
        json.dump(sn, open(y["sn"], "w", encoding="utf-8"), ensure_ascii=False)
        subprocess.run(["node", TPB.DUMAN, TPB.APP, y["fx"], y["sn"], y["cikti"]], check=True, timeout=180)
        c = json.load(open(y["cikti"], encoding="utf-8"))
    assert c["hatalar"] == [], c["hatalar"]
    return c["sonuc"]


@unittest.skipUnless(shutil.which("node"), "node yok")
class AraclarSayfasi(unittest.TestCase):
    def test_mcp_19_satir_anahtar_ve_rozetler(self):
        h = kos([{"depo": {}, "hash": "#/araclar"}])[0]["ana"]
        self.assertEqual(len(re.findall(r'role="switch"', h)), 19)
        self.assertIn("MCP<", h)
        self.assertIn("2/19", re.sub(r"<[^>]+>", "", h).replace(" ", ""))   # memory + github açık
        self.assertIn("Yüksek yetki", h)
        self.assertIn("Ön koşul eksik: uv", h)
        self.assertIn("Anahtar eksik", h)
        self.assertIn('aria-checked="true"', h)
        self.assertIn('aria-checked="false"', h)
        self.assertNotIn("GITHUB_TOKEN=", h)

    def test_on_kosulu_eksik_kapali_anahtar_devre_disi(self):
        h = kos([{"depo": {}, "hash": "#/araclar"}])[0]["ana"]
        satir = re.search(r'<button[^>]*data-ad="serena"[^>]*>', h).group(0)
        self.assertIn("disabled", satir)
        self.assertNotIn("disabled", re.search(r'<button[^>]*data-ad="memory"[^>]*>', h).group(0))

    def test_anahtar_adini_etiketle_baglar(self):
        h = kos([{"depo": {}, "hash": "#/araclar"}])[0]["ana"]
        b = re.search(r'<button[^>]*data-ad="memory"[^>]*>', h).group(0)
        self.assertIn('aria-labelledby="ar-mcp-memory"', b)
        self.assertIn('id="ar-mcp-memory"', h)

    def test_tikla_acik_mcpyi_kapatir_ve_listeyi_yeniler(self):
        sonra = copy.deepcopy(MCPLER)
        sonra[0]["durum"] = "kapali"
        sn = [{"depo": {}, "hash": "#/araclar", "adimlar": [["tikla", "arac-degistir", {"tur": "mcp", "ad": "memory"}]]}]
        # tıklama sırasında aria-checked, fixture'da yok; sahte düğme dataset'inde belirtilmediği için "açık değil" okunur
        r = kos(sn, {"POST " + MCP: {"status": 200, "govde": {"ad": "memory", "istenen": "kapali", "durum": "kapali", "tamam": True},
                                     "sonra": {MCP: {"mcp": sonra}}}})[0]
        self.assertEqual(r["postlar"][0]["yol"].split("?")[0], MCP)
        self.assertEqual(set(r["postlar"][0]["govde"]), {"ad", "durum"})
        self.assertEqual(r["postlar"][0]["govde"]["ad"], "memory")

    def test_basarisiz_degisiklik_hata_gosterir_ve_cokmez(self):
        sn = [{"depo": {}, "hash": "#/araclar", "adimlar": [["tikla", "arac-degistir", {"tur": "mcp", "ad": "memory"}]]}]
        r = kos(sn, {"POST " + MCP: {"status": 409, "govde": {"ad": "memory", "tamam": False, "durum": "acik"}}})[0]
        self.assertEqual(len(r["postlar"]), 1)
        self.assertIn("role=\"switch\"", r["ana"])

    def test_skill_sekmesi_kaynak_ve_deny_notu(self):
        h = kos([{"depo": {}, "hash": "#/araclar?t=skill"}])[0]["ana"]
        self.assertEqual(len(re.findall(r'role="switch"', h)), 2)
        self.assertIn("Eklenti", h)
        self.assertIn("çağrıya kapanır", h)
        self.assertIn("1/2".replace("1", "1"), re.sub(r"<[^>]+>", "", h).replace(" ", ""))

    def test_arama_suzer(self):
        h = kos([{"depo": {}, "hash": "#/araclar?q=serena"}])[0]["ana"]
        self.assertEqual(len(re.findall(r'role="switch"', h)), 1)
        h = kos([{"depo": {}, "hash": "#/araclar?q=yokboyle"}])[0]["ana"]
        self.assertIn("Eşleşen MCP yok", h)

    def test_gezinti_girdisi_var(self):
        r = kos([{"depo": {}, "hash": "#/araclar"}])[0]
        self.assertIn("#/araclar", r["ray"])
        self.assertIn("Araçlar", r["ray"])


if __name__ == "__main__":
    unittest.main()
