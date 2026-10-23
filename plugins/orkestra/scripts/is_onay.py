"""İş onayı (P-016): onay gelmeden uygulamaya (kod/dosya değişikliği, commit, bağımlılık ekleme) geçilmez.

Saf Python, model çağrılmaz. Durum işin is.json'unda `onay` alanıdır: `bekliyor` | `verildi`. Alan yoksa kapı yoktur
(eski işler kilitlenmez). Yeni sıralı iş `bekliyor` doğar; `is devam` alansız sıralı işte todo'da biten madde yoksa
`bekliyor`, varsa `verildi` koyar. Durumu yalnız kullanıcının onay mesajı `verildi` yapar (hook.user_prompt_submit);
ajanın kabuktan `orkestra is onayla` çalıştırması hook'ta reddedilir. ORKESTRA_ONAY_KAPISI=0 kapıyı kapatır.
"""
from __future__ import annotations

import os
import re

import is_sirasi as SIRA
import ork_lib as L

ALAN = "onay"
BEKLIYOR = "bekliyor"
VERILDI = "verildi"
BEKLEYEN_ALAN = "onay_bekleyen"  # ADR-0070: eksik belge yüzünden kaydedilemeyen onay mesajının zamanı
BEKLEYEN_YENI = "bekleyen"  # baglam_satiri'nın "onayı sakla" sinyali
AZAMI_MESAJ = 200
MOD_ALANI = "mod"  # ADR-0009: iş başına çalışma modu
MOD_PLAN = "plan"
MOD_AUTO = "auto"
_MOD = re.compile(r"^\s*/(?:orkestra:)?(plan|auto)\b", re.I)  # ADR-0021: eklenti önekli komut da mod yazar

_ONAY = re.compile(
    r"^\W*(?:/onay|onay\w*|onal\w*|tamam\w*|olur|evet|yap|yapal[ıi]m|yapabilirsin|ba[sş]la\w*|uygun|uygula\w*|kabul\w*|devam(?:\s+et\w*)?|ok|okay)\b",
    re.I)
# Tek harfli kısayol (y, o, e, q) yalnız mesajın tamamıysa onaydır; "o bir sorun" gibi cümleler eşleşmez.
_ONAY_KISA = re.compile(r"^\W*[yoeq]\W*$", re.I)
# Onay fiili cümlenin içinde geçebilir ("Planı onaylıyorum", "kabul ediyorum"); kök: onayl(ı)yor, onayladım, onay veriyorum.
_ONAY_FIIL = re.compile(r"\b(?:onayl(?:[ıi]yor|ad[ıi])\w*|onay\s+veriyor\w*|kabul\s+ed(?:iyor|tim|ildi)\w*)", re.I)
_KOSUL = re.compile(r"\b(?:ama|fakat|ancak|lakin|yeter\s+ki|[sş]art[ıi]yla)\b", re.I)
_RED = re.compile(r"\b(?:hay[ıi]r|de[gğ]il|yapma\w*|bekle\w*|dur|durdur|iptal|onaylam\w*|olmaz|\w+m[ıiuü]yor\w*)\b", re.I)
# I-168 (ADR-0035): icra niyeti. Yalnız emir/izin biçimleri; "yapıyor", "devam ediyor" gibi anlatım eşleşmez.
_ICRA = re.compile(
    r"\b(?:yap(?:[ıi]n|abilirsin|sana|s[ıi]n)?|gerekeni\s+yap\w*|hallet(?:sin|sene|in)?|halledelim|[çc][öo]z(?:elim|sene)?"
    r"|ilerle(?:yelim)?|devam\s+et\w*|go\s+ahead|proceed|ba[sş]la(?:yal[ıi]m|yın)?)\b", re.I)
# Bulanık eşleşme: yazım hatalı onay fiili ("onaylyıorum"); 5 harften kısa sözcükte kapalı.
_ONAY_KOKLERI = ("onaylıyorum", "onayladım", "onaylıyoruz", "onaylandı", "tamamdır", "başlayalım", "uygulayalım")
BULANIK_ESIK = 0.85

# Onay beklerken ana ya da alt ajanın kabukta çalıştıramayacağı komutlar (tırnak içi metin atılmış komuta uygulanır)
KABUK_YASAK = re.compile(
    r"(?:^|[;&|(`]\s*|\s)(?:"
    r"git(?:\s+-{1,2}[^\s=]+(?:=\S+)?(?:\s+[^\s-]\S*)?)*\s+(?:commit|add|push|merge|rebase|reset|cherry-pick|am|apply|stash)\b"
    r"|(?:pip3?|pipenv|poetry|uv|npm|pnpm|yarn|conda|cargo|gem|composer)\s+(?:\S+\s+)?(?:install|add|i)\b"
    r"|python3?\s+-m\s+pip\s+(?:install|uninstall)\b"
    r"|orkestra(?:\.py|\.cmd)?\s+is\s+onayla\b"
    r")", re.I)
