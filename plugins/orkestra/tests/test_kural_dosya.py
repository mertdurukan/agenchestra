"""kural_dosya modülü ve panel uçları: liste, tam okuma, güvenli yazma (çakışma, JSON, CRLF, yedek, beyaz liste)."""
import http.client
import http.server
import json
import os
import sys
import tempfile
import threading
import unittest
from unittest import mock

AD = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AD, "..", "scripts"))
import kural_dosya as KD  # noqa: E402
import ork_lib as L  # noqa: E402
import panel  # noqa: E402


def yaz(yol, metin, ikili=False):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "wb") as f:
        f.write(metin if ikili else metin.encode("utf-8"))


class KuralDosya(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        r = self.t.name
        self.proje = os.path.join(r, "proje")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        self.ev = os.path.join(r, "ev")
        self.eklenti = os.path.join(r, "eklenti")
        yaz(os.path.join(self.proje, "CLAUDE.md"), "# Proje\nkural\n")
        yaz(os.path.join(self.proje, "AGENTS.md"), "# Ajanlar\n")
        yaz(os.path.join(self.proje, ".claude", "rules", "db.md"), "db kuralı\n")
        yaz(os.path.join(self.proje, ".claude", "agents", "a.md"), "ajan\n")
        yaz(os.path.join(self.proje, ".claude", "skills", "s", "SKILL.md"), "skill\n")
        yaz(os.path.join(self.proje, ".claude", "settings.json"), '{"model": "x"}\n')
        yaz(os.path.join(self.proje, "baska.md"), "listede olmamalı\n")
        yaz(os.path.join(self.eklenti, "KURALLAR.md"), "genel kurallar\n")
        yaz(os.path.join(self.eklenti, "agents", "isci.md"), "işçi\n")
        yaz(os.path.join(self.ev, ".claude", "CLAUDE.md"), "kullanıcı\n")
        self.yamalar = [mock.patch.object(L, "PLUGIN_ROOT", self.eklenti),
                        mock.patch("os.path.expanduser", lambda p: self.ev if p == "~" else p)]
        for y in self.yamalar:
            y.start()

    def tearDown(self):
        for y in self.yamalar:
            y.stop()
        self.t.cleanup()

    def kimlik(self, ad, grup=None):
        k = [d for d in KD.liste(self.proje) if d["ad"] == ad and (grup is None or d["grup"] == grup)]
        self.assertEqual(len(k), 1, ad)
        return k[0]["id"]

    def test_liste_kapsami_ve_beyaz_liste(self):
        adlar = {(d["grup"], d["ad"]) for d in KD.liste(self.proje)}
        for beklenen in [("proje", "CLAUDE.md"), ("proje", "AGENTS.md"), ("proje", ".claude/rules/db.md"),
                         ("proje", ".claude/agents/a.md"), ("proje", ".claude/skills/s/SKILL.md"),
                         ("proje", ".claude/settings.json"), ("eklenti", "KURALLAR.md"),
                         ("eklenti", "agents/isci.md"), ("kullanici", "CLAUDE.md")]:
            self.assertIn(beklenen, adlar)
        self.assertNotIn(("proje", "baska.md"), adlar)

    def test_oku_tam_metin_ve_taban(self):
        o = KD.oku(self.proje, self.kimlik("CLAUDE.md", "proje"))
        self.assertEqual(o["metin"], "# Proje\nkural\n")
        self.assertTrue(o["taban"])

    def test_bilinmeyen_kimlik(self):
        with self.assertRaises(LookupError):
            KD.oku(self.proje, "yoksa")
        with self.assertRaises(LookupError):
            KD.yaz(self.proje, self.sd, "../../etc", "x", "t")

    def test_yaz_yedek_ve_yeni_taban(self):
        k = self.kimlik("AGENTS.md")
        o = KD.oku(self.proje, k)
        s = KD.yaz(self.proje, self.sd, k, "# Yeni\n", o["taban"])
        self.assertTrue(s["degisti"])
        self.assertEqual(open(os.path.join(self.proje, "AGENTS.md"), encoding="utf-8").read(), "# Yeni\n")
        yedek = os.listdir(os.path.join(self.sd, "kural_yedek"))
        self.assertEqual(len(yedek), 1)
        self.assertEqual(open(os.path.join(self.sd, "kural_yedek", yedek[0]), encoding="utf-8").read(), "# Ajanlar\n")
        self.assertEqual(KD.oku(self.proje, k)["taban"], s["taban"])

    def test_cakisma_reddedilir(self):
        k = self.kimlik("AGENTS.md")
        o = KD.oku(self.proje, k)
        yaz(os.path.join(self.proje, "AGENTS.md"), "başkası değiştirdi\n")
        with self.assertRaises(ValueError) as c:
            KD.yaz(self.proje, self.sd, k, "benim\n", o["taban"])
        self.assertTrue(str(c.exception).startswith("cakisma:"))
        self.assertEqual(open(os.path.join(self.proje, "AGENTS.md"), encoding="utf-8").read(), "başkası değiştirdi\n")

    def test_degisiklik_yoksa_yazmaz(self):
        k = self.kimlik("AGENTS.md")
        o = KD.oku(self.proje, k)
        self.assertFalse(KD.yaz(self.proje, self.sd, k, o["metin"], o["taban"])["degisti"])
        self.assertFalse(os.path.isdir(os.path.join(self.sd, "kural_yedek")))

    def test_json_gecerli_olmali(self):
        k = self.kimlik(".claude/settings.json")
        o = KD.oku(self.proje, k)
        with self.assertRaises(ValueError):
            KD.yaz(self.proje, self.sd, k, "{bozuk", o["taban"])
        KD.yaz(self.proje, self.sd, k, '{"model": "y"}\n', o["taban"])

    def test_crlf_korunur(self):
        yaz(os.path.join(self.proje, "CLAUDE.md"), b"a\r\nb\r\n", ikili=True)
        k = self.kimlik("CLAUDE.md", "proje")
        o = KD.oku(self.proje, k)
        self.assertEqual(o["metin"], "a\nb\n")
        KD.yaz(self.proje, self.sd, k, "a\nc\n", o["taban"])
        with open(os.path.join(self.proje, "CLAUDE.md"), "rb") as f:
            self.assertEqual(f.read(), b"a\r\nc\r\n")

    def test_boyut_ve_nul(self):
        k = self.kimlik("AGENTS.md")
        o = KD.oku(self.proje, k)
        with self.assertRaises(ValueError):
            KD.yaz(self.proje, self.sd, k, "a\x00b", o["taban"])
        with self.assertRaises(ValueError):
            KD.yaz(self.proje, self.sd, k, "x" * (KD.DOSYA_MAX + 1), o["taban"])


class KuralDosyaPanel(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.proje = os.path.join(self.t.name, "proje")
        os.makedirs(os.path.join(self.proje, ".claude", "orkestra"))
        yaz(os.path.join(self.proje, "CLAUDE.md"), "merhaba\n")
        self.alan = {"id": "alan-x", "ad": "proje", "yol": self.proje, "orkestra": True, "sohbet": 1, "son": "x"}
        self.yama = mock.patch.object(L, "calisma_alanlari", lambda: [self.alan])
        self.yama.start()
        self.sunucu = http.server.ThreadingHTTPServer(("127.0.0.1", 0), panel._isleyici())
        self.port = self.sunucu.server_address[1]
        threading.Thread(target=self.sunucu.serve_forever, daemon=True).start()

    def tearDown(self):
        self.sunucu.shutdown()
        self.sunucu.server_close()
        self.yama.stop()
        self.t.cleanup()

    def istek(self, yontem, yol, govde=None, baslik=None):
        h = {"Host": f"127.0.0.1:{self.port}"}
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
        return r.status, json.loads(b) if b[:1] == b"{" else b

    def post(self, govde, baslik=None):
        b = {"X-Orkestra": "1", "Content-Type": "application/json"}
        b.update(baslik or {})
        return self.istek("POST", "/api/kural-dosya?alan=alan-x", govde, b)

    def test_liste_oku_yaz(self):
        k, v = self.istek("GET", "/api/kural-dosyalar?alan=alan-x")
        self.assertEqual(k, 200)
        d = next(x for x in v["dosyalar"] if x["grup"] == "proje" and x["ad"] == "CLAUDE.md")
        k, o = self.istek("GET", f"/api/kural-dosya?alan=alan-x&id={d['id']}")
        self.assertEqual(o["metin"], "merhaba\n")
        k, s = self.post({"id": d["id"], "metin": "yeni\n", "taban": o["taban"]})
        self.assertEqual(k, 200)
        self.assertEqual(open(os.path.join(self.proje, "CLAUDE.md"), encoding="utf-8").read(), "yeni\n")
        k, s2 = self.post({"id": d["id"], "metin": "eski taban\n", "taban": o["taban"]})
        self.assertEqual(k, 409)

    def test_yazma_korumalari(self):
        self.assertEqual(self.post({"id": "x", "metin": "a", "taban": "t"}, baslik={"X-Orkestra": "0"})[0], 403)
        self.assertEqual(self.post({"id": "../x", "metin": "a", "taban": "t"})[0], 404)
        self.assertEqual(self.post({"id": "x", "metin": 5, "taban": "t"})[0], 400)
        self.assertEqual(self.istek("GET", "/api/kural-dosya?alan=alan-x&id=yok")[0], 404)


if __name__ == "__main__":
    unittest.main()
