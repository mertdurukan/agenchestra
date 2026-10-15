"""Orkestra kota kaydı: Claude Code durum satırı (statusLine) komutu.

Claude Code durum satırı komutuna stdin'den JSON verir. Pro/Max hesaplarda içinde `rate_limits.five_hour` ve
`rate_limits.seven_day` (used_percentage 0-100, resets_at Unix saniye) bulunur; oturumdaki ilk yanıttan sonra gelir.
Bu betik değer değişince (ya da 5 dakikada bir) ~/.claude/orkestra-panel/kota.jsonl'a bir satır ekler ve
tek satırlık durum yazar. Sınırlar hesaba bağlıdır, projeye değil; kayıt bu yüzden genel klasördedir.

Ayar (proje .claude/settings.json):
  "statusLine": {"type": "command", "command": "python \"<plugin>/scripts/kota.py\""}
Hiçbir hata durum satırını bozmaz: her durumda bir satır basar ve 0 ile çıkar.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import time

GENEL_DIZIN = os.path.join(os.path.expanduser("~"), ".claude", "orkestra-panel")
KOTA_YOLU = os.path.join(GENEL_DIZIN, "kota.jsonl")
SON_YOLU = os.path.join(GENEL_DIZIN, "kota_son.json")
CAGRI_YOLU = os.path.join(GENEL_DIZIN, "kota_cagri.json")  # tanı: komut çağrıldı mı, rate_limits geldi mi
EN_SIK_S = 300  # değer değişmese de bu sürede bir nokta yaz (eğri boş kalmasın)
AZAMI_BAYT = 2 * 1024 * 1024


def _pencere(rl: dict, ad: str) -> dict | None:
    p = rl.get(ad)
    if not isinstance(p, dict) or p.get("used_percentage") is None:
        return None
    try:
        return {"yuzde": round(float(p["used_percentage"]), 1), "sifirlanma": p.get("resets_at")}
    except (TypeError, ValueError):
        return None


def _saat(sifir) -> str:
    try:
        return datetime.datetime.fromtimestamp(float(sifir)).strftime("%H:%M")
    except Exception:
        return "?"


def _cagri_izi(girdi: dict) -> None:
    """Küçük bir iz yazar; kota.jsonl yoksa nedenini (çağrılmadı / alan yok) ayırt etmeye yarar.
    Yalnız rate_limits_var ya da anahtarlar değişince, ya da son yazımdan EN_SIK_S geçmişse yazar."""
    rl = girdi.get("rate_limits")
    var = isinstance(rl, dict) and bool(rl)
    anahtarlar = sorted(girdi.keys())[:40]
    try:
        with open(CAGRI_YOLU, encoding="utf-8") as f:
            onceki = json.load(f)
    except Exception:
        onceki = {}
    if (onceki.get("rate_limits_var") == var and onceki.get("anahtarlar") == anahtarlar
            and time.time() - onceki.get("t", 0) < EN_SIK_S):
        return
    iz = {"zaman": datetime.datetime.now().astimezone().isoformat(timespec="seconds"), "t": time.time(),
          "rate_limits_var": var, "anahtarlar": anahtarlar}
    os.makedirs(GENEL_DIZIN, exist_ok=True)
    with open(CAGRI_YOLU, "w", encoding="utf-8", newline="\n") as f:
        json.dump(iz, f, ensure_ascii=False)


def kaydet(girdi: dict) -> dict | None:
    try:
        _cagri_izi(girdi)
    except Exception:
        pass
    rl = girdi.get("rate_limits")
    rl = rl if isinstance(rl, dict) else {}
    nokta = {"bes_saat": _pencere(rl, "five_hour"), "haftalik": _pencere(rl, "seven_day")}
    if not any(nokta.values()):
        return None
    os.makedirs(GENEL_DIZIN, exist_ok=True)
    try:
        with open(SON_YOLU, encoding="utf-8") as f:
            son = json.load(f)
    except Exception:
        son = {}
    imza = json.dumps(nokta, sort_keys=True)
    if son.get("imza") != imza or time.time() - son.get("t", 0) >= EN_SIK_S:
        if os.path.exists(KOTA_YOLU) and os.path.getsize(KOTA_YOLU) > AZAMI_BAYT:
            os.replace(KOTA_YOLU, KOTA_YOLU + ".1")
        kayit = {"zaman": datetime.datetime.now().astimezone().isoformat(timespec="seconds"), **nokta,
                 "oturum": (girdi.get("session_id") or "")[:8]}
        with open(KOTA_YOLU, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(kayit, ensure_ascii=False) + "\n")
        with open(SON_YOLU, "w", encoding="utf-8") as f:
            json.dump({"imza": imza, "t": time.time()}, f)
    return nokta


def satir(girdi: dict, nokta: dict | None) -> str:
    m = girdi.get("model")
    model = (m.get("display_name") or "").strip() if isinstance(m, dict) else ""
    parca = [model] if model else []
    if nokta and nokta.get("bes_saat"):
        b = nokta["bes_saat"]
        parca.append(f"5 sa %{b['yuzde']:.0f} (sıfırlanma {_saat(b['sifirlanma'])})")
    if nokta and nokta.get("haftalik"):
        parca.append(f"hafta %{nokta['haftalik']['yuzde']:.0f}")
    if not nokta:
        parca.append("kota: ilk yanıt bekleniyor")
    return " · ".join(parca)


def main() -> None:
    try:
        ham = sys.stdin.buffer.read().decode("utf-8", errors="replace")
        girdi = json.loads(ham) if ham.strip() else {}
        if not isinstance(girdi, dict):
            girdi = {}
    except Exception:
        girdi = {}
    try:
        nokta = kaydet(girdi)
    except Exception:
        nokta = None
    try:
        sys.stdout.write(satir(girdi, nokta))
    except Exception:
        sys.stdout.write("orkestra")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