IS_JSON_YAZIMI = re.compile(r"(?:>|\btee\b|\bsed\s+-i|\bcp\b|\bmv\b|\bdel\b|\brm\b|Set-Content|Out-File|Add-Content)[^\n;|&]*is\.json", re.I)


def kapi_acik() -> bool:
    return os.environ.get("ORKESTRA_ONAY_KAPISI") != "0"


def mod_kapisi_acik() -> bool:
    return os.environ.get("ORKESTRA_MOD_KAPISI") != "0"


def mod_mesaji(metin: str) -> str | None:
    """Mesaj `/plan`, `/auto` ya da `/orkestra:` önekli biçimiyle başlıyorsa mod adı, yoksa None (ADR-0009, ADR-0021)."""
    m = _MOD.match(metin or "")
    return m.group(1).lower() if m and mod_kapisi_acik() else None


def mod(kayit: dict | None) -> str:
    """İşin modu; alan yoksa ya da geçersizse `plan`."""
    return MOD_AUTO if (kayit or {}).get(MOD_ALANI) == MOD_AUTO and mod_kapisi_acik() else MOD_PLAN


def mod_yaz(sd: str, is_id: str, yeni: str) -> dict:
    """Modu yalnız kullanıcı mesajını işleyen hook yazar (ajan is.json yazamaz)."""
    import is_kaydi
    import ork_lib as L

    def islem(k):
        k[MOD_ALANI] = yeni
        k.setdefault("gecmis", []).append({"zaman": L.simdi(), "olay": f"mod:{yeni}"})

    return is_kaydi._degistir(sd, is_id, islem)


def _bekleyen_yol(sd: str, oturum) -> str:
    return os.path.join(sd, "oturumlar", f"mod_{oturum}.json")


def bekleyen_mod_yaz(sd: str, oturum, yeni: str) -> None:
    """İş bağlı değilken gelen `/plan` ya da `/auto`: mod oturumda tutulur, iş bağlanınca uygulanır."""
    import json
    os.makedirs(os.path.join(sd, "oturumlar"), exist_ok=True)
    with open(_bekleyen_yol(sd, oturum), "w", encoding="utf-8") as f:
        json.dump({MOD_ALANI: yeni}, f)


def bekleyen_mod_al(sd: str, oturum) -> str | None:
    """Bekleyen modu okur ve siler; yoksa None."""
    import json
    yol = _bekleyen_yol(sd, oturum)
    try:
        with open(yol, encoding="utf-8") as f:
            v = (json.load(f) or {}).get(MOD_ALANI)
        os.remove(yol)
    except (OSError, ValueError):
        return None
    return v if v in (MOD_PLAN, MOD_AUTO) else None


def otomatik_onay(sd: str, kayit: dict | None) -> bool:
    """`auto` modda onay bekleyen işin belgeleri tamamsa onayı `verildi` yapar; yapıldıysa True."""
    if not kayit or mod(kayit) != MOD_AUTO or durum(kayit) != BEKLIYOR or not kapi_acik():
        return False
    if belge_eksikleri(str(kayit.get("klasor") or "")):
        return False
    yaz(sd, kayit["id"], VERILDI, "onay:auto")
    return True


def durum(kayit: dict | None) -> str | None:
    v = (kayit or {}).get(ALAN)
    return v if v in (BEKLIYOR, VERILDI) else None


def bekliyor_mu(kayit: dict | None) -> bool:
    return kapi_acik() and durum(kayit) == BEKLIYOR


