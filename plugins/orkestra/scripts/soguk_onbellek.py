"""Soğuk önbellek kapısı (UserPromptSubmit).

Ölçüm (15.10): ana ajanın önbellek yazımının ~%35'i, kullanıcı 1 saatten uzun ara verip büyük bağlamlı
sohbete döndüğünde bütün bağlamın yeniden yazılmasından geliyor (önbellek süresi en çok 1 saat).
Kapı: son ana ajan çağrısı `esik_dk`dan eski VE bağlam `esik_token`dan büyükse kullanıcıya tahmini yeniden yazma
maliyeti ve ucuz yol (yeni sohbet + `orkestra is devam <id>`) bilgi olarak söylenir; istek ENGELLENMEZ (ADR-0095).
Proje ezmesi: `.claude/orkestra/onbellek_kapisi.json` ({"acik": false} kapatır). Hata her zaman sessizce geçer.
"""
from __future__ import annotations

import datetime as D
import json
import os

import ork_lib as L

VARSAYILAN = {"acik": True, "esik_token": 150_000, "esik_dk": 60, "tekrar_dk": 15, "is_degisimi": True,
              "devir_uyarisi": True, "devir_esik_token": 200_000}
# Yeni sohbetin ölçülen açılış bağlamı (tasarruf tahmini için): ilk çağrı medyanı 91.223 token, 205 oturum, 22.10.2026
# (`orkestra maliyet taban`; I-159 P4). Eski 30.000 sabiti tasarrufu 1,6-2 kat şişiriyordu.
YENI_SOHBET_BAGLAMI = 91_000
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
    # Engellemez (ADR-0095): mesaj aynı turda işlenir. Çağrı sonrası son çağrı zamanı güncellenir, aynı soğukluk için ikinci uyarı doğmaz.
    f_ = L.model_fiyati(s["model"])
    usd = s["baglam"] / 1e6 * f_.get("onbellek_yazma_1sa", f_.get("giris", 0) * 2)
    return (f"Orkestra önbellek bilgisi: son çağrıdan bu yana {ara_dk:.0f} dk geçti, önbellek soğudu. "
            f"Bu sohbetin bağlamı ~{s['baglam'] // 1000}k token; bu mesaj bağlamın tamamını yeniden yazar (~{usd:.2f} USD). "
            "Mesajın işlendi. Ucuz yol: yeni sohbet aç ve `orkestra is devam <iş id>` de (sıradaki adımlar işin todo.md'sinde).")


def is_degisimi_uyarisi(sd: str, oid: str | None, transkript: str | None, bagli_is, onerilen_is) -> str | None:
    """G-125: bağlam büyükken oturum başka bir açık işe kayıyorsa ENGELLEMEYEN uyarı metni, yoksa None.

    Koşul: ayar `is_degisimi` açık, son çağrı bağlamı >= `esik_token`, bağlı iş var, önerilen iş var ve farklı.
    Aynı oturum + hedef iş için yalnız bir kez (işaret dosyası `<oid>.isdeg`). Hata her zaman None (hook düşmez)."""
    try:
        a = ayarlar(sd)
        if not a.get("is_degisimi") or not oid or not bagli_is or not onerilen_is:
            return None
        if str(bagli_is) == str(onerilen_is):
            return None
        s = son_cagri(transkript)
        if not s or s["baglam"] < a["esik_token"]:
            return None
        isaret = os.path.join(sd, "oturumlar", f"{oid}.isdeg")
        goruldu = set()
        try:
            with open(isaret, encoding="utf-8") as f:
                goruldu = {x.strip() for x in f.read().splitlines() if x.strip()}
        except OSError:
            pass
        if str(onerilen_is) in goruldu:
            return None
        os.makedirs(os.path.dirname(isaret), exist_ok=True)
        with open(isaret, "a", encoding="utf-8") as f:
            f.write(f"{onerilen_is}\n")
        tasarruf = max(0, s["baglam"] - YENI_SOHBET_BAGLAMI)
        return (f"Orkestra: bu sohbetin bağlamı ~{s['baglam'] // 1000}k token ve istek {bagli_is} yerine farklı bir işe "
                f"({onerilen_is}) daha yakın. Ucuz yol: yeni sohbet aç ve `orkestra is devam {onerilen_is}` de; "
                f"çağrı başına yaklaşık {tasarruf // 1000}k token tasarruf (bir iş bir oturum). Burada sürdürmek de mümkün.")
    except Exception:
        return None


def devir_uyarisi(sd: str, oid: str | None, transkript: str | None) -> str | None:
    """I-159 P5: son ana ajan çağrısının bağlamı `devir_esik_token` üstündeyse ENGELLEMEYEN devir uyarısı, yoksa None.

    Ölçüm (22.10.2026, 7 gün, I-159 P4): 200 bin üstünde devir (yeni sohbet + devir belgesi) net kazançlı.
    Oturum başına bir kez (işaret `<oid>.devir`); ayar `devir_uyarisi: false` kapatır. Hata her zaman None."""
    try:
        a = ayarlar(sd)
        if not a.get("devir_uyarisi") or not oid:
            return None
        s = son_cagri(transkript)
        if not s or s["baglam"] <= a["devir_esik_token"]:
            return None
        isaret = os.path.join(sd, "oturumlar", f"{oid}.devir")
        if os.path.exists(isaret):
            return None
        os.makedirs(os.path.dirname(isaret), exist_ok=True)
        with open(isaret, "w", encoding="utf-8") as f:
            f.write(D.datetime.now(D.timezone.utc).isoformat())
        azalan = max(0, s["baglam"] - YENI_SOHBET_BAGLAMI)
        usd = azalan / 1e6 * L.model_fiyati(s["model"]).get("onbellek_okuma", 0)
        return (f"Orkestra: bu sohbetin bağlamı ~{s['baglam'] // 1000}k token. Ucuz yol: `/orkestra:devir` ile devir belgesi üret, "
                f"yeni sohbet aç; çağrı başına ~{azalan // 1000}k token (~{usd:.2f} USD) daha az okunur "
                "(ölçüm: 200k üstünde devir net kazançlı). Burada sürdürmek de mümkün; uyarıyı kapatmak için "
                "`onbellek_kapisi.json` içinde `devir_uyarisi: false`.")
    except Exception:
        return None
