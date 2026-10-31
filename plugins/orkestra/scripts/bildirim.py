"""Windows toast bildirimi: insan aksiyonu gereken anlarda (iş bitti, yanıt/onay bekleniyor) kullanıcıyı sisteme geri çağırır.

Kanal yalnız yerel toast'tır; dışarı veri gitmez. Toast'a tıklayınca `claude://` ile Claude uygulaması öne gelir.
Kapatma: panelde Ayarlar > Bildirim (makine config'i, cfg 'bildirim') ya da ORKESTRA_BILDIRIM=0 (ortam değişkeni önceliklidir). Tur bildirimi için en kısa tur süresi: ORKESTRA_BILDIRIM_MIN_S (varsayılan 30 sn).

'İş bitti' yalnız çalışma gerçekten durduğunda gider (tur_sonu): tur biterken arka plan görevi (Bash/Agent/Workflow) açıksa toast
ertelenir ve çalışmanın başlangıcı saklanır; görev bitince Claude'u uyandıran bildirim turunun sonunda gider. Süre, önceki
durak ile kullanıcı isteği arasındaki bekleme hariç, çalışmanın başladığı kullanıcı isteğinden ölçülür.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

import cfg
import ork_lib as L

TUR_ESIK_S = 30
ACIK_AZAMI_S = 7200  # arka plan görevinin bitiş bildirimi hiç gelmezse (oturum öldü) toast bu süreden sonra yine de gider
IDLE_TEKRAR_S = 600  # tur bildirimi gittiyse aynı oturumda bu süre içinde 'idle' bildirimi tekrarlanmaz

_PS = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType=WindowsRuntime] | Out-Null
$x = New-Object Windows.Data.Xml.Dom.XmlDocument
$x.LoadXml('<toast activationType="protocol" launch="claude://"><visual><binding template="ToastText02"><text id="1"></text><text id="2"></text></binding></visual></toast>')
$t = $x.GetElementsByTagName('text')
$t.Item(0).InnerText = $env:ORK_TOAST_BASLIK
$t.Item(1).InnerText = $env:ORK_TOAST_METIN
$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show([Windows.UI.Notifications.ToastNotification]::new($x))
"""


def ayar() -> tuple[bool, str]:
    """(açık mı, kaynak): kaynak ortam | makine | varsayilan. Ortam değişkeni (ORKESTRA_BILDIRIM) panel ayarından önce gelir."""
    deger, kaynak = cfg.kaynakli_al("bildirim", None, "1")
    return str(deger).strip() != "0", kaynak


def ayar_yaz(acik: bool) -> str:
    """Panel ayarını makine config'ine yazar ('1' | '0'); yazılan dosyanın yolunu döner."""
    return cfg.makine_yaz({"bildirim": "1" if acik else "0"}, kaynak="panel")


def aktif() -> bool:
    return sys.platform == "win32" and ayar()[0] and not os.environ.get("ORKESTRA_PERSPEKTIF")


def tek_satir(metin, en_cok: int = 140) -> str:
    s = re.sub(r"\s+", " ", L.maskele(str(metin or ""))).strip()
    return s if len(s) <= en_cok else s[: en_cok - 1] + "…"


