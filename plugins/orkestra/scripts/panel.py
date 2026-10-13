"""Orkestra HTML canlı paneli: bu bilgisayardaki TÜM Claude çalışma alanları için tek yerel sunucu (yalnız 127.0.0.1).

GET /                          → Şimdi sayfası (assets/simdi.html); /index.html aynı
GET /maliyet                   → Maliyet sayfası (assets/maliyet.html; yoksa "hazırlanıyor")
GET /verim                     → Verim ve sağlık sayfası (assets/verim.html; yoksa "hazırlanıyor")
GET /ortak.css, /ortak.js      → üç sayfanın ortak tasarım sistemi
GET /alanlar.json              → çalışma alanları (ad, yol, orkestra kurulu mu, son etkinlik)
GET /ozet.json?alan=<id>       → seçili alanın anlık görüntüsü (orkestra varsa tam, yoksa sohbet maliyetleri)
GET /analitik, /analitik.html  → 301 /verim (sorgu dizesi korunur)
GET /analitik.json?alan=<id>   → seçili orkestralı alanın analitiği (analitik.alan_analitigi)
GET /analitik-tum.json         → bütün alanların toplamı ve karşılaştırması
GET /simdi.json                → her sohbet: ne yapılıyor, neye yarayacak, kimi bekliyor (niyet.gorunum)
POST /ac?oturum=<id>           → sohbeti Claude uygulamasında aç (X-Orkestra: 1 başlığı zorunlu)
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

ASSETS = os.path.join(L.PLUGIN_ROOT, "assets")
# yol → (dosya, içerik türü); sayfa dosyası henüz yoksa "hazırlanıyor" sayfası döner
SAYFALAR = {"/": "simdi.html", "/index.html": "simdi.html", "/simdi.html": "simdi.html",
            "/maliyet": "maliyet.html", "/maliyet.html": "maliyet.html",
            "/verim": "verim.html", "/verim.html": "verim.html"}
STATIK = {"/ortak.css": ("ortak.css", "text/css; charset=utf-8"),
          "/ortak.js": ("ortak.js", "application/javascript; charset=utf-8")}
YONLENDIR = {"/analitik": "/verim", "/analitik.html": "/verim"}
DURUM = os.path.join(L.GENEL_DIZIN, "panel.json")
SURUM = "7"  # sayfa/sunucu sözleşmesi; değişince eski sunucu yeniden başlatılır


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

        def _hazirlaniyor(self, ad: str) -> bytes:
            baslik = {"maliyet.html": "Maliyet", "verim.html": "Verim ve sağlık"}.get(ad, "Sayfa")
            return (f'<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
                    f'<title>Orkestra · {baslik}</title><link rel="stylesheet" href="ortak.css"></head>'
                    f'<body><main class="hazirlaniyor"><h1>{baslik}</h1><p>Bu sayfa hazırlanıyor.</p>'
                    f'<p><a href="/">Şimdi sayfasına dön</a></p></main></body></html>').encode("utf-8")

        def do_POST(self):
            # Sohbeti aç. Özel başlık zorunlu: başka bir sitenin sayfası bu isteği CORS ön denetimi olmadan gönderemez.
            u = urllib.parse.urlparse(self.path)
            if u.path != "/ac" or self.headers.get("X-Orkestra") != "1":
                return self._gonder(403, "text/plain", b"yasak")
            oturum = (urllib.parse.parse_qs(u.query).get("oturum") or [""])[0]
            try:
                sonuc = niyet.ac(oturum)
            except Exception as e:  # noqa: BLE001
                sonuc = {"tamam": False, "hata": f"{type(e).__name__}: {e}"}
            return self._gonder(200, "application/json; charset=utf-8", json.dumps(sonuc, ensure_ascii=False).encode("utf-8"))

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            if u.path in SAYFALAR:
                ad = SAYFALAR[u.path]
                yol = os.path.join(ASSETS, ad)
                if not os.path.isfile(yol):
                    return self._gonder(200, "text/html; charset=utf-8", self._hazirlaniyor(ad))
                with open(yol, "rb") as f:
                    return self._gonder(200, "text/html; charset=utf-8", f.read())
            if u.path in STATIK:
                ad, tip = STATIK[u.path]
                yol = os.path.join(ASSETS, ad)
                if not os.path.isfile(yol):
                    return self._gonder(404, "text/plain", b"yok")
                with open(yol, "rb") as f:
                    return self._gonder(200, tip, f.read())
            if u.path in YONLENDIR:
                hedef = YONLENDIR[u.path] + (f"?{u.query}" if u.query else "")
                self.send_response(301)
                self.send_header("Location", hedef)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return None
            if u.path == "/alanlar.json":
                return self._gonder(200, "application/json; charset=utf-8",
                                    onbellekli("alanlar", 5.0, L.calisma_alanlari))
            if u.path == "/ozet.json":
                alan = (q.get("alan") or [None])[0]
                return self._gonder(200, "application/json; charset=utf-8",
                                    onbellekli(("ozet", alan), 1.0, lambda: ozet.alan_ozeti(alan)))
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
