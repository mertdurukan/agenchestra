"""Orkestra HTML canlı paneli: yerel sunucu (yalnız 127.0.0.1), standart kütüphane.

GET /            → panel sayfası (assets/panel.html)
GET /ozet.json   → anlık görüntü (ozet.olustur; en çok 1 sn önbellek)
GET /saglik      → "ok"
`orkestra panel` sunucuyu arka planda başlatır (zaten çalışıyorsa yeniden kullanır) ve adresi yazar.
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
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402
import ozet  # noqa: E402

HTML = os.path.join(L.PLUGIN_ROOT, "assets", "panel.html")


def _isleyici(sd: str, proje: str):
    kilit = threading.Lock()
    onbellek = {"zaman": 0.0, "veri": b""}

    class Isleyici(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):  # sessiz
            pass

        def _gonder(self, kod, tip, govde: bytes):
            self.send_response(kod)
            self.send_header("Content-Type", tip)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(govde)))
            self.end_headers()
            self.wfile.write(govde)

        def do_GET(self):
            yol = self.path.split("?")[0]
            if yol in ("/", "/index.html"):
                with open(HTML, "rb") as f:
                    return self._gonder(200, "text/html; charset=utf-8", f.read())
            if yol == "/ozet.json":
                with kilit:
                    if time.time() - onbellek["zaman"] > 1.0:
                        try:
                            veri = ozet.olustur(sd, proje)
                        except Exception as e:  # noqa: BLE001
                            veri = {"acik": False, "hata": f"{type(e).__name__}: {e}"}
                        onbellek["veri"] = json.dumps(veri, ensure_ascii=False).encode("utf-8")
                        onbellek["zaman"] = time.time()
                    govde = onbellek["veri"]
                return self._gonder(200, "application/json; charset=utf-8", govde)
            if yol == "/saglik":
                return self._gonder(200, "text/plain", b"ok")
            return self._gonder(404, "text/plain", b"yok")

    return Isleyici


def _bos_port(baslangic: int) -> int:
    for p in range(baslangic, baslangic + 30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    raise RuntimeError("boş port bulunamadı")


def _saglikli(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/saglik", timeout=1.5) as r:
            return r.read() == b"ok"
    except Exception:
        return False


def calistir(sd: str, proje: str, port: int) -> None:
    sunucu = http.server.ThreadingHTTPServer(("127.0.0.1", port), _isleyici(sd, proje))
    L.atomik_yaz(os.path.join(sd, "oturumlar", "panel.json"), json.dumps({"port": port, "pid": os.getpid(), "zaman": L.simdi()}))
    sunucu.serve_forever()


def baslat(sd: str, proje: str, port: int = 8765, on_planda: bool = False) -> str:
    try:
        with open(os.path.join(sd, "oturumlar", "panel.json"), encoding="utf-8") as f:
            eski = json.load(f)
        if _saglikli(eski["port"]):
            return f"http://127.0.0.1:{eski['port']}/  (zaten çalışıyor)"
    except Exception:
        pass
    port = _bos_port(port)
    if on_planda:
        print(f"http://127.0.0.1:{port}/  (Ctrl+C ile durur)", flush=True)
        calistir(sd, proje, port)
        return ""
    bayrak = 0x00000008 | 0x00000200 | 0x08000000 if os.name == "nt" else 0
    subprocess.Popen([sys.executable, os.path.abspath(__file__), "_kos", sd, proje, str(port)], cwd=proje,
                     creationflags=bayrak, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True)
    for _ in range(30):
        if _saglikli(port):
            return f"http://127.0.0.1:{port}/"
        time.sleep(0.2)
    return f"http://127.0.0.1:{port}/  (başlatıldı; yanıt vermiyorsa `orkestra panel --on-planda` ile hatayı gör)"


if __name__ == "__main__":
    if len(sys.argv) >= 5 and sys.argv[1] == "_kos":
        calistir(sys.argv[2], sys.argv[3], int(sys.argv[4]))
