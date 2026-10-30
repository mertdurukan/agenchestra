"""orkestra komutları: bakim (durum klasörü hijyeni; 041 P3).

`orkestra bakim` varsayılan olarak yalnız listeler (`--kuru`); `--uygula` ile işler:
- eski lock dosyaları silinir (yaş eşiği; kaynağı eşik içinde değişmiş ya da kilitli lock'a dokunulmaz),
- eski oturum kayıtları `oturumlar_arsiv/<YYYYAA>/` altına taşınır (bu oturumun kaydına dokunulmaz),
- ortak defterin aylık özeti `ortak_defter_ozet.json` olarak yazılır (defterin kendisi değişmez),
- kartsız, todo'suz, içeriği boş planlı ve eşikten eski açık işler listelenir; `--kapat` ile (yalnız `--uygula`yla)
  `--ozetsiz "otomatik açılış, iş yapılmadı"` gerekçesiyle kapatılır.
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import datetime
import re
import io
import json
import os
import shutil
import time

import ork_lib as L  # noqa: E402
from komutlar._ortak import hata, oturum_id, sd_gerekli  # noqa: E402

OZETSIZ_NEDEN = "otomatik açılış, iş yapılmadı"
ARSIV_DIZINI = "oturumlar_arsiv"


def lock_adaylari(sd: str, gun: float, simdi: float | None = None) -> list[str]:
    """Silinebilir lock dosyaları: kendisi ve kaynağı (adı `.lock`suz dosya) `gun` günden eski. Kaynak yoksa yalnız lock yaşı sayılır."""
    esik = (simdi or time.time()) - gun * 86400
    out = []
    for kok, dizinler, dosyalar in os.walk(sd):
        dizinler[:] = [d for d in dizinler if d != ARSIV_DIZINI]
        for ad in dosyalar:
            if not ad.endswith(".lock"):
                continue
            yol = os.path.join(kok, ad)
            try:
                if os.path.getmtime(yol) >= esik:
                    continue
                kaynak = yol[:-len(".lock")]
                if os.path.exists(kaynak) and os.path.getmtime(kaynak) >= esik:
                    continue  # kaynak yakın zamanda kullanılmış: lock hâlâ canlı olabilir
            except OSError:
                continue
            out.append(yol)
    return sorted(out)


def eski_oturumlar(sd: str, gun: float, simdi: float | None = None) -> list[str]:
    """Arşive taşınabilecek oturum kayıtları (oturumlar/*.json): `gun` günden eski; bu oturumun kaydı hariç."""
    esik = (simdi or time.time()) - gun * 86400
    dizin = os.path.join(sd, "oturumlar")
    benim = oturum_id() + ".json"
    out = []
    try:
        adlar = os.listdir(dizin)
    except OSError:
        return out
    for ad in adlar:
        if not ad.endswith(".json") or ad == benim:
            continue
        yol = os.path.join(dizin, ad)
        try:
            if os.path.isfile(yol) and os.path.getmtime(yol) < esik:
                out.append(yol)
        except OSError:
            continue
    return sorted(out)


def defter_ozeti(sd: str) -> dict:
    """Ortak defterin satır sayısı, bayt boyutu ve aylık dağılımı (salt okuma)."""
    yol = os.path.join(sd, "ortak_defter.jsonl")
    aylik = collections.Counter()
    n = 0
    for k in L.jsonl_oku(yol):
        n += 1
        aylik[str(k.get("zaman") or "")[:7] or "?"] += 1
    try:
        boyut = os.path.getsize(yol)
    except OSError:
        boyut = 0
    return {"satir": n, "bayt": boyut, "aylik": dict(sorted(aylik.items()))}


def _plan_dolu(yol: str) -> bool:
    """plan.md'de başlık dışında yazılmış içerik var mı (`is ac` şablonu yalnız başlık içerir; o boş sayılır)."""
    try:
        with open(yol, encoding="utf-8") as f:
            metin = f.read()
    except OSError:
        return False
    metin = re.sub(r"<!--.*?-->", "", metin, flags=re.S)  # şablon yorumları (doldur ipuçları) içerik değildir
    # şablonun doldurulmamış slotları ('- **ADR:** <ADR-nnnn | gerekmez — neden>') yazılmış içerik sayılmaz
    slot = re.compile(r"^\s*[-*]\s*\*\*[^*]+:\*\*\s*<[^<>]*>\s*$")
    return any(x.strip() and not x.lstrip().startswith("#") and not slot.match(x) for x in metin.splitlines())


def bos_isler(sd: str, saat: float, simdi: datetime.datetime | None = None) -> list[dict]:
    """Açık, kartsız, todo'suz, içeriği boş planlı ve `saat` saatten eski işler (otomatik açılıp kullanılmamış adaylar)."""
    import is_kaydi
    simdi = simdi or datetime.datetime.now().astimezone()
    kart_isleri = {str(k.get("is")) for k in L.kartlar(sd) if k.get("is")}
    out = []
    for g in is_kaydi.is_liste(sd, "acik"):
        klasor = g.get("klasor") or ""
        if g["id"] in kart_isleri or _plan_dolu(os.path.join(klasor, "plan.md")):
            continue
        try:
            if is_kaydi.todo_ozet(klasor)["toplam"]:
                continue
            olus = datetime.datetime.fromisoformat(str(g.get("olusturma")))
            if olus.tzinfo is None:
                olus = olus.astimezone()
        except Exception:
            continue
        yas = (simdi - olus).total_seconds() / 3600
        if yas >= saat:
            out.append({"id": g["id"], "baslik": str(g.get("baslik") or ""), "yas_saat": round(yas, 1)})
    return out


def _goreli(sd: str, yol: str) -> str:
    return os.path.relpath(yol, sd).replace(os.sep, "/")


def hook_kural_uyari(sd: str) -> str:
    """Kural dosyasındaki 'Hook ile yüklenen kurallar' kimlikleri eklentideki etkin yukle=hook kimlikleriyle uyuşmuyorsa tek satır uyarı; uyuşuyorsa ya da dosya yoksa ''."""
    import onay
    dosyada = onay.kural_dosyasi_hook_idleri(sd)
    if dosyada is None:
        return ""
    beklenen = onay.hook_yuklenen_idler(sd)
    if sorted(dosyada) == sorted(beklenen):
        return ""
    return (f"uyarı: kural dosyasındaki hook kuralları ({', '.join(dosyada) or '-'}) eklentidekiyle ({', '.join(beklenen) or '-'}) "
            "uyuşmuyor; dosyayı panelden yeniden üret")


def jira_izin_uyari(sd: str) -> str:
    """Proje izin politikası Jira yazmasını (MCP yazma aracı ya da REST yazması) serbest bırakıyor, geçerli jira_yorum standardı ise
    hâlâ 'onaya tabidir' diyorsa tek satır uyarı; yoksa ''. Karar izin_politikasi.karar'dan okunur (ask/deny = kapı var)."""
    import izin_politikasi as IP
    import standart
    metin = standart.oku("jira_yorum", sd) or ""
    if not re.search(r"onaya\s+tabi", metin, re.IGNORECASE):
        return ""
    cfg = IP.ayar_yukle(sd)
    mcp = IP.karar("mcp__atlassian__addCommentToJiraIssue", {}, sd=sd, cfg=cfg)[0]
    rest = IP.karar("Bash", {"command": "curl -X POST https://x.atlassian.net/rest/api/3/issue/A-1/comment -d @y.json"},
                    sd=sd, cfg=cfg)[0]
    serbest = [ad for ad, k in (("MCP yazma", mcp), ("REST yazma", rest)) if k not in ("ask", "deny")]
    if not serbest:
        return ""
    return (f"uyarı: izin politikası Jira yazmasını serbest bırakıyor ({', '.join(serbest)}) ama jira_yorum standardı "
            "'yazma onaya tabidir' diyor; standardı proje izin politikasına göre düzelt")


def olu_yol_ve_terk(sd: str, a, rapor: dict, uygula: bool) -> None:
    """I-271 P4: rapora 'olu_yol' (açık, klasörü diskte yok) ve 'terk_isler' (boş, maliyetsiz, terk_is_saat'ten eski;
    is_esleme.json, varsayılan 24) ekler. --kapat --uygula terk işleri mevcut kapatma yoluyla kapatır; ölü yola dokunmaz."""
    import is_olu_yol as O
    rapor["olu_yol"] = O.olu_yollar(sd)
    rapor["terk_isler"] = O.terk_isler(sd, bos_isler)
    if uygula and a.kapat:
        from komutlar import isler
        for g in rapor["terk_isler"]:
            if g["id"] in rapor["kapatilan_is"]:
                continue
            with contextlib.redirect_stdout(io.StringIO()):
                isler.cmd_is_kapat(argparse.Namespace(is_id=g["id"], ozetsiz=OZETSIZ_NEDEN))
            rapor["kapatilan_is"].append(g["id"])
    if a.json:
        return
    print(f"ölü yol: {len(rapor['olu_yol'])} açık iş kaydının klasörü diskte yok")
    for g in rapor["olu_yol"]:
        print(f"  {g['id']} {g['baslik'][:50]} ({g['klasor'] or '-'})")
    saat = rapor["terk_isler"][0]["saat_esigi"] if rapor["terk_isler"] else O.terk_saat(sd)
    print(f"terk: {len(rapor['terk_isler'])} boş, maliyetsiz açık iş (≥{saat:g} saat; is_esleme.json terk_is_saat)"
          + ("" if uygula and a.kapat else "; kapatmak için orkestra bakim --kapat --uygula"))
    for g in rapor["terk_isler"]:
        print(f"  {g['id']} {g['baslik'][:60]} ({g['yas_saat']} saat)")


def worktree_geride_uyari(kok: str | None = None) -> str:
    """I-271 P8: oturum bağlı bir git worktree'sindeyse ve ana ağaçta durum klasörü varsa (ADR-0033), worktree'nin
    .claude/orkestra kopyasındaki gunluk.jsonl ve maliyet.jsonl satır sayısını ana kopyayla karşılaştırır; ana kopya
    öndeyse tek satır uyarı, değilse (worktree değil, ana kopya yok, fark yok) ''."""
    kok = kok or L.oturum_koku()
    ana = L.ana_agac_koku(kok)
    if not ana:
        return ""
    wt_sd, ana_sd = (os.path.join(x, ".claude", "orkestra") for x in (kok, ana))
    if not (os.path.isdir(wt_sd) and os.path.isdir(ana_sd)):
        return ""

    def satir(d, ad):
        try:
            with open(os.path.join(d, ad), "rb") as f:
                return sum(1 for s in f if s.strip())
        except OSError:
            return 0
    fark = {ad: satir(ana_sd, ad + ".jsonl") - satir(wt_sd, ad + ".jsonl") for ad in ("gunluk", "maliyet")}
    if max(fark.values()) <= 0:
        return ""
    return f"worktree geride: gunluk {max(fark['gunluk'], 0)}, maliyet {max(fark['maliyet'], 0)} satır"


def cmd_bakim(a):
    sd = sd_gerekli()
    uygula = bool(a.uygula)
    locklar = lock_adaylari(sd, a.lock_gun)
    oturumlar = eski_oturumlar(sd, a.oturum_gun)
    ozet = defter_ozeti(sd)
    bos = bos_isler(sd, a.bos_saat)
    rapor = {"mod": "uygula" if uygula else "kuru", "lock": [_goreli(sd, x) for x in locklar],
             "oturum": [_goreli(sd, x) for x in oturumlar], "defter": ozet, "bos_isler": bos,
             "silinen_lock": 0, "arsivlenen_oturum": 0, "kapatilan_is": []}
    if uygula:
        for yol in oturumlar:
            ay = datetime.datetime.fromtimestamp(os.path.getmtime(yol)).strftime("%Y%m")
            hedef = os.path.join(sd, ARSIV_DIZINI, ay)
            os.makedirs(hedef, exist_ok=True)
            try:
                shutil.move(yol, os.path.join(hedef, os.path.basename(yol)))
                rapor["arsivlenen_oturum"] += 1
            except OSError:
                continue
        for yol in lock_adaylari(sd, a.lock_gun):  # taşınan oturumların lock'ları da yeniden taranır
            try:
                os.remove(yol)
                rapor["silinen_lock"] += 1
            except OSError:
                pass  # başka süreç tutuyor (Windows) ya da zaten silinmiş
        L.atomik_yaz(os.path.join(sd, "ortak_defter_ozet.json"),
                     json.dumps({"olcum_saati": L.simdi(), **ozet}, ensure_ascii=False, indent=2) + "\n")
        if a.kapat:
            from komutlar import isler
            for g in bos:
                with contextlib.redirect_stdout(io.StringIO()):  # kapatma çıktısı --json akışını bozmasın
                    isler.cmd_is_kapat(argparse.Namespace(is_id=g["id"], ozetsiz=OZETSIZ_NEDEN))
                rapor["kapatilan_is"].append(g["id"])
    olu_yol_ve_terk(sd, a, rapor, uygula)
    if a.json:
        print(json.dumps(rapor, ensure_ascii=False))
        return
    if not uygula:
        print("Bakım (kuru koşu: hiçbir şey değişmedi; işlemek için --uygula)")
    print(f"lock dosyası: {len(locklar)} eski ({a.lock_gun:g} gün)" + (f"; silinen {rapor['silinen_lock']}" if uygula else ""))
    print(f"oturum kaydı: {len(oturumlar)} eski ({a.oturum_gun:g} gün)" + (f"; arşivlenen {rapor['arsivlenen_oturum']}" if uygula else ""))
    aylar = ", ".join(f"{k}: {v}" for k, v in ozet["aylik"].items()) or "-"
    print(f"defter: {ozet['satir']} satır, {ozet['bayt']} bayt; aylık {aylar}")
    print(f"boş açık iş: {len(bos)} (kartsız, todo'suz, içeriği boş planlı, ≥{a.bos_saat:g} saat)")
    for g in bos:
        print(f"  {g['id']} {g['baslik'][:60]} ({g['yas_saat']} saat)")
    _u = hook_kural_uyari(sd)
    if _u:
        print(_u)
    _j = jira_izin_uyari(sd)
    if _j:
        print(_j)
    if a.kapat and not uygula:
        print(f"kuru: --kapat yalnız --uygula ile {len(bos)} işi --ozetsiz \"{OZETSIZ_NEDEN}\" ile kapatır")


def kaydet(alt):
    """Bu modülün alt komutlarını ana ayrıştırıcıya ekler."""
    b = alt.add_parser("bakim", help="durum klasörü hijyeni: eski lock, eski oturum kaydı, defter özeti, boş açık işler (varsayılan kuru koşu)")
    g = b.add_mutually_exclusive_group()
    g.add_argument("--kuru", action="store_true", help="yalnız listele (varsayılan)")
    g.add_argument("--uygula", action="store_true", help="silme/arşivleme/özet yazma işlemlerini yap")
    b.add_argument("--lock-gun", type=float, default=7, metavar="GUN", help="bu günden eski lock dosyaları (varsayılan 7)")
    b.add_argument("--oturum-gun", type=float, default=30, metavar="GUN", help="bu günden eski oturum kayıtları (varsayılan 30)")
    b.add_argument("--bos-saat", type=float, default=24, metavar="SAAT", help="boş sayılması için en az iş yaşı (varsayılan 24)")
    b.add_argument("--kapat", action="store_true", help=f"boş açık işleri --ozetsiz \"{OZETSIZ_NEDEN}\" ile kapat (--uygula ile)")
    b.add_argument("--json", action="store_true")
    b.set_defaults(f=cmd_bakim)
