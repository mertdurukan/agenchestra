"""Ajanın görev listesinin (masaüstünde `mcp__ccd_turn__update_plan`, CLI'da `TodoWrite`) son durumunu transcript'ten kurar.

Tek ayrıştırıcıdır: Stop kapısı (gorev_listesi_kapisi) ve close skill'i (sohbet_cikar.Plan) bunu kullanır. Madde biçimi
{"icerik": str, "durum": "pending" | "in_progress" | "completed"}. Model çağrısı yok.

update_plan anlamı: `items` listeyi değiştirir; ardından `done` (1 tabanlı) tamamlar; `advance` in_progress adımı tamamlar ve
ondan SONRAKİ ilk pending adımı başlatır; `start` (1 tabanlı) adımı başlatır. TodoWrite `todos` listeyi bütünüyle değiştirir.
"""
import json
import os

PLAN_SONEKI = "update_plan"
TODO_ARACI = "TodoWrite"


def arac_mi(ad) -> bool:
    return isinstance(ad, str) and (ad.endswith(PLAN_SONEKI) or ad == TODO_ARACI)


def _maddeler(liste) -> list:
    return [{"icerik": str(x.get("content") or ""), "durum": str(x.get("status") or "pending")}
            for x in liste if isinstance(x, dict)]


def uygula(maddeler: list, ad: str, girdi) -> list:
    """Tek bir görev listesi çağrısını uygular; yeni liste döner (girdi bozuksa liste aynen kalır)."""
    if not isinstance(girdi, dict):
        return maddeler
    if ad == TODO_ARACI:
        return _maddeler(girdi["todos"]) if isinstance(girdi.get("todos"), list) else maddeler
    yeni = _maddeler(girdi["items"]) if isinstance(girdi.get("items"), list) else [dict(m) for m in maddeler]
    for n in girdi.get("done") or []:
        if isinstance(n, int) and 1 <= n <= len(yeni):
            yeni[n - 1]["durum"] = "completed"
    if girdi.get("advance"):
        i = next((k for k, m in enumerate(yeni) if m["durum"] == "in_progress"), None)
        if i is not None:
            yeni[i]["durum"] = "completed"
        j = next((k for k, m in enumerate(yeni) if m["durum"] == "pending" and (i is None or k > i)), None)
        if j is not None:
            yeni[j]["durum"] = "in_progress"
    s = girdi.get("start")
    if isinstance(s, int) and 1 <= s <= len(yeni):
        yeni[s - 1]["durum"] = "in_progress"
    return yeni


def durum_kur(transkript) -> tuple:
    """Ana zincirdeki görev listesi çağrılarını sırayla uygular: (son liste, son kullanılan araç adı)."""
    maddeler, son_arac = [], None
    if not transkript or not os.path.isfile(transkript):
        return maddeler, son_arac
    with open(transkript, encoding="utf-8", errors="replace") as f:
        for satir in f:
            if PLAN_SONEKI not in satir and TODO_ARACI not in satir:
                continue  # ucuz süzgeç: yalnız ilgili satırlar JSON çözülür
            try:
                o = json.loads(satir)
            except ValueError:
                continue
            if not isinstance(o, dict) or o.get("isSidechain"):
                continue  # alt ajanın listesi ana ajanın listesi değildir
            ms = o.get("message")
            if not isinstance(ms, dict) or ms.get("role") != "assistant" or not isinstance(ms.get("content"), list):
                continue
            for b in ms["content"]:
                if isinstance(b, dict) and b.get("type") == "tool_use" and arac_mi(b.get("name")):
                    maddeler = uygula(maddeler, b["name"], b.get("input") or {})
                    son_arac = b["name"]
    return maddeler, son_arac
