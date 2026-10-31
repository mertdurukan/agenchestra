"""Arka plan görevi yaşı (ADR-0123, G3): Stop satırına "en eski görev N dk" ve eşik üstü işareti ekler; Windows'ta çocuk
`find.exe` süreçlerini listeler. Model çağrılmaz, süreç öldürülmez (K4): yalnız gösterir; kapatma ajanda ya da kullanıcıdadır.

Yaş kaynağı sırası: görev nesnesinin zaman alanı (varsa) → transkriptte arka plana düşen aracın zaman damgası.
Eşik ve süreç adı `ayarlar/arka_plan_yas.json`'da. Hatada sessiz (boş metin).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AYAR_YOLU = os.path.join(_KOK, "ayarlar", "arka_plan_yas.json")
_VARSAYILAN = {"esik_dk": 10, "zaman_alanlari": ["started_at", "startedAt", "start_time", "created_at", "createdAt", "start"],
               "cocuk_surec": "find", "transkript_okuma_bayt": 4000000}
_BITTI = re.compile(r"<status>\s*(completed|stopped|failed|killed)\s*</status>", re.I)
_KIMLIK = re.compile(r"<tool-use-id>\s*([^<\s]+)\s*</tool-use-id>")


def ayar_oku() -> dict:
    ayar = dict(_VARSAYILAN)
    try:
        with open(AYAR_YOLU, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            ayar.update(d)
    except Exception:
        pass
    return ayar


def _saniye(deger, simdi: float):
    """ISO metin, epoch saniye ya da milisaniye → geçen saniye; çözülemezse None."""
    try:
        if isinstance(deger, (int, float)):
            t = float(deger) / (1000.0 if deger > 1e11 else 1.0)
        elif isinstance(deger, str) and deger.strip():
            s = deger.strip().replace("Z", "+00:00")
            t = datetime.fromisoformat(s).timestamp()
        else:
            return None
        return max(0.0, simdi - t)
    except Exception:
        return None


def alan_yaslari(gorevler, simdi: float, ayar: dict | None = None) -> list[float]:
    """Görev nesnelerinin zaman alanından yaşlar (saniye); alanı olmayan görev atlanır."""
    ayar = ayar or ayar_oku()
    sonuc = []
    for g in gorevler if isinstance(gorevler, list) else []:
        if not isinstance(g, dict):
            continue
        for a in ayar["zaman_alanlari"]:
            y = _saniye(g.get(a), simdi)
            if y is not None:
                sonuc.append(y)
                break
    return sonuc


def transkript_yaslari(yol, simdi: float, ayar: dict | None = None) -> list[float]:
    """Transkriptte arka plana düşen (zaman aşımı ya da run_in_background) ve bildirimi gelmemiş araçların yaşları (saniye)."""
    ayar = ayar or ayar_oku()
    acik: dict[str, float] = {}
    try:
        if not yol or not os.path.exists(yol):
            return []
        boy = os.path.getsize(yol)
        with open(yol, "rb") as f:
            f.seek(max(0, boy - int(ayar["transkript_okuma_bayt"])))
            veri = f.read()
        import genis_tarama_hatirlatma as GT
        for ham in veri.splitlines():
            try:
                o = json.loads(ham.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                continue
            if not isinstance(o, dict) or o.get("isSidechain"):
                continue
            icerik = (o.get("message") or {}).get("content")
            zaman = _saniye(o.get("timestamp"), simdi)
            if o.get("type") == "assistant" and isinstance(icerik, list) and zaman is not None:
                for b in icerik:
                    if (isinstance(b, dict) and b.get("type") == "tool_use" and isinstance(b.get("input"), dict)
                            and b["input"].get("run_in_background") is True and b.get("id")):
                        acik.setdefault(b["id"], zaman)
            elif o.get("type") == "user" and isinstance(icerik, list) and zaman is not None:
                for b in icerik:
                    if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id"):
                        ham_metin = b.get("content")
                        metin = ham_metin if isinstance(ham_metin, str) else json.dumps(ham_metin, ensure_ascii=False)
                        if GT.arka_plana_dustu_mu(metin):
                            acik.setdefault(b["tool_use_id"], zaman)
            elif o.get("type") == "user" and isinstance(icerik, str) and "<task-notification>" in icerik and _BITTI.search(icerik):
                for k in _KIMLIK.findall(icerik):
                    acik.pop(k, None)
    except Exception:
        return []
    return sorted(acik.values(), reverse=True)


def cocuk_surecler(ayar: dict | None = None, calistir=None) -> list[tuple[int, float]]:
    """Windows'ta çalışan `find.exe` süreçleri: [(pid, yaş_saniye)]; başka platformda ya da hatada boş."""
    if sys.platform != "win32":
        return []
    ayar = ayar or ayar_oku()
    ad = re.sub(r"[^A-Za-z0-9_.-]", "", str(ayar["cocuk_surec"]))
    komut = ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             f"Get-Process -Name {ad} -ErrorAction SilentlyContinue | ForEach-Object {{ \"$($_.Id) $($_.StartTime.ToUniversalTime().ToString('o'))\" }}"]
    try:
        cikti = (calistir or (lambda c: subprocess.run(c, capture_output=True, text=True, timeout=8,
                                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout))(komut)
        simdi = datetime.now(timezone.utc).timestamp()
        sonuc = []
        for s in str(cikti).splitlines():
            p = s.split()
            if len(p) == 2 and p[0].isdigit():
                y = _saniye(p[1], simdi)
                if y is not None:
                    sonuc.append((int(p[0]), y))
        return sonuc
    except Exception:
        return []


def _dk(saniye: float) -> int:
    return int(saniye // 60)


def ek_metin(gorevler, transkript=None, simdi: float | None = None, cocuklar=None) -> str:
    """Stop satırının eki: " — en eski N dk" (+ eşik üstü işareti) ve çocuk süreçler; veri yoksa ''."""
    try:
        simdi = simdi if simdi is not None else datetime.now(timezone.utc).timestamp()
        ayar = ayar_oku()
        yaslar = alan_yaslari(gorevler, simdi, ayar) or transkript_yaslari(transkript, simdi, ayar)
        parca = []
        if yaslar:
            en_eski = max(yaslar)
            ek = f"en eski {_dk(en_eski)} dk"
            if _dk(en_eski) >= int(ayar["esik_dk"]):
                ek += f", {ayar['esik_dk']} dk üstü: gereksizse kapat"
            parca.append(ek)
        c = cocuklar if cocuklar is not None else (cocuk_surecler(ayar) if yaslar or gorevler else [])
        if c:
            parca.append(f"{ayar['cocuk_surec']}.exe " + ", ".join(f"PID {p} ({_dk(y)} dk)" for p, y in c[:3]))
        return " — " + "; ".join(parca) if parca else ""
    except Exception:
        return ""
