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

ALAN = "onay"
BEKLIYOR = "bekliyor"
VERILDI = "verildi"
AZAMI_MESAJ = 200

_ONAY = re.compile(
    r"^\W*(?:/onay|onay\w*|tamam\w*|olur|evet|yap|yapal[ıi]m|yapabilirsin|ba[sş]la\w*|uygun|kabul\w*|devam(?:\s+et\w*)?|ok|okay)\b",
    re.I)
_RED = re.compile(r"\b(?:hay[ıi]r|de[gğ]il|yapma\w*|bekle\w*|dur|durdur|iptal|onaylam\w*|olmaz)\b", re.I)

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


def durum(kayit: dict | None) -> str | None:
    v = (kayit or {}).get(ALAN)
    return v if v in (BEKLIYOR, VERILDI) else None


def bekliyor_mu(kayit: dict | None) -> bool:
    return kapi_acik() and durum(kayit) == BEKLIYOR


def onay_mesaji_mi(metin: str) -> bool:
    """Kısa, soru olmayan, olumsuzlama içermeyen ve onay sözcüğüyle başlayan kullanıcı mesajı."""
    m = (metin or "").strip()
    if not m or len(m) > AZAMI_MESAJ or "?" in m or m.startswith("<"):
        return False
    m = m.replace("İ", "i").replace("I", "ı")
    return bool(_ONAY.match(m)) and not _RED.search(m)


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
        k.setdefault("gecmis", []).append({"zaman": L.simdi(), "olay": olay})

    return is_kaydi._degistir(sd, is_id, islem)


def yazma_engeli(kayit: dict, proje: str, tam: str) -> str:
    """`bekliyor` iken yazılan dosya izinli mi: işin klasörü (is.json hariç) ve proje adr/ klasörü izinlidir.
    İş klasörü projenin kökü ya da atası ise yalnız .md dosyaları izinlidir. Boş döner = izin."""
    tam = os.path.normcase(os.path.abspath(tam))
    if os.path.basename(tam) == "is.json":
        return "is.json elle yazılmaz; onayı yalnız kullanıcı mesajı verir."
    adr = os.path.normcase(os.path.abspath(os.path.join(proje, "adr")))
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


def kabuk_engeli(tirnaksiz_komut: str) -> str:
    if KABUK_YASAK.search(tirnaksiz_komut) or IS_JSON_YAZIMI.search(tirnaksiz_komut):
        return ("iş onay bekliyor (P-016): commit, ekleme/itme, bağımlılık kurma ve onay komutu kullanıcı onayından önce "
                "çalıştırılmaz. Mevcut durum → plan → todo'yu bağlantılarıyla göster, kullanıcının onayını bekle.")
    return ""


def baglam_satiri(kayit: dict, mesaj_onay: bool) -> tuple[str, str | None]:
    """UserPromptSubmit için (bağlam satırı, yeni durum). `bekliyor` değilse ('', None)."""
    if not bekliyor_mu(kayit):
        return "", None
    klasor = str(kayit.get("klasor") or "")
    if mesaj_onay:
        eksik = belge_eksikleri(klasor)
        if not eksik:
            return ("Orkestra: kullanıcı onayladı (P-016); iş onaylandı, uygulamaya geçilebilir. Çalışma özeti kapanışta en son verilir.",
                    VERILDI)
        return ("Orkestra (P-016): onay mesajı geldi ama belgeler hazır değil, onay kaydedilmedi. Eksik: "
                + "; ".join(eksik[:4]) + ". Belgeleri tamamla, sırayla (mevcut durum → plan → todo) bağlantılarıyla göster.", None)
    return ("Orkestra (P-016): iş onay bekliyor; uygulama (kod/dosya, commit, bağımlılık) yok. Mevcut durum → plan → todo "
            "sırasıyla hazırla ve bağlantılarıyla göster; kullanıcı onaylayınca iş başlar.", None)
