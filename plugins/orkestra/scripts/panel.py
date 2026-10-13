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
GET /onaylar, /onaylar.html    → Onay merkezi sayfası (assets/onaylar.html; yoksa "hazırlanıyor")
GET /kurallar, /kurallar.html  → Kurallar sayfası (assets/kurallar.html; yoksa "hazırlanıyor")
GET /onaylar.json?alan=<id>    → onay kuyruğu: sayaç, kayıtlar, perspektif (rapor, durum)
GET /kurallar.json?alan=<id>   → etkin kurallar, öneriler, geçmiş, kural kaynakları
GET /onay-sayac.json           → {alan_id: onay sayacı} (sekme rozeti)
POST /onay?alan=<id>           → karar / kural-ekle / kural-duzenle / kural-kaldir (X-Orkestra: 1, yerel Host, ≤64 KB)
GET /saglik                    → "ok"
Sunucu durumu ~/.claude/orkestra-panel/panel.json'da; `orkestra panel` çalışan sunucuyu yeniden kullanır.
"""
from __future__ import annotations

import http.server
import glob
import json
import os
import re
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
import onay  # noqa: E402

POST_MAX = 64 * 1024
POST_ATIM_MAX = 1024 * 1024  # bunun altındaki aşırı gövde okunup atılır

ASSETS = os.path.join(L.PLUGIN_ROOT, "assets")
# yol → (dosya, içerik türü); sayfa dosyası henüz yoksa "hazırlanıyor" sayfası döner
SAYFALAR = {"/": "simdi.html", "/index.html": "simdi.html", "/simdi.html": "simdi.html",
            "/maliyet": "maliyet.html", "/maliyet.html": "maliyet.html",
            "/verim": "verim.html", "/verim.html": "verim.html",
            "/onaylar": "onaylar.html", "/onaylar.html": "onaylar.html",
            "/kurallar": "kurallar.html", "/kurallar.html": "kurallar.html"}
STATIK = {"/ortak.css": ("ortak.css", "text/css; charset=utf-8"),
          "/ortak.js": ("ortak.js", "application/javascript; charset=utf-8")}
YONLENDIR = {"/analitik": "/verim", "/analitik.html": "/verim"}
DURUM = os.path.join(L.GENEL_DIZIN, "panel.json")
SURUM = "8"  # sayfa/sunucu sözleşmesi; değişince eski sunucu yeniden başlatılır


def _alan(alan_id, kesin: bool):
    """Alan sözlüğü ya da None. kesin=False: ozet.alan_ozeti ile aynı geri düşüş (ilk orkestralı alan)."""
    alanlar = L.calisma_alanlari()
    a = next((x for x in alanlar if x["id"] == alan_id), None)
    if kesin:
        return a
    return a or next((x for x in alanlar if x["orkestra"]), None) or (alanlar[0] if alanlar else None)


def _alan_sd(alan_id, kesin: bool = False):
    """(alan, sd) ya da (None, hata sözlüğü)."""
    a = _alan(alan_id, kesin)
    if not a or not a.get("orkestra"):
        return None, {"acik": False, "hata": "Bu çalışma alanında orkestra açık değil."}
    return a, os.path.join(a["yol"], ".claude", "orkestra")


def _alan_kisa(a: dict) -> dict:
    return {"id": a["id"], "ad": a["ad"], "yol": a["yol"]}


def _perspektif(sd: str) -> dict:
    """En yeni rapor (sd/perspektif/ ve sd/ruya/ içinden tarih damgasına göre) ve perspektif durumu; modül yoksa durum None."""
    rapor = None
    try:
        rapor = onay.en_yeni_rapor(sd)
    except Exception:  # noqa: BLE001
        rapor = None
    try:
        import perspektif  # noqa: PLC0415
        d = perspektif.durum(sd)
        son = d.get("son_perspektif")
        return {"rapor": rapor, "durum": {"son_perspektif": son, "son_ruya": son,  # son_ruya: eski anahtar (geriye uyum)
                                          "calisiyor": d.get("calisiyor"), "okunmamis_rapor": d.get("okunmamis_rapor")}}
    except Exception:  # noqa: BLE001
        return {"rapor": rapor, "durum": None}


def _onaylar_json(alan_id) -> dict:
    a, sd = _alan_sd(alan_id)
    if a is None:
        return sd
    onay.esitle(sd)
    kayitlar = onay.liste(sd)
    bekleyen = [k for k in kayitlar if k.get("durum") == "bekliyor"]
    diger = [k for k in kayitlar if k.get("durum") != "bekliyor"]
    return {"acik": True, "alan": _alan_kisa(a), "sayac": onay.sayac(sd),
            "kayitlar": bekleyen + diger[:max(0, 200 - len(bekleyen))],
            "perspektif": _perspektif(sd), "uretim": L.simdi()}


def _kurallar_json(alan_id) -> dict:
    a, sd = _alan_sd(alan_id)
    if a is None:
        return sd
    onay.esitle(sd)
    return {"acik": True, "alan": _alan_kisa(a), **onay.kural_gorunum(sd, a["yol"]), "uretim": L.simdi()}


def _sayac_tum() -> dict:
    out = {}
    for a in L.calisma_alanlari():
        if a.get("orkestra"):
            sd = os.path.join(a["yol"], ".claude", "orkestra")
            onay.esitle(sd)
            out[a["id"]] = onay.sayac(sd)
    return out


def _govde_denetle(g: dict) -> str | None:
    """Gövde alan türlerini denetler; sorun varsa Türkçe hata metni, yoksa None."""
    if not isinstance(g.get("islem"), str):
        return "islem metin olmalı."
    for ad in ("id", "metin", "sonuc", "neden", "not"):
        if ad in g and not isinstance(g[ad], str):
            return f"{ad} metin olmalı."
    if g.get("secim") is not None and not isinstance(g["secim"], str):
        return "secim metin olmalı."
    return None


def _onay_islemi(sd: str, g: dict):
    islem = g.get("islem")
    if islem == "karar":
        return onay.karar_ver(sd, g.get("id"), g.get("sonuc"), g.get("secim"), g.get("not"), kim="panel")
    if islem == "kural-ekle":
        return onay.kural_ekle(sd, g.get("metin") or "", g.get("neden") or "")
    if islem == "kural-duzenle":
        return onay.kural_duzenle(sd, g.get("id"), g.get("metin") or "", g.get("neden"))
    if islem == "kural-kaldir":
        return onay.kural_kaldir(sd, g.get("id"), g.get("not") or "")
    raise ValueError("bilinmeyen işlem.")


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
        timeout = 10  # yavaş istemci iş parçacığını süresiz tutmasın

        def log_message(self, *a):
            pass

        def _gonder(self, kod, tip, govde: bytes, kapat=False):
            self.send_response(kod)
            if kapat:
                self.send_header("Connection", "close")
                self.close_connection = True
            self.send_header("Content-Type", tip)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(govde)))
            self.end_headers()
            self.wfile.write(govde)
            if kapat:
                self._temiz_kapat()

        def _temiz_kapat(self):
            # Yanıtı gönder, yazma yönünü kapat, istemcinin kalan baytlarını kısa süre boşalt (Windows RST'sini önler).
            try:
                self.wfile.flush()
                self.connection.shutdown(socket.SHUT_WR)
                self.connection.settimeout(1.0)
                bitis = time.time() + 1.0
                kalan = 256 * 1024
                while kalan > 0 and time.time() < bitis:
                    parca = self.connection.recv(min(65536, kalan))
                    if not parca:
                        break
                    kalan -= len(parca)
            except (OSError, ValueError):
                pass

        def _hazirlaniyor(self, ad: str) -> bytes:
            baslik = {"maliyet.html": "Maliyet", "verim.html": "Verim ve sağlık",
                     "onaylar.html": "Onaylar", "kurallar.html": "Kurallar"}.get(ad, "Sayfa")
            return (f'<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
                    f'<title>Orkestra · {baslik}</title><link rel="stylesheet" href="ortak.css"></head>'
                    f'<body><main class="hazirlaniyor"><h1>{baslik}</h1><p>Bu sayfa hazırlanıyor.</p>'
                    f'<p><a href="/">Şimdi sayfasına dön</a></p></main></body></html>').encode("utf-8")

        def _json(self, kod, veri, kapat=False):
            return self._gonder(kod, "application/json; charset=utf-8",
                                json.dumps(veri, ensure_ascii=False).encode("utf-8"), kapat)

        def _yerel_host(self) -> bool:
            port = self.server.server_address[1]
            return (self.headers.get("Host") or "").strip().lower() in (f"127.0.0.1:{port}", f"localhost:{port}")

        def _post_onay(self, q):
            if self.headers.get("X-Orkestra") != "1" or not self._yerel_host():
                return self._gonder(403, "text/plain", b"yasak")
            if "application/json" not in (self.headers.get("Content-Type") or "").lower():
                return self._json(400, {"tamam": False, "hata": "Content-Type application/json olmalı."})
            try:
                uzun = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                uzun = -1
            if uzun < 0:
                return self._json(400, {"tamam": False, "hata": "Geçersiz Content-Length."})
            if uzun > POST_MAX:
                # Gövde işlenmez. Makul boyuttaysa istemcinin gönderimi bitsin diye atılır (Windows'ta
                # sunucu okumadan kapatırsa istemci bağlantı sıfırlaması görür); dev ise bağlantı kapatılır.
                if uzun <= POST_ATIM_MAX:
                    kalan = uzun
                    while kalan > 0:
                        parca = self.rfile.read(min(65536, kalan))
                        if not parca:
                            break
                        kalan -= len(parca)
                    return self._json(413, {"tamam": False, "hata": "Gövde çok büyük (en çok 64 KB)."})
                return self._json(413, {"tamam": False, "hata": "Gövde çok büyük (en çok 64 KB)."}, kapat=True)
            try:
                g = json.loads(self.rfile.read(uzun).decode("utf-8") or "null")
                if not isinstance(g, dict):
                    raise ValueError("Gövde bir JSON nesnesi olmalı.")
            except (ValueError, UnicodeDecodeError) as e:
                return self._json(400, {"tamam": False, "hata": f"Geçersiz JSON: {e}"})
            a, sd = _alan_sd((q.get("alan") or [None])[0], kesin=True)
            if a is None:
                return self._json(400, {"tamam": False, "hata": sd["hata"]})
            hata = _govde_denetle(g)
            if hata:
                return self._json(400, {"tamam": False, "hata": hata})
            try:
                kayit = _onay_islemi(sd, g)
            except (ValueError, TypeError) as e:
                return self._json(400, {"tamam": False, "hata": str(e)})
            except Exception as e:  # noqa: BLE001
                return self._json(500, {"tamam": False, "hata": f"{type(e).__name__}: {e}"})
            with kilit:
                for k in [k for k in onbellek if (isinstance(k, tuple) and k[0] in ("onay", "kural")) or k == "sayac"]:
                    onbellek.pop(k, None)
            return self._json(200, {"tamam": True, "kayit": kayit})

        def do_POST(self):
            # Sohbeti aç. Özel başlık zorunlu: başka bir sitenin sayfası bu isteği CORS ön denetimi olmadan gönderemez.
            u = urllib.parse.urlparse(self.path)
            if u.path == "/onay":
                return self._post_onay(urllib.parse.parse_qs(u.query))
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
            if u.path == "/onaylar.json":
                alan = (q.get("alan") or [None])[0]
                return self._gonder(200, "application/json; charset=utf-8",
                                    onbellekli(("onay", alan), 2.0, lambda: _onaylar_json(alan)))
            if u.path == "/kurallar.json":
                alan = (q.get("alan") or [None])[0]
                return self._gonder(200, "application/json; charset=utf-8",
                                    onbellekli(("kural", alan), 2.0, lambda: _kurallar_json(alan)))
            if u.path == "/onay-sayac.json":
                return self._gonder(200, "application/json; charset=utf-8", onbellekli("sayac", 5.0, _sayac_tum))
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
