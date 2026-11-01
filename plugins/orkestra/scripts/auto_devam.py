"""/auto tur sonu devam denetimi (ADR-0132, P-028 gölge): bağlı iş `auto` modda açıkken ve çalışma özeti doldurulmamışken
tur biterse `gunluk.jsonl`'a `kapi_golge / auto_devam` yazılır. `ihlal` modunda tur başına bir kez block (`stop_hook_active`
döngüyü keser). Hatada sessiz geçer; kapatma: ORKESTRA_AUTO_DEVAM_KAPISI=0."""
from __future__ import annotations

import glob
import os
import re

import ork_lib as L

KAPI = "auto_devam"
NEDEN = "auto modda çalışma özeti yazılmadan tur bitti"
HATIRLATMA = ("Orkestra /auto (ADR-0132): iş açık ve çalışma özeti yok. Kullanıcıya dönme; kalan plan maddelerini best in class "
              "yöntemle bitir, kullanıcıya kalan işleri kendin çöz, kararları özetin '## Otomatik kararlar' bölümüne yaz ve "
              "`orkestra is kapat` ile kapat.")


def ozet_dolu_mu(klasor: str) -> bool:
    """Klasörde `**Ne yapıldı?**` (eski biçimde `**Ana bulgu:**`) altında yorum dışı metin olan calisma_ozeti_*.md var mı."""
    for yol in sorted(glob.glob(os.path.join(klasor, "calisma_ozeti_*.md"))):
        try:
            with open(yol, encoding="utf-8") as f:
                metin = f.read()
        except OSError:
            continue
        yorumsuz = re.sub(r"<!--.*?-->", "", metin, flags=re.S)
        m = re.search(r"\*\*(?:Ne yapıldı\?|Ana bulgu:)\*\*[ \t]*\n(.*?)(?=^\*\*[^\n]+[:?]\*\*|^#|\Z)", yorumsuz, re.S | re.M)
        govde = re.sub(r"^\s*[-*]\s*$", "", m.group(1), flags=re.M) if m else ""
        if govde.strip():
            return True
    return False


def kontrol(sd: str, oid, inp: dict) -> None:
    """Stop'ta çağrılır. Auto değilse, iş bağlı/açık değilse ya da özet doluysa susar."""
    if os.environ.get("ORKESTRA_AUTO_DEVAM_KAPISI") == "0" or not sd or not oid:
        return
    try:
        import is_kaydi
        import is_onay
        import izin_politikasi
        import kapi_mod
        if not izin_politikasi._auto_modu(sd, oid):
            return
        is_id = is_onay._bagli_is_id(sd, oid)
        kayit = is_kaydi.is_al(sd, is_id) if is_id else None
        if not kayit or kayit.get("durum") != "acik" or not kayit.get("klasor"):
            return
        klasor = kayit["klasor"]
        if ozet_dolu_mu(klasor):
            return
        kapi_mod.kaydet(klasor, KAPI, NEDEN)
        if kapi_mod.mod(KAPI, klasor) == "ihlal" and not inp.get("stop_hook_active"):
            L.hook_cikti({"decision": "block", "reason": HATIRLATMA})
    except SystemExit:
        raise
    except Exception:
        return