def onay_mesaji_mi(metin: str) -> bool:
    """Kısa, soru olmayan, ilk cümleciğinde (ilk ; . , öncesi) olumsuzlama içermeyen, onay sözcüğüyle başlayan mesaj."""
    m = (metin or "").strip()
    if not m or len(m) > AZAMI_MESAJ or "?" in m or m.startswith("<"):
        return False
    m = m.replace("İ", "i").replace("I", "ı")
    ilk = re.split(r"[;.,]", m, maxsplit=1)[0]  # I-138 P15: ret kalıbı yalnız ilk cümlecikte aranır
    if _RED.search(ilk):
        return False
    if _ONAY.match(m) or _ONAY_KISA.match(m):
        return True
    # I-154: "Planı (P1-P10) onaylıyorum, K3 ve K5 önerildiği gibi" onay sözcüğüyle başlamaz; onay fiili ilk cümlecikte
    # geçiyorsa ve mesaj koşul/itiraz bağlacı taşımıyorsa onaydır (yanlış onay pahalı: bağlaç varsa onay sayılmaz).
    # I-168: icra niyeti ("ne gerekiyorsa yap") ve yazım hatalı onay fiili de aynı korumalarla onaydır.
    niyet = _ONAY_FIIL.search(m) or _ICRA.search(m) or _bulanik_onay(m)
    return bool(niyet) and not _KOSUL.search(m) and not _RED.search(m)


def mesaj_sinifi(metin: str) -> str:
    """I-168: `onay` | `ret` | `soru` | `belirsiz` | `diger` (boş, sistem iletisi, komut ya da uzun mesaj)."""
    m = (metin or "").strip()
    if not m or len(m) > AZAMI_MESAJ or m.startswith(("<", "/")):
        return "diger"
    if onay_mesaji_mi(m):
        return "onay"
    if "?" in m:
        return "soru"
    ilk = re.split(r"[;.,]", m.replace("İ", "i").replace("I", "ı"), maxsplit=1)[0]
    return "ret" if _RED.search(ilk) else "belirsiz"


