"""Kritik SessionStart bağlamı: sürekli açık skill gövdeleri ve kurallar yolu satırı (ADR-0132, I-314).

Ana SessionStart hook'undan (hook.py) bağımsız ikinci komut olarak koşar: ana hook ağır bölümlerde 10 sn zaman
aşımını aşsa bile caveman gibi sürekli açık skill'ler kendi süresi içinde teslim edilir. Ağır import ve iş parçacığı yok;
orkestra açık olmayan projede sessiz çıkar. Kendi kaydını yazar: gunluk.jsonl `tur=baglam_kritik` (eklenti sürümü etiketli).
`ORKESTRA_SKILL_SUREKLI=0` içeriği, `ORKESTRA_BAGLAM_KAYDI=0` kaydı kapatır.
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ork_lib as L  # noqa: E402

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def uret(inp: dict) -> tuple[str, str | None]:
    """(bağlam metni, durum dizini). Orkestra açık değilse ('', None)."""
    sd = L.durum_dizini(inp.get("cwd"))
    if not sd:
        return "", None
    parcalar = []
    try:
        import skill_surekli
        sk = skill_surekli.baglam(L.proje_dizini(inp.get("cwd")))
        if sk:
            parcalar.append(sk)
    except Exception:
        pass
    yol = L.kaynaga_cevir(os.path.join(KOK, "KURALLAR.md"))
    if os.path.isfile(yol):
        parcalar.append(f"Kurallar: {yol}")
    return "\n".join(parcalar), sd


def kaydet(sd: str, oturum, ek: str, ms: float) -> None:
    if os.environ.get("ORKESTRA_BAGLAM_KAYDI") == "0":
        return
    try:
        import baglam_kaydi
        L.jsonl_ekle(os.path.join(sd, "gunluk.jsonl"),
                     {"zaman": L.simdi(), "oturum": oturum, "tur": "baglam_kritik", "olay": "SessionStart",
                      "surum": os.path.basename(KOK), "sure_ms": round(ms), **baglam_kaydi.ozet(ek)})
    except Exception:
        pass


def main() -> None:
    t0 = time.perf_counter()
    inp = L.stdin_json()
    ek, sd = uret(inp)
    if not ek or not sd:
        return
    kaydet(sd, inp.get("session_id"), ek, (time.perf_counter() - t0) * 1000)
    L.hook_cikti({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ek}})


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        main()
    except Exception:
        pass  # kritik hook oturumu asla düşürmez
