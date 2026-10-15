"""G-098: /yapilacaklar akışı uçtan uca (ekle -> listede -> bitti/sil; iş seçici) ve HTML-rota eşleşmesi.

Gerçek ~/.claude/orkestra-panel/panel.json ve gerçek todo dosyalarına dokunulmaz (geçici dizin + yama).
"""
import hashlib
import http.client
import http.server
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from unittest import mock

AD = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(AD, "..", "scripts")
ASSETS = os.path.join(AD, "..", "assets")
sys.path.insert(0, SCRIPTS)
import ork_lib as L  # noqa: E402
import is_kaydi as IK  # noqa: E402
import panel  # noqa: E402


def _ozet(yol):
    if not os.path.exists(yol):
        return None
    with open(yol, "rb") as f:
        return (os.path.getmtime(yol), hashlib.sha256(f.read()).hexdigest())


class Akis(unittest.TestCase):
    def setUp(self):
        self.once = _ozet(panel.DURUM)
        self.t = tempfile.TemporaryDirectory()
        self.proje = os.path.join(self.t.name, "proje")
        self.sd = os.path.join(self.proje, ".claude", "orkestra")
        os.makedirs(self.sd)
        alan = {"id": "alan-x", "ad": "proje", "yol": self.proje, "orkestra": True, "sohbet": 1, "son": "x"}
        self.yama = mock.patch.object(L, "calisma_alanlari", lambda: [alan])
        self.yama.start()
        self.i1 = IK.is_ac(self.sd, "Birinci iş", os.path.join(self.t.name, "k1"))
        self.i2 = IK.is_ac(self.sd, "Orkestra açık maddeler", os.path.join(self.t.name, "k2"))
        self.i3 = IK.is_ac(self.sd, "Kapalı iş", os.path.join(self.t.name, "k3"))
        IK.is_durum(self.sd, self.i3["id"], "kapandi")
        IK.todo_ekle(self.i2["klasor"], "açık bir madde")
        IK.todo_ekle(self.i2["klasor"], "bitecek madde")
        IK.todo_bitir(self.i2["klasor"], "bitecek")
        self.sunucu = http.server.ThreadingHTTPServer(("127.0.0.1", 0), panel._isleyici())
        self.port = self.sunucu.server_address[1]
        threading.Thread(target=self.sunucu.serve_forever, daemon=True).start()

    def tearDown(self):
        self.sunucu.shutdown()
        self.sunucu.server_close()
        self.yama.stop()
        self.t.cleanup()
        self.assertEqual(self.once, _ozet(panel.DURUM), "gerçek panel.json değişmemeli")

    def istek(self, yontem, yol, govde=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Host": f"127.0.0.1:{self.port}"}
        veri = None
        if govde is not None:
            veri = json.dumps(govde).encode("utf-8")
            h.update({"Content-Type": "application/json", "X-Orkestra": "1", "Content-Length": str(len(veri))})
        c.putrequest(yontem, yol, skip_host=True)
        for k, v in h.items():
            c.putheader(k, v)
        c.endheaders(veri)
        r = c.getresponse()
        b = r.read()
        c.close()
        return r.status, b

    def kliste(self):
        k, b = self.istek("GET", "/api/kullanici-todo?alan=alan-x")
        self.assertEqual(k, 200)
        return json.loads(b)["maddeler"]

    # --- 1 ---
    def test_ekle_listele_bitti(self):
        self.assertEqual(self.kliste(), [])
        k, b = self.istek("POST", "/api/kullanici-todo?alan=alan-x", {"eylem": "ekle", "metin": "yeni madde"})
        self.assertEqual(k, 200, b)
        m = self.kliste()
        self.assertEqual([x["metin"] for x in m], ["yeni madde"])
        dosya = os.path.join(self.sd, "kullanici_todo.json")
        with open(dosya, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["maddeler"][0]["metin"], "yeni madde")
        k, _ = self.istek("POST", "/api/kullanici-todo?alan=alan-x", {"eylem": "sil", "id": m[0]["id"]})
        self.assertEqual(k, 200)
        self.assertEqual(self.kliste(), [])
        with open(dosya, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["maddeler"], [])

    def test_is_todo_bitti_isaretli(self):
        k, b = self.istek("GET", f"/api/todo?alan=alan-x&is={self.i2['id']}")
        v = json.loads(b)
        self.assertEqual((k, v["acik_maddeler"], v["biten_maddeler"]), (200, ["açık bir madde"], ["bitecek madde"]))
        IK.todo_bitir(self.i2["klasor"], "1")
        v = json.loads(self.istek("GET", f"/api/todo?alan=alan-x&is={self.i2['id']}")[1])
        self.assertEqual((v["acik_maddeler"], len(v["biten_maddeler"])), ([], 2))

    def test_is_secici_acik_isleri_doner(self):
        v = json.loads(self.istek("GET", "/api/todo?alan=alan-x")[1])
        self.assertEqual({i["id"] for i in v["isler"]}, {self.i1["id"], self.i2["id"]})
        self.assertEqual(v["is"], self.i2["id"])  # varsayılan
        v = json.loads(self.istek("GET", f"/api/todo?alan=alan-x&is={self.i1['id']}")[1])
        self.assertEqual(v["is"], self.i1["id"])

    # --- 2 ---
    def test_html_fetch_adresleri_rotalarla_eslesir(self):
        with open(os.path.join(ASSETS, "yapilacaklar.html"), encoding="utf-8") as f:
            html = f.read()
        with open(os.path.join(ASSETS, "yapilacaklar.js"), encoding="utf-8") as f:
            html += "\n" + f.read()  # sayfa betiği ayrı dosyada
        with open(os.path.join(SCRIPTS, "panel.py"), encoding="utf-8") as f:
            kaynak = f.read()
        adresler = set(re.findall(r"'(/api/[a-z-]+)\?", html))
        self.assertEqual(adresler, {"/api/todo", "/api/kullanici-todo"})
        for a in adresler:
            self.assertIn(f'u.path == "{a}"', kaynak, a)
        # sayfa rotası ve fetch/gönder çağrıları yalnız bu iki adresi kullanır
        self.assertIn('"/yapilacaklar": "yapilacaklar.html"', kaynak)
        self.assertIsNone(re.search(r"fetch\(\s*['\"`](?!/api/)", html))
        k, b = self.istek("GET", "/yapilacaklar.js")
        self.assertEqual(k, 200)
        self.assertIn(b"/api/kullanici-todo", b)

    # --- 3: ayrı süreçte --test sunucusu panel.json'a yazmaz ---
    def test_kos_test_bayragi_panel_json_yazmaz(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        env = dict(os.environ, USERPROFILE=self.t.name, HOME=self.t.name)
        p = subprocess.Popen([sys.executable, os.path.join(SCRIPTS, "panel.py"), "_kos", str(port), "--test"],
                             env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            son = time.time() + 20
            ok = False
            while time.time() < son and p.poll() is None:
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/saglik", timeout=1) as r:
                        ok = r.status == 200
                        break
                except Exception:
                    time.sleep(0.1)
            self.assertTrue(ok, "test sunucusu ayağa kalkmadı")
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/yapilacaklar", timeout=5) as r:
                self.assertEqual(r.status, 200)
        finally:
            p.kill()
            p.wait()
        self.assertFalse(os.path.exists(os.path.join(self.t.name, ".claude", "orkestra-panel", "panel.json")))


if __name__ == "__main__":
    unittest.main()
