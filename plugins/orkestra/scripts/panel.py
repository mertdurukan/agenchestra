"""Orkestra HTML canlı paneli: bu bilgisayardaki TÜM Claude çalışma alanları için tek yerel sunucu (yalnız 127.0.0.1).

GET /                          → panel sayfası (assets/panel.html)
GET /alanlar.json              → çalışma alanları (ad, yol, orkestra kurulu mu, son etkinlik)
GET /ozet.json?alan=<id>       → seçili alanın anlık görüntüsü (orkestra varsa tam, yoksa sohbet maliyetleri)
GET /analitik                  → analitik sayfası (assets/analitik.html)
GET /analitik.json?alan=<id>   → seçili orkestralı alanın analitiği (analitik.alan_analitigi)
GET /analitik-tum.json         → bütün alanların toplamı ve karşılaştırması
GET /simdi.json                → her sohbet: ne yapılıyor, neye yarayacak, kimi bekliyor (niyet.gorunum)
GET /saglik                    → "ok"
Sunucu durumu ~/.claude/orkestra-panel/panel.json'da; `orkestra panel` çalışan sunucuyu yeniden kullanır.
"""
from __future__ import annotations

import http.server
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402
import ozet  # noqa: E402
import analitik  # noqa: E402
import niyet  # noqa: E402

HTML = os.path.join(L.PLUGIN_ROOT, "assets", "panel.html")
ANALITIK_HTML = os.path.join(L.PLUGIN_ROOT, "assets", "analitik.html")
DURUM = os.path.join(L.GENEL_DIZIN, "panel.json")
SURUM = "5"  # sayfa/sunucu sözleşmesi; değişince eski sunucu yeniden başlatılır


def _isleyici():
    kilit = threading.Lock()
    onbellek: dict = {}

    def onbellekli(anahtar, sure, uret):
        with kilit:
            z, v = onbellek.get(anahtar, (0.0, b""))
            if time.time() - z > sure:
                try:
                    veri = uret()
                except Exception as e:  # noqa: BLE001
                    veri = {"acik": False, "hata": f"{type(e).__name__}: {e}"}
                v = json.dumps(veri, ensure_ascii=False).encode("utf-8")
                onbellek[anahtar] = (time.time(), v)
            return v

    class Isleyici(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _gonder(self, kod, tip, govde: bytes):
            self.send_response(kod)
            self.send_header("Content-Type", tip)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(govde)))
            self.end_headers()
            self.wfile.write(govde)

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            if u.path in ("/", "/index.html"):
                with open(HTML, "rb") as f:
                    return self._gonder(200, "text/html; charset=utf-8", f.read())
            if u.path == "/alanlar.json":
                return self._gonder(200, "application/json; charset=utf-8",
                                    onbellekli("alanlar", 5.0, L.calisma_alanlari))
            if u.path == "/ozet.json":
                alan = (q.get("alan") or [None])[0]
                return self._gonder(200, "application/json; charset=utf-8",
                                    onbellekli(("ozet", alan), 1.0, lambda: ozet.alan_ozeti(alan)))
            if u.path in ("/analitik", "/analitik.html"):
                with open(ANALITIK_HTML, "rb") as f:
                    return self._gonder(200, "text/html; charset=utf-8", f.read())
            if u.path == "/analitik.json":
                alan = (q.get("alan") or [None])[0]
                return self._gonder(200, "application/json; charset=utf-8",
                                    onbellekli(("analitik", alan), 10.0, lambda: analitik.alan_analitigi(alan)))
            if u.path == "/analitik-tum.json":
                return self._gonder(200, "application/json; charset=utf-8",
                                    onbellekli("analitik-tum", 20.0, analitik.tum_alanlar))
            if u.path == "/simdi.json":
                return self._gonder(200, "application/json; charset=utf-8", onbellekli("simdi", 3.0, niyet.gorunum))
            if u.path == "/saglik":
                return self._gonder(200, "text/plain", f"ok {SURUM}".encode())
            return self._gonder(404, "text/plain", b"yok")

    return Isleyici


def _bos_port(baslangic: int) -> int:
    for p in range(baslangic, baslangic + 30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    raise RuntimeError("boş port bulunamadı")


def _saglik(port: int) -> str | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/saglik", timeout=1.5) as r:
            return r.read().decode()
    except Exception:
        return None


def calistir(port: int) -> None:
    sunucu = http.server.ThreadingHTTPServer(("127.0.0.1", port), _isleyici())
    L.atomik_yaz(DURUM, json.dumps({"port": port, "pid": os.getpid(), "surum": SURUM, "zaman": L.simdi()}))
    sunucu.serve_forever()


def _durdur(eski: dict) -> None:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(eski["pid"]), "/F"], capture_output=True)
        else:
            os.kill(int(eski["pid"]), 15)
    except Exception:
        pass


def baslat(port: int = 8765, alan_id: str | None = None, on_planda: bool = False) -> str:
    sorgu = f"?alan={urllib.parse.quote(alan_id)}" if alan_id else ""
    try:
        with open(DURUM, encoding="utf-8") as f:
            eski = json.load(f)
        durum = _saglik(eski["port"])
        if durum == f"ok {SURUM}":
            return f"http://127.0.0.1:{eski['port']}/{sorgu}"
        if durum is not None:          # eski sürüm sunucu: kapat, yenisini aç
            _durdur(eski)
            time.sleep(0.5)
    except Exception:
        pass
    port = _bos_port(port)
    if on_planda:
        print(f"http://127.0.0.1:{port}/{sorgu}  (Ctrl+C ile durur)", flush=True)
        calistir(port)
        return ""
    bayrak = 0x00000008 | 0x00000200 | 0x08000000 if os.name == "nt" else 0
    subprocess.Popen([sys.executable, os.path.abspath(__file__), "_kos", str(port)], cwd=L.GENEL_DIZIN if os.path.isdir(L.GENEL_DIZIN) else None,
                     creationflags=bayrak, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True)
    for _ in range(30):
        if _saglik(port):
            return f"http://127.0.0.1:{port}/{sorgu}"
        time.sleep(0.2)
    return f"http://127.0.0.1:{port}/{sorgu}  (başlatıldı; yanıt vermiyorsa `orkestra panel --on-planda` ile hatayı gör)"


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "_kos":
        os.makedirs(L.GENEL_DIZIN, exist_ok=True)
        calistir(int(sys.argv[2]))
