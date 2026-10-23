"""Panel gelen kutusu için eklenti güncelleme durumu: arka plan yoklaması, erteleme ve güncelleme koşusu.

Sürüm kontrolü ve koşu `guncelle.py`'dedir (CLI ile aynı kod); burası yalnız panel sunucusunun bellek durumunu,
30 dk'lık yoklamayı ve "Sonra" erteleme dosyasını tutar. Kullanıcı düzeyindedir: çalışma alanı almaz (ADR-0039).
Testte `kontrol`, `kosu`, `dizin` ve `saat` değiştirilir.
"""
from __future__ import annotations

import json
import os
import threading
import time

import guncelle as G
import ork_lib as L

YOKLAMA_ARALIGI = 30 * 60   # sn; sunucu açılışında ve bundan sonra en çok bu sıklıkta git fetch
BITTI_GOSTER = 10 * 60      # sn; başarılı güncellemeden sonra "güncellendi" kartı bu kadar görünür
ERTELEME_DOSYASI = "guncelleme_ertele.json"


class Guncelleme:
    def __init__(self, dizin: str | None = None, kontrol=None, kosu: G.Kosu | None = None, ev: str | None = None,
                 saat=time.time):
        self._dizin = dizin or L.GENEL_DIZIN
        self._kontrol = kontrol or G.kontrol
        self._ev = ev
        self._saat = saat
        self.kosu = kosu or G.Kosu(ev=ev)
        self._kilit = threading.Lock()
        self._son: dict | None = None
        self._son_zaman: float | None = None
        self._kosu_sonrasi_yenilendi = True
        self._durdur = threading.Event()
        self._is: threading.Thread | None = None

    # ---- yoklama -------------------------------------------------------------------------------------------
    def yokla(self, getir: bool = True) -> dict:
        """Sürümü kontrol eder ve saklar. Ağ hatası daha önce bulunmuş 'yeni' sonucunu silmez (kart titremez)."""
        try:
            s = self._kontrol(ev=self._ev, getir=getir)
        except Exception as e:  # noqa: BLE001: yoklama sunucuyu düşürmemeli
            s = {"durum": "hata", "neden": f"{type(e).__name__}: {e}"}
        with self._kilit:
            if s.get("durum") != "hata" or self._son is None or self._son.get("durum") == "hata":
                self._son = s
            self._son_zaman = self._saat()
            return dict(self._son)

    def yoklamayi_baslat(self) -> None:
        """Arka plan iş parçacığı: açılışta bir, sonra her YOKLAMA_ARALIGI'nda bir yoklama. İkinci çağrı etkisizdir."""
        with self._kilit:
            if self._is and self._is.is_alive():
                return
            self._durdur.clear()
            self._is = threading.Thread(target=self._dongu, name="orkestra-guncelleme-yoklama", daemon=True)
            self._is.start()

    def yoklamayi_durdur(self) -> None:
        self._durdur.set()

    def _dongu(self) -> None:
        while not self._durdur.is_set():
            self.yokla(getir=True)
            if self._durdur.wait(YOKLAMA_ARALIGI):
                return

    # ---- erteleme ------------------------------------------------------------------------------------------
    def _erteleme_yolu(self) -> str:
        return os.path.join(self._dizin, ERTELEME_DOSYASI)

    def _ertelenen_sha(self) -> str | None:
        try:
            with open(self._erteleme_yolu(), encoding="utf-8") as f:
                return (json.load(f) or {}).get("sha") or None
        except (OSError, ValueError, AttributeError):
            return None

    def ertele(self) -> dict:
        """Şu anki yeni SHA için kartı gizler; daha yeni bir SHA gelince kart döner. Yeni sürüm yoksa tamam=False."""
        with self._kilit:
            son = self._son
        if not son or son.get("durum") != "yeni" or not son.get("yeni"):
            return {"tamam": False, "hata": "Ertelenecek yeni sürüm yok."}
        os.makedirs(self._dizin, exist_ok=True)
        L.atomik_yaz(self._erteleme_yolu(), json.dumps({"sha": son["yeni"], "zaman": L.simdi()}))
        return {"tamam": True, "sha": son["yeni"]}

    # ---- güncelleme koşusu ---------------------------------------------------------------------------------
    def guncelle(self) -> dict:
        """Koşuyu başlatır. Zaten çalışıyorsa tamam=False (ikinci koşu açılmaz)."""
        with self._kilit:
            self._kosu_sonrasi_yenilendi = False
        if not self.kosu.baslat():
            return {"tamam": False, "hata": "Güncelleme zaten çalışıyor."}
        return {"tamam": True}

    # ---- durum ---------------------------------------------------------------------------------------------
    def durum(self) -> dict:
        """Panelin tek okuma ucu. durum: yok | yeni | calisiyor | bitti | hata."""
        k = self.kosu.anlik()
        if k["durum"] in ("bitti", "hata"):
            with self._kilit:
                yenile = not self._kosu_sonrasi_yenilendi
                self._kosu_sonrasi_yenilendi = True
            if yenile:
                self.yokla(getir=False)   # yerel: ağa çıkmadan klonun yeni halini yansıt
        with self._kilit:
            son = dict(self._son) if self._son else None
            zaman = self._son_zaman
        durum = "yok"
        if k["durum"] == "calisiyor":
            durum = "calisiyor"
        elif k["durum"] == "hata":
            durum = "hata"
        elif k["durum"] == "bitti" and k["bitis"] is not None and self._saat() - k["bitis"] <= BITTI_GOSTER:
            durum = "bitti"
        elif son and son.get("durum") == "yeni" and (son.get("yenilik_say") or 0) > 0:
            durum = "yeni"   # yeni özellik (Yenilik: commit'i) yoksa kart hiç çıkmaz
        ertelendi = bool(durum == "yeni" and son and self._ertelenen_sha() == son.get("yeni"))
        kontrol = None
        if son:
            kontrol = {a: son.get(a) for a in ("kurulu", "yeni", "fark", "yenilik_say", "degisiklikler", "klon_kirli", "neden")}
            kontrol["zaman"] = zaman
        return {"durum": durum, "ertelendi": ertelendi, "kontrol": kontrol,
                "kosu": k if k["durum"] != "bosta" else None}