def gonder(baslik: str, metin: str) -> bool:
    """Toast'u ayrı süreçte atar; kancayı bekletmez. Başarısızlık sessizdir."""
    if not aktif():
        return False
    env = dict(os.environ, ORK_TOAST_BASLIK=tek_satir(baslik, 60), ORK_TOAST_METIN=tek_satir(metin))
    try:
        subprocess.Popen(["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", _PS],
                         env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return True
    except Exception:
        return False


def _son_yolu(sd: str) -> str:
    return os.path.join(sd, "bildirim_son.json")


def son_oku(sd: str, oid: str) -> float:
    try:
        with open(_son_yolu(sd), encoding="utf-8") as f:
            return float(json.load(f).get(oid) or 0)
    except Exception:
        return 0.0


def son_yaz(sd: str, oid: str) -> None:
    yol = _son_yolu(sd)
    with L.kilit(yol):
        try:
            with open(yol, encoding="utf-8") as f:
                d = json.load(f)
            if not isinstance(d, dict):
                d = {}
        except Exception:
            d = {}
        simdi = time.time()
        d = {k: v for k, v in d.items() if isinstance(v, (int, float)) and simdi - v < 86400}
        d[oid] = simdi
        L.atomik_yaz(yol, json.dumps(d))


def tur_esigi() -> float:
    try:
        return float(os.environ.get("ORKESTRA_BILDIRIM_MIN_S", TUR_ESIK_S))
    except ValueError:
        return float(TUR_ESIK_S)


def tur_bitti(sd: str, oid: str, sure_ms, son_mesaj: str, is_baslik: str = "") -> bool:
    """Tur sonunda: yeterince uzun sürdüyse 'iş bitti' ya da (mesaj soruyla bitiyorsa) 'yanıt bekliyor' toast'ı."""
    if not aktif() or not isinstance(sure_ms, (int, float)) or sure_ms / 1000 < tur_esigi():
        return False
    mesaj = tek_satir(son_mesaj, 300)
    soru = mesaj.rstrip("*_` ").endswith("?")
    baslik = "Orkestra: yanıtınız bekleniyor" if soru else "Orkestra: iş bitti"
    govde = mesaj[-140:] if soru else (is_baslik or mesaj)
    if gonder(baslik, govde):
        son_yaz(sd, oid)
        return True
    return False


def _calisma_yolu(sd: str) -> str:
    return os.path.join(sd, "bildirim_calisma.json")


def calisma_oku(sd: str, oid: str) -> str | None:
    """Arka plan görevi yüzünden ertelenen çalışmanın başlangıç zamanı (ISO) ya da None."""
    try:
        with open(_calisma_yolu(sd), encoding="utf-8") as f:
            v = json.load(f).get(oid)
        return v if isinstance(v, str) and v else None
    except Exception:
        return None


def calisma_yaz(sd: str, oid: str, basi: str | None) -> None:
    """basi verilirse kaydeder, None ise siler. 1 günden eski kayıtlar atılır."""
    yol = _calisma_yolu(sd)
    with L.kilit(yol):
        try:
            with open(yol, encoding="utf-8") as f:
                d = json.load(f)
            if not isinstance(d, dict):
                d = {}
        except Exception:
            d = {}
        simdi = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        d = {k: v for k, v in d.items() if isinstance(v, str) and (L.sure_ms(v, simdi) or 0) < 86400_000}
        if basi:
            d[oid] = basi
        else:
            d.pop(oid, None)
        L.atomik_yaz(yol, json.dumps(d))


def tur_sonu(sd: str, oid: str, istem_zamani, son_zaman, arka_plan_acik: bool, son_mesaj: str, is_baslik: str = "") -> bool:
    """Stop anında tek karar noktası. Arka plan görevi açıksa çalışma sürüyor: toast gitmez, başlangıç saklanır.
    Görev yoksa çalışma bitti: süre saklanan başlangıçtan (yoksa bu turun kullanıcı isteğinden) ölçülür ve 'iş bitti' gider."""
    if not aktif():
        return False
    saklanan = calisma_oku(sd, oid)
    basi = saklanan or (istem_zamani if isinstance(istem_zamani, str) else None)
    if arka_plan_acik:
        yas = L.sure_ms(basi, son_zaman) if basi and isinstance(son_zaman, str) else None
        if yas is None or yas / 1000 < ACIK_AZAMI_S:
            if basi and not saklanan:
                calisma_yaz(sd, oid, basi)
            return False
    if saklanan:
        calisma_yaz(sd, oid, None)
    return tur_bitti(sd, oid, L.sure_ms(basi, son_zaman) if basi and isinstance(son_zaman, str) else None, son_mesaj, is_baslik)


def _arka_plan_var(sd: str, oid: str) -> bool:
    """Stop kancasının oturum dosyasına yazdığı açık arka plan görevi listesi dolu mu."""
    try:
        with open(os.path.join(sd, "oturumlar", f"{oid}.json"), encoding="utf-8") as f:
            return bool(json.load(f).get("acik_gorevler"))
    except Exception:
        return False


def bildirim_olayi(sd: str, oid: str, inp: dict) -> bool:
    """Claude Code `Notification` olayı: izin istemi ve girdi bekleme."""
    tur = str(inp.get("notification_type") or "")
    if tur == "idle_prompt" and time.time() - son_oku(sd, oid) < IDLE_TEKRAR_S:
        return False  # tur sonu toast'ı zaten gitti
    if tur == "idle_prompt" and _arka_plan_var(sd, oid):
        return False  # arka plan görevi sürüyor: Claude bekliyor değil, çalışıyor
    baslik = "Orkestra: onayınız gerekiyor" if tur == "permission_prompt" else "Orkestra: sizi bekliyor"
    return gonder(baslik, inp.get("message") or "Claude girdi bekliyor.")
