#!/usr/bin/env python3
"""Cursor IDE ölçüm donanımı (issue #14, PR-2, P3): günlük yazan hook'ları kurar, günlüğü çözümler.

  --kur HOOKS_JSON    log-only hook dosyasını yazar (var olan dosya <ad>.orkestra_yedek olarak saklanır)
  --kaldir HOOKS_JSON yedeği geri koyar ya da (yedek yoksa) dosyayı siler
  --analiz GUNLUK     günlükten olay/alan/çift tetik/paralellik/gecikme özeti (JSON)
  --gecikme N         adaptörün (cursor_hook.py) kendi süre payı: N çağrıda p50/p95 ms (Cursor'suz, yerel)

Ölçüm yalnız gözlemler: kaydedici hiçbir izni reddetmez ve içerik yazmaz (bkz. cursor_olcum_gunluk.py).
Yalnız standart kütüphane; Python 3.9+.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
import time
from typing import Dict, List, Optional

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUNLUKCU = os.path.join(KOK, "plugins", "orkestra", "scripts", "cursor_olcum_gunluk.py")
YEDEK_SONEK = ".orkestra_yedek"
OLAYLAR = ["sessionStart", "sessionEnd", "beforeSubmitPrompt", "preToolUse", "postToolUse", "postToolUseFailure",
           "subagentStart", "subagentStop", "beforeShellExecution", "afterShellExecution", "beforeMCPExecution",
           "afterMCPExecution", "afterFileEdit", "beforeReadFile", "afterAgentResponse", "afterAgentThought",
           "stop", "preCompact"]
ILGI_ALANLARI = ("agent_id", "agent_type", "session_id", "conversation_id", "generation_id", "subagent_id",
                 "tool_use_id", "is_parallel_worker", "duration", "duration_ms")


def hooks_json(gunlukcu: str = GUNLUKCU) -> dict:
    # Baştaki tırnaklı yol PowerShell'de söz dizimi hatasıdır (ADR-0172 madde 5): komut `python` ile başlar.
    yol = gunlukcu.replace("\\", "/")
    return {"version": 1, "hooks": {
        o: [{"command": 'python "%s" %s' % (yol, o), "timeout": 10}] for o in OLAYLAR}}


def kur(hedef: str) -> str:
    if os.path.exists(hedef) and not os.path.exists(hedef + YEDEK_SONEK):
        os.replace(hedef, hedef + YEDEK_SONEK)
    os.makedirs(os.path.dirname(os.path.abspath(hedef)), exist_ok=True)
    with open(hedef, "w", encoding="utf-8", newline="\n") as f:
        json.dump(hooks_json(), f, indent=2)
    return "kuruldu: %s" % hedef


def kaldir(hedef: str) -> str:
    yedek = hedef + YEDEK_SONEK
    if os.path.exists(yedek):
        os.replace(yedek, hedef)
        return "yedek geri konuldu: %s" % hedef
    if os.path.exists(hedef):
        os.remove(hedef)
        return "silindi: %s" % hedef
    return "yapilacak bir sey yok: %s" % hedef


def oku(yol: str) -> List[dict]:
    out = []
    with open(yol, encoding="utf-8") as f:
        for satir in f:
            satir = satir.strip()
            if satir:
                try:
                    out.append(json.loads(satir))
                except ValueError:
                    pass
    return out


def yuzdelik(degerler: List[float], p: float) -> Optional[float]:
    if not degerler:
        return None
    s = sorted(degerler)
    return round(s[min(len(s) - 1, int(round(p * (len(s) - 1))))], 2)


def analiz(kayitlar: List[dict]) -> dict:
    olay_sayisi: Dict[str, int] = {}
    alanlar: Dict[str, set] = {}
    ilgi: Dict[str, Dict[str, int]] = {}
    token_alanlari: Dict[str, set] = {}
    for k in kayitlar:
        o = k.get("olay", "")
        yuk = k.get("yuk") if isinstance(k.get("yuk"), dict) else {}
        olay_sayisi[o] = olay_sayisi.get(o, 0) + 1
        alanlar.setdefault(o, set()).update(yuk.keys())
        for a in ILGI_ALANLARI:
            if a in yuk:
                ilgi.setdefault(o, {})[a] = ilgi.setdefault(o, {}).get(a, 0) + 1

        def tara(v, yol=""):
            if isinstance(v, dict):
                for ka, x in v.items():
                    if re.search(r"token|usage|cost", ka, re.I):
                        token_alanlari.setdefault(o, set()).add(yol + ka)
                    tara(x, yol + ka + ".")
        tara(yuk)
    # çift tetik: aynı olay + tool_use_id (ya da subagent_id) birden çok kayıtta
    gruplar: Dict[str, int] = {}
    for k in kayitlar:
        yuk = k.get("yuk") if isinstance(k.get("yuk"), dict) else {}
        kimlik = yuk.get("tool_use_id") or yuk.get("subagent_id")
        if kimlik:
            anahtar = "%s|%s" % (k.get("olay"), kimlik)
            gruplar[anahtar] = gruplar.get(anahtar, 0) + 1
    cift = {a: n for a, n in gruplar.items() if n > 1}
    # Task paralelliği: subagentStart -> subagentStop aralıkları (subagent_id yoksa tool_call_id)
    baslangic: Dict[str, float] = {}
    aralik: List[List[float]] = []
    for k in sorted(kayitlar, key=lambda x: x.get("t", 0)):
        yuk = k.get("yuk") if isinstance(k.get("yuk"), dict) else {}
        if k.get("olay") == "subagentStart":
            baslangic[str(yuk.get("subagent_id") or yuk.get("tool_call_id"))] = k["t"]
    # subagentStop yükünde kimlik yok (belge): bitişleri başlangıç sırasıyla eşle
    bitis = [k["t"] for k in sorted(kayitlar, key=lambda x: x.get("t", 0)) if k.get("olay") == "subagentStop"]
    for b, e in zip(sorted(baslangic.values()), bitis):
        aralik.append([b, e])
    ust_uste = any(aralik[i][1] > aralik[j][0] and aralik[j][1] > aralik[i][0]
                   for i in range(len(aralik)) for j in range(i + 1, len(aralik)))
    # hook gecikmesi: kaydedicinin kendi süresi (yalnız kendi iş payı; süreç başlatma maliyeti dışarıdadır)
    sureler = [k["sure_ms"] for k in kayitlar if isinstance(k.get("sure_ms"), (int, float))]
    # preToolUse -> postToolUse aracı süresi (aynı tool_use_id)
    pre: Dict[str, float] = {}
    fark: List[float] = []
    for k in sorted(kayitlar, key=lambda x: x.get("t", 0)):
        yuk = k.get("yuk") if isinstance(k.get("yuk"), dict) else {}
        tid = yuk.get("tool_use_id")
        if not tid:
            continue
        if k.get("olay") == "preToolUse":
            pre.setdefault(tid, k["t"])
        elif k.get("olay") == "postToolUse" and tid in pre:
            fark.append((k["t"] - pre[tid]) * 1000)
    ortamlar = sorted({json.dumps(k.get("ortam", {}), sort_keys=True) for k in kayitlar})
    return {
        "kayit_sayisi": len(kayitlar),
        "olay_sayisi": dict(sorted(olay_sayisi.items())),
        "olaylar_gorulmeyen": [o for o in OLAYLAR if o not in olay_sayisi],
        "alanlar": {o: sorted(a) for o, a in sorted(alanlar.items())},
        "ilgi_alanlari": ilgi,
        "token_benzeri_alanlar": {o: sorted(a) for o, a in token_alanlari.items()},
        "agent_id_goruldu": any("agent_id" in a for a in alanlar.values()),
        "cift_tetik": cift,
        "alt_ajan_araliklari": len(aralik),
        "alt_ajanlar_ust_uste": ust_uste,
        "kaydedici_sure_ms": {"n": len(sureler), "p50": yuzdelik(sureler, 0.5), "p95": yuzdelik(sureler, 0.95)},
        "pre_post_arac_ms": {"n": len(fark), "p50": yuzdelik(fark, 0.5), "p95": yuzdelik(fark, 0.95)},
        "ortamlar": [json.loads(x) for x in ortamlar][:5],
    }


def gecikme(n: int) -> dict:
    """cursor_hook.py adaptörünü Cursor'suz n kez çağırır (dönüşüm + atlama dalı dahil, hook.py'siz salt okuma yolu)."""
    betik = os.path.join(KOK, "plugins", "orkestra", "scripts", "cursor_hook.py")
    yuk = json.dumps({"tool_name": "Read", "tool_input": {"path": "x"}, "workspace_roots": [KOK]}).encode()
    env = dict(os.environ, ORKESTRA_CURSOR_TEKIL="0")
    sureler: List[float] = []
    for _ in range(n):
        t = time.perf_counter()
        subprocess.run([sys.executable, betik, "preToolUse"], input=yuk, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, env=env, check=False)
        sureler.append((time.perf_counter() - t) * 1000)
    return {"n": n, "yol": "salt okuma (atlanan) preToolUse", "p50_ms": yuzdelik(sureler, 0.5),
            "p95_ms": yuzdelik(sureler, 0.95), "ortalama_ms": round(statistics.mean(sureler), 2) if sureler else None}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--kur", metavar="HOOKS_JSON")
    g.add_argument("--kaldir", metavar="HOOKS_JSON")
    g.add_argument("--analiz", metavar="GUNLUK")
    g.add_argument("--gecikme", type=int, metavar="N")
    a = ap.parse_args(argv)
    if a.kur:
        print(kur(a.kur))
        print("gunluk: %s" % os.path.join(tempfile.gettempdir(), "orkestra_ide_olcum", "olcum.jsonl"))
    elif a.kaldir:
        print(kaldir(a.kaldir))
    elif a.analiz:
        print(json.dumps(analiz(oku(a.analiz)), indent=2, ensure_ascii=False))
    else:
        print(json.dumps(gecikme(a.gecikme), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
