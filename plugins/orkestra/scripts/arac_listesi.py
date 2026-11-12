"""Oturumun araç listesi (I-455, ADR-0180): hook girdisi araç listesi taşımaz; liste transkriptten okunur.

Kaynaklar (birleşimi):
- son `api-request-shape` kaydının `shape.tools[].name` değerleri (yüklü araçlar);
- `deferred_tools_delta` kayıtları sırayla oynatılır: `addedNames` ekler, `removedNames` çıkarır, `readdedNames` geri ekler
  (`deferred_tools_record` bu alanları taşımaz, yok sayılır);
- ana ajanın çağırdığı `tool_use` adları (çağrılmış araç vardır).

Karar üçlüdür: True (var), False (yok), None (bilinmiyor). Yalnız False bir kapıyı susturur; okunamayan, kayıtsız ya da
boyut sınırını aşan transkript None döner ve eski davranış korunur (yanlış "yok" gerçek ihlali gizler).
Araç adı son `__` parçasıyla karşılaştırılır (`mcp__x__wrap_up` ile `wrap_up` aynıdır).
"""
from __future__ import annotations

import json
import os

_SINIR = 64_000_000  # bundan büyük transkript okunmaz: bilinmiyor


def _son_parca(ad) -> str:
    return str(ad or "").split("__")[-1]


def _oku(transkript):
    """(araç adları, yüklü liste kaydı görüldü mü); okunamazsa (None, False)."""
    if not transkript:
        return None, False
    try:
        if os.path.getsize(transkript) > _SINIR:
            return None, False
        with open(transkript, "rb") as f:
            satirlar = f.read().splitlines()
    except Exception:
        return None, False
    yuklu = None
    ertelenmis: set[str] = set()
    cagrilan: set[str] = set()
    delta_var = False
    for ham in satirlar:
        if b"api-request-shape" in ham:
            tur = "shape"
        elif b"deferred_tools_delta" in ham:
            tur = "delta"
        elif b'"tool_use"' in ham:
            tur = "cagri"
        else:
            continue
        try:
            o = json.loads(ham)
        except Exception:
            continue
        if not isinstance(o, dict):
            continue
        if tur == "shape" and o.get("type") == "api-request-shape":
            araclar = (o.get("shape") or {}).get("tools")
            if isinstance(araclar, list):
                yuklu = {_son_parca(a.get("name")) for a in araclar if isinstance(a, dict) and a.get("name")}
        elif tur == "delta":
            a = o.get("attachment")
            if isinstance(a, dict) and a.get("type") == "deferred_tools_delta":
                delta_var = True
                ertelenmis |= {_son_parca(x) for x in a.get("addedNames") or [] if x}
                ertelenmis -= {_son_parca(x) for x in a.get("removedNames") or [] if x}
                ertelenmis |= {_son_parca(x) for x in a.get("readdedNames") or [] if x}
        elif tur == "cagri" and o.get("type") == "assistant" and not o.get("isSidechain"):
            icerik = (o.get("message") or {}).get("content")
            for b in icerik if isinstance(icerik, list) else []:
                if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name"):
                    cagrilan.add(_son_parca(b.get("name")))
    if yuklu is None and not delta_var and not cagrilan:
        return None, False
    return (yuklu or set()) | ertelenmis | cagrilan, yuklu is not None


def arac_adlari(transkript):
    """Oturumdaki bilinen araç adları (son `__` parçaları); okunamazsa None."""
    return _oku(transkript)[0]


def var_mi(transkript, ad):
    """Araç oturumda var mı: True / False / None (bilinmiyor).

    Yüklü araç listesi (`api-request-shape`) görülmeden "yok" denmez: araç yüklü olup ertelenmiş listede ve çağrılar
    arasında bulunmayabilir.
    """
    adlar, yuklu_goruldu = _oku(transkript)
    if adlar is None:
        return None
    if _son_parca(ad) in adlar:
        return True
    return False if yuklu_goruldu else None
