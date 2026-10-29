"""Panel /api/araclar-mcp ve /api/araclar-skill (ADR-0098): yazma koruması, doğrulama, sır yok, arayüz bağlantısı."""
import http.client
import http.server
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from unittest import mock

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))
import araclar_mcp  # noqa: E402
import lib as L  # noqa: E402
import panel  # noqa: E402

SIR = "SAHTE-sir-77x"
JSON_B = {"Content-Type": "application/json"}


class AraclarPanelTesti(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.t, True)
        self.proje = os.path.join(self.t, "proje")
        sk = os.path.join(self.proje, ".claude", "skills", "yerel")
        os.makedirs(sk)
        with open(os.path.join(sk, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("---\nname: yerel\ndescription: deneme\n---\n")
        alan = {"id": "alan-x", "ad": "proje", "yol": self.proje, "orkestra": False, "sohbet": 1, "son": "x"}
        for p in (mock.patch.object(L, "calisma_alanlari", lambda: [alan]),
                  mock.patch.dict(os.environ, {"ORKESTRA_CLAUDE_JSON": os.path.join(self.t, "yok.json")})):
            p.start()
            self.addCleanup(p.stop)
        self.sunucu = http.server.ThreadingHTTPServer(("127.0.0.1", 0), panel._isleyici())
        self.port = self.sunucu.server_address[1]
        threading.Thread(target=self.sunucu.serve_forever, daemon=True).start()
        self.addCleanup(self.sunucu.server_close)
        self.addCleanup(self.sunucu.shutdown)

    def istek(self, yontem, yol, govde=None, baslik=None, host=None):
        h = {"Host": host or f"127.0.0.1:{self.port}"}
        h.update(baslik or {})
        veri = json.dumps(govde).encode("utf-8") if govde is not None else None
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.putrequest(yontem, yol, skip_host=True)
        for k, v in h.items():
            c.putheader(k, v)
        if veri is not None:
            c.putheader("Content-Length", str(len(veri)))
        c.endheaders(veri)
        r = c.getresponse()
        b = r.read()
        c.close()
        return r.status, b

    def post(self, yol, govde, **kw):
        return self.istek("POST", yol, govde, baslik={**JSON_B, "X-Orkestra": "1"}, **kw)

    # --- yazma koruması
    def test_basliksiz_post_403(self):
        for yol in ("/api/araclar-mcp", "/api/araclar-skill?alan=alan-x"):
            k, _ = self.istek("POST", yol, {"ad": "memory", "durum": "kapali"}, baslik=JSON_B)
            self.assertEqual(k, 403, yol)

    def test_yerel_olmayan_host_403(self):
        k, _ = self.post("/api/araclar-mcp", {"ad": "memory", "durum": "kapali"}, host="evil.example:80")
        self.assertEqual(k, 403)

    def test_gecersiz_govde_400(self):
        for g in ({"ad": 1, "durum": "acik"}, {"ad": "memory", "durum": "belki"}, {"ad": "memory"}, ["x"]):
            k, _ = self.post("/api/araclar-mcp", g)
            self.assertEqual(k, 400, g)

    def test_kayitsiz_mcp_adi_400(self):
        k, b = self.post("/api/araclar-mcp", {"ad": "kayitta-yok", "durum": "acik"})
        self.assertEqual(k, 400)
        self.assertFalse(json.loads(b)["tamam"])

    def test_mcp_basarili_ve_basarisiz_kodlar(self):
        with mock.patch.object(araclar_mcp, "degistir", return_value={"ad": "memory", "istenen": "acik", "durum": "acik", "tamam": True}):
            self.assertEqual(self.post("/api/araclar-mcp", {"ad": "memory", "durum": "acik"})[0], 200)
        with mock.patch.object(araclar_mcp, "degistir", return_value={"ad": "memory", "istenen": "acik", "durum": "kapali", "tamam": False}):
            self.assertEqual(self.post("/api/araclar-mcp", {"ad": "memory", "durum": "acik"})[0], 409)

    # --- GET
    def test_mcp_listesi_19_ve_sir_yok(self):
        k, b = self.istek("GET", "/api/araclar-mcp")
        self.assertEqual(k, 200)
        self.assertEqual(len(json.loads(b)["mcp"]), 19)
        with mock.patch.object(araclar_mcp.KM, "kimlik_durumu", return_value="var"):
            self.assertNotIn(SIR, self.istek("GET", "/api/araclar-mcp")[1].decode("utf-8"))

    def test_mcp_listesi_tum_alan_kabul_eder(self):
        self.assertEqual(self.istek("GET", "/api/araclar-mcp?alan=*")[0], 200)

    def test_skill_listesi_ve_alan_zorunlu(self):
        k, b = self.istek("GET", "/api/araclar-skill?alan=alan-x")
        v = json.loads(b)
        self.assertEqual(k, 200)
        self.assertIn("yerel", [s["ad"] for s in v["skill"]])
        self.assertEqual(self.istek("GET", "/api/araclar-skill?alan=*")[0], 400)

    # --- skill yazma
    def test_skill_kapat_ac_ayar_dosyasina_yazar(self):
        k, _ = self.post("/api/araclar-skill?alan=alan-x", {"ad": "yerel", "durum": "kapali"})
        self.assertEqual(k, 200)
        ayar = os.path.join(self.proje, ".claude", "settings.local.json")
        self.assertEqual(json.load(open(ayar, encoding="utf-8")), {"skillOverrides": {"yerel": "off"}})
        self.post("/api/araclar-skill?alan=alan-x", {"ad": "yerel", "durum": "acik"})
        self.assertEqual(json.load(open(ayar, encoding="utf-8")), {})

    def test_skill_bilinmeyen_ad_ve_alan_400(self):
        self.assertEqual(self.post("/api/araclar-skill?alan=alan-x", {"ad": "../x", "durum": "kapali"})[0], 400)
        self.assertEqual(self.post("/api/araclar-skill?alan=yok", {"ad": "yerel", "durum": "kapali"})[0], 400)
        self.assertEqual(self.post("/api/araclar-skill?alan=*", {"ad": "yerel", "durum": "kapali"})[0], 400)

    # --- sözleşme
    def test_arayuz_baglantisi(self):
        js = open(os.path.join(KOK, "assets", "app.js"), encoding="utf-8").read()
        for parca in ("'/api/araclar-mcp'", "'/api/araclar-skill'", "araclar: gAraclar", "data-eylem=\"arac-degistir\"",
                      "'#/araclar'", "role=\"switch\""):
            self.assertIn(parca, js)
        self.assertIn("/api/araclar-mcp", panel.KULLANICI_YOLLARI)
        self.assertNotIn("/api/araclar-skill", panel.KULLANICI_YOLLARI)


if __name__ == "__main__":
    unittest.main()
