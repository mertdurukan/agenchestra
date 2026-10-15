"""Soğuk önbellek kapısı (UserPromptSubmit).

Ölçüm (15.10): ana ajanın önbellek yazımının ~%35'i, kullanıcı 1 saatten uzun ara verip büyük bağlamlı
sohbete döndüğünde bütün bağlamın yeniden yazılmasından geliyor (önbellek süresi en çok 1 saat).
Kapı: son ana ajan çağrısı `esik_dk`dan eski VE bağlam `esik_token`dan büyükse istek bir kez durdurulur,
kullanıcıya tahmini yeniden yazma maliyeti ve ucuz yol (yeni sohbet + `orkestra is devam <id>`) söylenir.
Aynı oturumda `tekrar_dk` içinde gelen ikinci istek geçer (kullanıcı bilerek sürdürüyor).
Proje ezmesi: `.claude/orkestra/onbellek_kapisi.json` ({"acik": false} kapatır). Hata her zaman sessizce geçer.
"""
from __future__ import annotations

import datetime as D
import json
import os

import ork_lib as L

VARSAYILAN = {"acik": True, "esik_token": 150_000, "esik_dk": 60, "tekrar_dk": 15}
OKUMA_KUYRUGU = 4_000_000  # transkriptin son bu kadar baytı okunur (büyük dosyada hızlı kalsın)


def ayarlar(sd: str) -> dict:
    a = dict(VARSAYILAN)
    try:
        with open(os.path.join(sd, "onbellek_kapisi.json"), encoding="utf-8") as f:
            ez = json.load(f)
        if isinstance(ez, dict):
            a.update({k: v for k, v in ez.items() if k in VARSAYILAN})
    except Exception:
        pass
    return a


def _zaman(s: str | None):
    if not s:
        return None
    try:
        z = D.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return z if z.tzinfo else z.replace(tzinfo=D.timezone.utc)
    except ValueError:
        return None


def son_cagri(transkript: str | None) -> dict | None:
    """Ana zincirdeki son asistan çağrısı: {'zaman', 'baglam', 'model', 'kullanim'} ya da None."""
    if not transkript or not os.path.isfile(transkript):
        return None
    with open(transkript, "rb") as f:
        f.seek(0, os.SEEK_END)
        boy = f.tell()
        f.seek(max(0, boy - OKUMA_KUYRUGU))
        satirlar = f.read().decode("utf-8", errors="replace").splitlines()
    for satir in reversed(satirlar):
        if '"assistant"' not in satir:
            continue
        try:
            r = json.loads(satir)
        except ValueError:
            continue
        if r.get("type") != "assistant" or r.get("isSidechain"):
            continue
        m = r.get("message") or {}
        u = m.get("usage") or {}
        baglam = sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
        z = _zaman(r.get("timestamp"))
        if baglam and z:
            return {"zaman": z, "baglam": baglam, "model": m.get("model") or "", "kullanim": u}
    return None


def _isaret_yolu(sd: str, oid: str) -> str:
    return os.path.join(sd, "oturumlar", f"{oid}.soguk")


def karar(sd: str, oid: str | None, transkript: str | None, simdi: D.datetime | None = None) -> str | None:
    """Durdurma gerekçesi (kullanıcıya gösterilir) ya da None (geç)."""
    a = ayarlar(sd)
    if not a.get("acik") or not oid:
        return None
    s = son_cagri(transkript)
    if not s:
        return None
    simdi = simdi or D.datetime.now(D.timezone.utc)
    ara_dk = (simdi - s["zaman"]).total_seconds() / 60
    if ara_dk < a["esik_dk"] or s["baglam"] < a["esik_token"]:
        return None
    isaret = _isaret_yolu(sd, oid)
    try:
        with open(isaret, encoding="utf-8") as f:
            onceki = _zaman(f.read().strip())
        os.remove(isaret)
        if onceki and 0 <= (simdi - onceki).total_seconds() / 60 < a["tekrar_dk"]:
            return None  # kullanıcı bilerek sürdürüyor: bir kez geç
    except OSError:
        pass
    os.makedirs(os.path.dirname(isaret), exist_ok=True)
    with open(isaret, "w", encoding="utf-8") as f:
        f.write(simdi.isoformat())
    f_ = L.model_fiyati(s["model"])
    usd = s["baglam"] / 1e6 * f_.get("onbellek_yazma_1sa", f_.get("giris", 0) * 2)
    return (f"Orkestra önbellek kapısı: son çağrıdan bu yana {ara_dk:.0f} dk geçti, önbellek soğudu. "
            f"Bu sohbetin bağlamı ~{s['baglam'] // 1000}k token; devam etmek bağlamın tamamını yeniden yazar (~{usd:.2f} USD). "
            "Ucuz yol: yeni sohbet aç ve `orkestra is devam <iş id>` de (sıradaki adımlar işin todo.md'sinde). "
            f"Yine de burada sürdürmek için mesajını {a['tekrar_dk']} dk içinde yeniden gönder.")
