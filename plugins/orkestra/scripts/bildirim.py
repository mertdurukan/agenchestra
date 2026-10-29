"""Windows toast bildirimi: insan aksiyonu gereken anlarda (iş bitti, yanıt/onay bekleniyor) kullanıcıyı sisteme geri çağırır.

Kanal yalnız yerel toast'tır; dışarı veri gitmez. Toast'a tıklayınca `claude://` ile Claude uygulaması öne gelir.
Kapatma: panelde Ayarlar > Bildirim (makine config'i, cfg 'bildirim') ya da ORKESTRA_BILDIRIM=0 (ortam değişkeni önceliklidir). Tur bildirimi için en kısa tur süresi: ORKESTRA_BILDIRIM_MIN_S (varsayılan 30 sn).
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


def bildirim_olayi(sd: str, oid: str, inp: dict) -> bool:
    """Claude Code `Notification` olayı: izin istemi ve girdi bekleme."""
    tur = str(inp.get("notification_type") or "")
    if tur == "idle_prompt" and time.time() - son_oku(sd, oid) < IDLE_TEKRAR_S:
        return False  # tur sonu toast'ı zaten gitti
    baslik = "Orkestra: onayınız gerekiyor" if tur == "permission_prompt" else "Orkestra: sizi bekliyor"
    return gonder(baslik, inp.get("message") or "Claude girdi bekliyor.")