def aday_yaz(sd: str, metin: str, sinif: str) -> None:
    """Onay bekleyen işte onay sayılmayan kısa mesajı günlüğe yazar (kalıp listesi gerçek mesajdan büyür); hata yutulur."""
    import json
    import time
    try:
        with open(os.path.join(sd, "onay_adaylari.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "sinif": sinif,
                                "mesaj": (metin or "").strip()[:AZAMI_MESAJ]}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _bulanik_onay(m: str) -> bool:
    import difflib
    for kelime in re.findall(r"\w+", m.lower()):
        if len(kelime) >= 5 and difflib.get_close_matches(kelime, _ONAY_KOKLERI, n=1, cutoff=BULANIK_ESIK):
            return True
    return False


def belge_eksikleri(klasor: str) -> list[str]:
    """Onayın ön koşulu: mevcut durum, plan ve todo tamam (todo en az bir madde). Boş liste = hazır."""
    adim, eksik = SIRA.adim(klasor)
    if eksik:
        return eksik
    import is_kaydi
    if is_kaydi.todo_ozet(klasor)["toplam"] < 1:
        return ["todo.md yok ya da madde içermiyor (`orkestra is todo <id> --ekle \"P1: …\"`)"]
    return []


def ilk_durum(klasor: str) -> str:
    """Alansız sıralı iş için `is devam` kararı: todo'da biten madde yoksa iş başlamamıştır."""
    import is_kaydi
    return BEKLIYOR if is_kaydi.todo_ozet(klasor)["biten"] == 0 else VERILDI


def yaz(sd: str, is_id: str, yeni: str, olay: str) -> dict:
    import is_kaydi
    import ork_lib as L

    def islem(k):
        k[ALAN] = yeni
        k.pop(BEKLEYEN_ALAN, None)
        k.setdefault("gecmis", []).append({"zaman": L.simdi(), "olay": olay})

    return is_kaydi._degistir(sd, is_id, islem)


def bekleyen_mi(kayit: dict | None) -> bool:
    return bool((kayit or {}).get(BEKLEYEN_ALAN))


def bekleyen_yaz(sd: str, is_id: str) -> dict:
    """ADR-0070: kullanıcı onay mesajı gönderdi ama belgeler eksikti; onay, eksik giderilince verilmek üzere saklanır."""
    import is_kaydi
    import ork_lib as L

    def islem(k):
        k[BEKLEYEN_ALAN] = L.simdi()
        k.setdefault("gecmis", []).append({"zaman": L.simdi(), "olay": "onay:bekleyen"})

    return is_kaydi._degistir(sd, is_id, islem)


def bekleyen_temizle(sd: str, is_id: str) -> dict:
    """Kullanıcı onay dışı bir mesaj yazdı: saklı onay düşer (konu ya da niyet değişmiş olabilir)."""
    import is_kaydi
    import ork_lib as L

    def islem(k):
        if k.pop(BEKLEYEN_ALAN, None):
            k.setdefault("gecmis", []).append({"zaman": L.simdi(), "olay": "onay:bekleyen-iptal"})

    return is_kaydi._degistir(sd, is_id, islem)


def bekleyen_onay_ver(sd: str, kayit: dict | None) -> bool:
    """Saklı onay varsa ve belgeler artık tamamsa onayı `verildi` yapar (ADR-0070); yapıldıysa True. Kullanıcıdan yeniden onay istenmez."""
    if not kayit or not kapi_acik() or durum(kayit) != BEKLIYOR or not bekleyen_mi(kayit):
        return False
    if belge_eksikleri(str(kayit.get("klasor") or "")):
        return False
    yaz(sd, kayit["id"], VERILDI, "onay:bekleyen-verildi")
    return True


def yazma_engeli(kayit: dict, proje: str, tam: str) -> str:
    """`bekliyor` iken yazılan dosya izinli mi: işin klasörü (is.json hariç) ve proje adr/ klasörü izinlidir.
    İş klasörü projenin kökü ya da atası ise yalnız .md dosyaları izinlidir. Boş döner = izin."""
    tam = os.path.normcase(os.path.abspath(tam))
    if os.path.basename(tam) == "is.json":
        return "is.json elle yazılmaz; onayı yalnız kullanıcı mesajı verir."
    for kok in {proje, L.baglanti_koku(proje)}:  # oturum bağlı worktree'deyse onun adr/ klasörü de (ADR-0035)
        adr = os.path.normcase(os.path.abspath(os.path.join(kok, "adr")))
        if tam.startswith(adr + os.sep):
            return ""
    klasor = os.path.normcase(os.path.abspath(str(kayit.get("klasor") or "")))
    if klasor and tam.startswith(klasor + os.sep):
        proje_n = os.path.normcase(os.path.abspath(proje))
        genis = proje_n == klasor or proje_n.startswith(klasor + os.sep)
        if not genis or tam.endswith(".md"):
            return ""
    return ("iş onay bekliyor (P-016): önce mevcut durum → plan → todo hazırlanır, bağlantılarıyla kullanıcıya gösterilir; "
            "kullanıcı onaylamadan işin belgeleri dışında dosya yazılmaz. Kapatma: ORKESTRA_ONAY_KAPISI=0.")


# ADR-0031: kullanıcı commit/push'u açıkça istediği turda yalnız bu git alt komutları kapıdan geçer.
GIT_IZINLI = ("commit", "add", "push", "reset", "merge")
_GIT_EMRI = re.compile(r"\b(?:commit|push)(?:'?l[ae](?!r)\w*|'?[au]\b|\s+(?:et|yap)\w*)", re.I)
_GIT_OLUMSUZ = re.compile(r"\b(?:commit|push)\w*?(?:lama|leme|etme|yapma)", re.I)


def git_emri_mi(metin: str) -> bool:
    """Kısa, soru olmayan, ret içermeyen mesaj commit/push'u fiil olarak istiyor mu ('commitle pushla', 'pusha', 'commit et')."""
    m = (metin or "").strip()
    if not m or len(m) > AZAMI_MESAJ or "?" in m or m.startswith("<"):
        return False
    return bool(_GIT_EMRI.search(m)) and not _RED.search(m) and not _GIT_OLUMSUZ.search(m)


_GIT_OTURUM = re.compile(r"\b(?:push|commit)\w*\b[^.?!]{0,30}\b(?:serbest|izinli|sorma\w*)\b|\b(?:serbest|izinli)\b[^.?!]{0,20}\b(?:push|commit)", re.I)


def git_oturum_izni_mi(metin: str) -> bool:
    """ADR-0036: 'push serbest', 'pushlarda sorma' gibi mesaj push/commit'i oturum boyu serbest bırakır."""
    m = (metin or "").strip()
    if not m or len(m) > AZAMI_MESAJ or "?" in m or m.startswith("<"):
        return False
    return (bool(_GIT_OTURUM.search(m)) and not _RED.search(m) and not _GIT_OLUMSUZ.search(m)
            and not re.search(r"b[ıi]rakma|verme|kapat", m, re.I))


def git_izni_isle(sd: str, oturum, metin: str) -> bool:
    """Her kullanıcı mesajında (ADR-0036 onay kaydı): tur kayıtları silinir; emirse tur, 'serbest' ise oturum kaydı yazılır.
    Emir ya da oturum izni var mı döner."""
    if not oturum:
        return False
    import onay_kaydi
    onay_kaydi.tur_temizle(sd, oturum)
    if git_oturum_izni_mi(metin):
        onay_kaydi.ekle(sd, oturum, "git", "oturum")
        return True
    if git_emri_mi(metin):
        onay_kaydi.ekle(sd, oturum, "git", "tur")
        return True
    return False


def git_izni_var(sd: str, oturum) -> bool:
    import onay_kaydi
    return onay_kaydi.var(sd, oturum, "git")


def _git_izinli_mi(eslesme: str) -> bool:
    if not re.match(r"[;&|(`\s]*git\b", eslesme, re.I):
        return False
    return eslesme.split()[-1].lower() in GIT_IZINLI


def kabuk_engeli(tirnaksiz_komut: str, git_izni: bool = False) -> str:
    yasak = [m.group(0) for m in KABUK_YASAK.finditer(tirnaksiz_komut)]
    if git_izni:
        yasak = [y for y in yasak if not _git_izinli_mi(y)]
    if yasak or IS_JSON_YAZIMI.search(tirnaksiz_komut):
        return ("iş onay bekliyor (P-016): commit, ekleme/itme, bağımlılık kurma ve onay komutu kullanıcı onayından önce "
                "çalıştırılmaz. Mevcut durum → plan → todo'yu bağlantılarıyla göster, kullanıcının onayını bekle.")
    return ""


TUR_BITIREN = ("wrap_up", "AskUserQuestion", "ExitPlanMode")  # çağrılınca tur kullanıcıya geçer; son metin bunlardan önce yazılmış olmalı


def tur_bitiren_mi(arac: str) -> bool:
    return bool(arac) and arac.split("__")[-1] in TUR_BITIREN


def teslim_imzasi(klasor: str, proje: str) -> tuple[str, list[str]]:
    """Kutudan önce yanıta yazılacak belge bağlantıları: (imza, satırlar). İmza belgelerin değişim zamanından türer;
    satır yoksa imza boştur."""
    import is_kaydi
    satirlar = is_kaydi.belge_baglantilari(klasor, proje)
    parca = []
    for ad in sorted(os.listdir(klasor)) if os.path.isdir(klasor) else []:
        if ad.endswith(".md"):
            try:
                parca.append(f"{ad}:{int(os.path.getmtime(os.path.join(klasor, ad)))}")
            except OSError:
                pass
    return ("|".join(parca) if satirlar else ""), satirlar


def baglam_satiri(kayit: dict, mesaj_onay: bool, belirsiz: bool = False) -> tuple[str, str | None]:
    """UserPromptSubmit için (bağlam satırı, yeni durum). `bekliyor` değilse ('', None)."""
    if not bekliyor_mu(kayit):
        return "", None
    klasor = str(kayit.get("klasor") or "")
    if mesaj_onay:
        eksik = belge_eksikleri(klasor)
        if not eksik:
            return ("Orkestra: kullanıcı onayladı (P-016); iş onaylandı, uygulamaya geçilebilir. Çalışma özeti kapanışta en son verilir.",
                    VERILDI)
        return ("Orkestra (P-016): onay mesajı geldi ama belgeler hazır değil; onay saklandı, eksik giderilince kendiliğinden verilir "
                "(kullanıcıdan yeniden onay isteme). Eksik: " + "; ".join(eksik[:4])
                + ". Eksiği düzelt (belgeleri aynen kullanıcının onayladığı kapsamda tut), sonra uygulamaya geç.", BEKLEYEN_YENI)
    harita = (" Önce `orkestra harita oku` ile sistem haritasını oku (.claude/orkestra/sistem_haritasi/INDEX.md); "
              "mevcut durumda dokunduğun yerdeki var olan kayıtları ve plan maddesinde `**Mevcut varlık:**` alanını yaz.") if kayit.get("harita") else ""
    soru = (" Son mesaj onay sayılmadı ama başlatma niyeti taşıyor olabilir: niyet buysa tek cümleyle 'bunu onay sayayım mı?' diye sor "
            "(\"tek kelime yaz\" deme); tartışma ya da düzeltmeyse sormadan yanıtla.") if belirsiz else ""
    return ("Orkestra (P-016): iş onay bekliyor; uygulama (kod/dosya, commit, bağımlılık) yok. Mevcut durum → plan → todo "
            "sırasıyla hazırla ve bağlantılarıyla göster; kullanıcı onaylayınca iş başlar. SIRA (K-003): onay isteyen kutu/soru "
            "aracı (wrap_up, AskUserQuestion) turu bitirir; bağlantı satırlarını (`orkestra is baglanti " + str(kayit.get("id", "<id>"))
            + "` hazır verir) önce yanıt METNİNE yaz, kutuyu en son çağır." + harita + soru, None)
