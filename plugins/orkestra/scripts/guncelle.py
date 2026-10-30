"""orkestra update / guncelle: yayın klonunu GitHub origin'den ilerletir, kurulu plugin'leri kendi kapsamıyla günceller.

LLM çağırmaz; CLI (`orkestra update`) ve slash komutu (`/orkestra:update`) aynı kodu çalıştırır.
Adımlar: araçları bul → yayın klonunu (kirliyse reddet) fetch + merge --ff-only → `claude plugin marketplace update`
→ installed_plugins.json'daki her kurulu plugin için `claude plugin update <ad> --scope <kapsam>` → sonuç.
Testte `kos` (subprocess), `ev` (home dizini) ve `ortam` değiştirilir.
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import threading
import time
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cfg  # noqa: E402

PAZAR = "claude-orchestration"


class GuncelleHata(Exception):
    """Kullanıcıya 'HATA: neden' olarak yazılan, sıfır olmayan çıkış kodlu durum."""


def kos(argv: list[str], cwd: str | None = None) -> tuple[int, str]:
    """Komutu çalıştırır; (çıkış kodu, stdout+stderr) döner. Program yoksa 127."""
    try:
        r = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", **cfg.PENCERESIZ)
    except OSError as e:
        return 127, str(e)
    return r.returncode, (r.stdout + r.stderr).strip()


def _surum_anahtari(yol: str) -> tuple:
    """claude.exe yolundan sürüm: .../claude-code/<sürüm>/<platform>/claude.exe."""
    s = os.path.basename(os.path.dirname(os.path.dirname(yol)))
    return tuple(int(x) for x in re.findall(r"\d+", s)) or (0,)


def claude_bul(ortam: dict | None = None, which=shutil.which) -> str | None:
    """claude.exe: CLAUDE_CODE_EXECPATH > %APPDATA% ve MSIX paketi (Packages\\Claude_*) altındaki en yeni sürüm > PATH.

    Claude masaüstü MSIX paketli olduğu için %APPDATA% tek başına yetmez: gerçek konum
    %LOCALAPPDATA%\\Packages\\Claude_*\\LocalCache\\Roaming\\Claude\\claude-code altındadır.
    """
    ortam = os.environ if ortam is None else ortam
    yol = ortam.get("CLAUDE_CODE_EXECPATH")
    if yol and os.path.isfile(yol):
        return yol
    kokler = []
    if ortam.get("APPDATA"):
        kokler.append(os.path.join(ortam["APPDATA"], "Claude", "claude-code"))
    if ortam.get("LOCALAPPDATA"):
        kokler += glob.glob(os.path.join(ortam["LOCALAPPDATA"], "Packages", "Claude_*", "LocalCache", "Roaming", "Claude", "claude-code"))
        kokler += glob.glob(os.path.join(ortam["LOCALAPPDATA"], "Claude-Data", "claude_*", "claude-code"))
    adaylar = []
    for k in kokler:
        adaylar += glob.glob(os.path.join(k, "*", "*", "claude.exe"))
    adaylar = [a for a in adaylar if os.path.isfile(a)]
    if adaylar:
        return max(adaylar, key=_surum_anahtari)
    return which("claude")


def kurulu_pluginler(ev: str | None = None, pazar: str = PAZAR) -> list[dict]:
    """installed_plugins.json'daki pazar plugin'leri: [{ad, kapsam, surum, proje}] (her kapsam ayrı satır)."""
    ev = ev or os.path.expanduser("~")
    try:
        with open(os.path.join(ev, ".claude", "plugins", "installed_plugins.json"), encoding="utf-8") as f:
            veri = json.load(f).get("plugins") or {}
    except (OSError, ValueError):
        return []
    liste = []
    for anahtar, girdiler in veri.items():
        if anahtar.partition("@")[2] != pazar:
            continue
        for g in girdiler or []:
            liste.append({"ad": anahtar, "kapsam": g.get("scope") or "user",
                          "surum": g.get("version") or "-", "proje": g.get("projectPath")})
    return liste


def pazar_klonu(ev: str | None = None, pazar: str = PAZAR) -> str | None:
    """known_marketplaces.json'daki yayın klonu (installLocation); yoksa None."""
    ev = ev or os.path.expanduser("~")
    try:
        with open(os.path.join(ev, ".claude", "plugins", "known_marketplaces.json"), encoding="utf-8") as f:
            yol = (json.load(f).get(pazar) or {}).get("installLocation")
    except (OSError, ValueError):
        return None
    return yol if yol and os.path.isdir(yol) else None


def _git_cikti(klon: str, *a: str) -> str:
    kod, cikti = kos(["git", "-C", klon, *a])
    if kod != 0:
        raise GuncelleHata(f"git {' '.join(a)} başarısız (çıkış {kod}): {cikti}")
    return cikti


def klon_ilerlet(klon: str, kuru: bool, yaz) -> tuple[str, str]:
    """Yayın klonunu origin'den hızlı ileri sarar (kirliyse reddeder); (eski, yeni) kısa SHA döner."""
    if not os.path.isdir(os.path.join(klon, ".git")):
        raise GuncelleHata(f"yayın klonu git deposu değil: {klon}")
    eski = _git_cikti(klon, "rev-parse", "--short", "HEAD")
    kirli = _git_cikti(klon, "status", "--porcelain")
    if kirli:
        raise GuncelleHata(f"yayın klonunda commitlenmemiş değişiklik var; güncelleme reddedildi ({klon}):\n{kirli}\n"
                           f"Klona hiçbir şey yazılmaz ve klon elle düzenlenmez: değişiklikleri geri al (git -C <klon> restore .) ya da klonu silip `python araclar/yayin_kur.py` ile GitHub'dan yeniden kur. Düzeltme Desktop deposunda yapılır, push edilir, sonra `orkestra guncelle`.")
    for a in (("fetch", "-q", "origin"), ("merge", "--ff-only", "-q", "@{u}")):
        yaz(f"> git -C {klon} {' '.join(a)}")
        if kuru:
            continue
        kod, cikti = kos(["git", "-C", klon, *a])
        if kod != 0:
            if a[0] == "fetch":
                raise GuncelleHata(f"GitHub'dan çekilemedi (ağ ya da yetki?): {cikti}")
            raise GuncelleHata(f"yayın klonu ileri sarılamadı (yerel commit ya da ayrışmış dal): {cikti}")
    yeni = eski if kuru else _git_cikti(klon, "rev-parse", "--short", "HEAD")
    return eski, yeni


UZAK_DAL = "origin/main"
DEGISIKLIK_SINIRI = 20
YENILIK_ONEKI = "Yenilik:"   # yalnız bu önekli commit yeni özellik sayılır; güncelleme kartı yalnız onlar için çıkar
FETCH_ZAMAN_ASIMI = 20


def _kisa(sha: str) -> str:
    return (sha or "")[:7]


def kontrol(ev: str | None = None, getir: bool = True) -> dict:
    """Yeni sürüm var mı? Kurulu plugin SHA'sını GitHub `origin/main` ile karşılaştırır; asla fırlatmaz.

    Sürüm commit SHA'sıdır (GELISTIRME.md). Yayın klonu geride kalsa bile `origin/main` ilerlediyse "yeni" döner.
    `getir=False` ağa çıkmaz, klonda zaten bilinen `origin/main`'e bakar.
    Dönüş: {durum: guncel|yeni|hata, kurulu, yeni, fark, yenilik_say, degisiklikler:[{sha, konu}], klon_kirli, klon, neden}.
    `degisiklikler` yalnız konusu `YENILIK_ONEKI` ile başlayan commit'leri taşır; `yenilik_say` onların toplamıdır.
    """
    sonuc = {"durum": "hata", "kurulu": None, "yeni": None, "fark": None, "yenilik_say": 0, "degisiklikler": [],
             "klon_kirli": False, "klon": None, "neden": None}
    try:
        if not shutil.which("git"):
            raise GuncelleHata("git bulunamadı (PATH'te yok).")
        klon = pazar_klonu(ev)
        if not klon:
            raise GuncelleHata(f"{PAZAR} yayın klonu bulunamadı (known_marketplaces.json).")
        sonuc["klon"] = klon
        if not os.path.isdir(os.path.join(klon, ".git")):
            raise GuncelleHata(f"yayın klonu git deposu değil: {klon}")
        kurulu = kurulu_pluginler(ev)
        if not kurulu:
            raise GuncelleHata(f"kurulu {PAZAR} plugin'i bulunamadı (installed_plugins.json).")
        if getir:
            # lowSpeedTime: 20 sn boyunca (neredeyse) veri gelmezse fetch kendiliğinden düşer; panel iş parçacığı asılmaz.
            kod, cikti = kos(["git", "-C", klon, "-c", "http.lowSpeedLimit=1000", "-c", f"http.lowSpeedTime={FETCH_ZAMAN_ASIMI}",
                              "fetch", "-q", "origin"])
            if kod != 0:
                raise GuncelleHata(f"GitHub'a ulaşılamadı (ağ ya da yetki?): {cikti}")
        uzak = _git_cikti(klon, "rev-parse", UZAK_DAL)
        sonuc["yeni"] = _kisa(uzak)
        ana = next((p for p in kurulu if p["ad"].startswith("orkestra@")), kurulu[0])
        sonuc["kurulu"] = ana["surum"]
        surumler = {p["surum"] for p in kurulu}
        sonuc["klon_kirli"] = bool(_git_cikti(klon, "status", "--porcelain"))
        if all(uzak.startswith(s) for s in surumler if s != "-") and "-" not in surumler:
            sonuc["durum"] = "guncel"
            sonuc["fark"] = 0
            return sonuc
        sonuc["durum"] = "yeni"
        # Kurulu SHA klonda bilinmiyorsa (kod != 0) fark sayılamaz: sayı None, son commitler listelenir.
        taban = ana["surum"] if ana["surum"] != "-" else None
        aralik = f"{taban}..{UZAK_DAL}" if taban and kos(["git", "-C", klon, "cat-file", "-e", f"{taban}^{{commit}}"])[0] == 0 else None
        if aralik:
            sonuc["fark"] = int(_git_cikti(klon, "rev-list", "--count", aralik))
        if aralik:
            log = _git_cikti(klon, "log", f"--grep=^{YENILIK_ONEKI}", "--format=%h%x09%s", aralik)
        else:
            log = _git_cikti(klon, "log", f"-n{DEGISIKLIK_SINIRI}", "--format=%h%x09%s", UZAK_DAL)
        yenilikler = []
        for satir in log.splitlines():
            sha, _, konu = satir.partition("\t")
            if konu.startswith(YENILIK_ONEKI):
                yenilikler.append({"sha": sha, "konu": konu[len(YENILIK_ONEKI):].strip()})
        sonuc["yenilik_say"] = len(yenilikler)
        sonuc["degisiklikler"] = yenilikler[:DEGISIKLIK_SINIRI]
        return sonuc
    except GuncelleHata as e:
        sonuc["durum"] = "hata"
        sonuc["neden"] = str(e)
        return sonuc


def calistir(kuru: bool = False, yaz=print, ev: str | None = None, ortam: dict | None = None) -> int:
    """Güncellemeyi yürütür, Türkçe sonucu `yaz` ile verir; çıkış kodunu döner (0 başarı, 1 hata)."""
    try:
        return _calistir(kuru, yaz, ev, ortam)
    except GuncelleHata as e:
        yaz("")
        yaz(f"HATA: {e}")
        return 1


class Kosu:
    """Güncellemeyi arka plan iş parçacığında çalıştıran, aynı anda tek koşuya izin veren sarmalayıcı (panel kullanır).

    `calistir`'ın çıktı satırlarını toplar; durum: bosta | calisiyor | bitti | hata. LLM ya da ikinci güncelleyici yoktur.
    """
    SATIR_SINIRI = 500

    def __init__(self, ev: str | None = None, ortam: dict | None = None, calistir=None, saat=time.time):
        self._ev, self._ortam, self._calistir, self._saat = ev, ortam, calistir, saat
        self._kilit = threading.Lock()
        self._is: threading.Thread | None = None
        self._durum = "bosta"
        self._satirlar: list[str] = []
        self._neden: str | None = None
        self._bas = self._bit = None

    def baslat(self) -> bool:
        """Koşu başlatır; zaten çalışıyorsa False (ikinci koşu açılmaz)."""
        with self._kilit:
            if self._durum == "calisiyor":
                return False
            self._durum, self._satirlar, self._neden = "calisiyor", [], None
            self._bas, self._bit = self._saat(), None
            self._is = threading.Thread(target=self._yurut, name="orkestra-guncelle", daemon=True)
            self._is.start()
            return True

    def _yaz(self, satir: str) -> None:
        with self._kilit:
            if len(self._satirlar) < self.SATIR_SINIRI:
                self._satirlar.append(str(satir))

    def _yurut(self) -> None:
        kos_fn = self._calistir or calistir
        try:
            kod = kos_fn(kuru=False, yaz=self._yaz, ev=self._ev, ortam=self._ortam)
            beklenmedik = None
        except Exception as e:  # noqa: BLE001: iş parçacığı sessizce ölmemeli, durum 'hata' olmalı
            kod, beklenmedik = 1, f"{type(e).__name__}: {e}"
        with self._kilit:
            if kod != 0:
                hatalar = [s[len("HATA: "):] for s in self._satirlar if s.startswith("HATA: ")]
                self._neden = beklenmedik or (hatalar[-1] if hatalar else f"güncelleme başarısız (çıkış {kod})")
            self._durum = "bitti" if kod == 0 else "hata"
            self._bit = self._saat()

    def bekle(self, zaman_asimi: float | None = None) -> None:
        t = self._is
        if t:
            t.join(zaman_asimi)

    def anlik(self) -> dict:
        with self._kilit:
            bit = self._bit if self._bit is not None else self._saat()
            return {"durum": self._durum, "satirlar": list(self._satirlar), "neden": self._neden,
                    "sure": round(bit - self._bas, 1) if self._bas is not None else None, "bitis": self._bit}


_EKLENTI_KOKU = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUDA_AYAR = os.path.join(_EKLENTI_KOKU, "ayarlar", "onbellek_buda.json")
BUDA_VARSAYILAN = 3
BUDA_MANIFEST = "onbellek_buda.jsonl"


def buda_esigi(yol: str = BUDA_AYAR) -> int:
    """ayarlar/onbellek_buda.json `tutulacak_son_surum` (etkin sürüm hariç tutulacak en yeni sürüm sayısı); okunamazsa 3."""
    try:
        with open(yol, encoding="utf-8") as f:
            n = int(json.load(f).get("tutulacak_son_surum", BUDA_VARSAYILAN))
    except (OSError, ValueError, TypeError, AttributeError):
        return BUDA_VARSAYILAN
    return max(n, 0)


def _gercek(yol: str) -> str:
    return os.path.normcase(os.path.realpath(yol))


def onbellek_koku(ev: str | None = None, pazar: str = PAZAR) -> str:
    ev = ev or os.path.expanduser("~")
    return os.path.join(ev, ".claude", "plugins", "cache", pazar)


def onbellek_klasoru_sil(kok: str, yol: str) -> None:
    """Yalnız önbellek kökünün (`kok`) altındaki sürüm klasörünü siler; kök dışı, kökün kendisi, bağlantı (symlink/junction)
    ya da klasör olmayan yol ValueError ile reddedilir (budama kök dışına çıkamaz)."""
    k, y = _gercek(kok), _gercek(yol)
    if y == k or os.path.commonpath([k, y]) != k:
        raise ValueError(f"önbellek kökü dışında yol reddedildi: {yol}")
    if os.path.islink(yol) or not os.path.isdir(yol) or _gercek(os.path.dirname(os.path.dirname(y))) != k:
        raise ValueError(f"önbellek sürüm klasörü değil: {yol}")
    shutil.rmtree(yol)


def korunan_surumler(ev: str | None = None, ortam: dict | None = None, pazar: str = PAZAR) -> set[str]:
    """Silinmeyecek sürüm klasörleri (gerçek yol): installed_plugins.json'daki pazar plugin'lerinin installPath'i (etkin sürüm),
    çalışan oturumların kopyası (CLAUDE_PLUGIN_ROOT ve bu betiğin eklenti kökü). `.in_use` işaretli klasörler ayrıca budamada korunur."""
    ev = ev or os.path.expanduser("~")
    ortam = os.environ if ortam is None else ortam
    korunan = set()
    try:
        with open(os.path.join(ev, ".claude", "plugins", "installed_plugins.json"), encoding="utf-8") as f:
            veri = json.load(f).get("plugins") or {}
    except (OSError, ValueError, AttributeError):
        veri = {}
    for anahtar, girdiler in veri.items():
        if anahtar.partition("@")[2] != pazar:
            continue
        for g in girdiler or []:
            if isinstance(g, dict) and g.get("installPath"):
                korunan.add(_gercek(g["installPath"]))
    for yol in (ortam.get("CLAUDE_PLUGIN_ROOT"), _EKLENTI_KOKU):
        if yol:
            korunan.add(_gercek(yol))
    return korunan


def _kullanimda(surum_yolu: str) -> bool:
    """Claude Code çalışan oturumu `.in_use` (dosya ya da pid dosyalı klasör) ile işaretler."""
    iu = os.path.join(surum_yolu, ".in_use")
    if os.path.isfile(iu):
        return True
    try:
        return bool(os.listdir(iu))
    except OSError:
        return False


def _boyut(yol: str) -> int:
    toplam = 0
    for r, _, dosyalar in os.walk(yol):
        for d in dosyalar:
            try:
                toplam += os.path.getsize(os.path.join(r, d))
            except OSError:
                pass
    return toplam


def onbellek_buda(ev: str | None = None, ortam: dict | None = None, tut: int | None = None, kuru: bool = False,
                  yaz=print, manifest_dizini: str | None = None, pazar: str = PAZAR) -> dict:
    """Her eklenti için etkin/kullanımdaki sürümler + bunlar dışındaki en yeni `tut` sürüm (mtime) kalır, kalanlar silinir.
    Silmeden önce manifest (ad, boyut, tarih) `<ev>/.claude/orkestra-makine/onbellek_buda.jsonl`e eklenir.
    Dönüş: {silinen: [kayıt], hata: [metin], manifest: yol|None}. Geri alma: eklentiyi yeniden indirmek."""
    tut = buda_esigi() if tut is None else max(int(tut), 0)
    kok = onbellek_koku(ev, pazar)
    sonuc = {"aday": [], "silinen": [], "hata": [], "manifest": None}
    if not os.path.isdir(kok):
        return sonuc
    korunan = korunan_surumler(ev, ortam, pazar)
    adaylar = []
    for eklenti in sorted(os.listdir(kok)):
        d = os.path.join(kok, eklenti)
        if os.path.islink(d) or not os.path.isdir(d):
            continue
        surumler = []
        for s in os.listdir(d):
            y = os.path.join(d, s)
            if os.path.isdir(y) and not os.path.islink(y):
                surumler.append((os.path.getmtime(y), s, y))
        surumler.sort(reverse=True)
        serbest = [x for x in surumler if _gercek(x[2]) not in korunan and not _kullanimda(x[2])]
        for mt, s, y in serbest[tut:]:
            adaylar.append({"eklenti": eklenti, "ad": s, "yol": y, "boyut": _boyut(y),
                            "tarih": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(mt))})
    if not adaylar:
        return sonuc
    toplam = sum(a["boyut"] for a in adaylar)
    yaz(f"Önbellek budama: {len(adaylar)} eski sürüm, {toplam / 1e6:.1f} MB" + (" (kuru koşu, silinmedi)" if kuru else ""))
    sonuc["aday"] = adaylar
    if kuru:
        return sonuc
    if manifest_dizini is None:
        manifest_dizini = os.path.join(ev, ".claude", "orkestra-makine") if ev else cfg.ev_dizini()
    os.makedirs(manifest_dizini, exist_ok=True)
    mf = os.path.join(manifest_dizini, BUDA_MANIFEST)
    kayit = {"zaman": time.strftime("%Y-%m-%dT%H:%M:%S"), "onbellek": kok, "tutulan_son": tut,
             "geri_alma": "eklentiyi yeniden indir: orkestra guncelle / claude plugin install",
             "klasorler": [{k: a[k] for k in ("eklenti", "ad", "boyut", "tarih")} for a in adaylar]}
    with open(mf, "a", encoding="utf-8") as f:  # manifest silmeden ÖNCE yazılır; yazılamazsa hiçbir şey silinmez
        f.write(json.dumps(kayit, ensure_ascii=False) + "\n")
    sonuc["manifest"] = mf
    for a in adaylar:
        try:
            onbellek_klasoru_sil(kok, a["yol"])
            sonuc["silinen"].append(a)
        except (OSError, ValueError) as e:
            sonuc["hata"].append(f"{a['eklenti']}/{a['ad']}: {e}")
    yaz(f"  silinen {len(sonuc['silinen'])}; manifest {mf}" + (f"; silinemeyen {len(sonuc['hata'])}" if sonuc["hata"] else ""))
    return sonuc


def _calistir(kuru, yaz, ev, ortam) -> int:
    if not shutil.which("git"):
        raise GuncelleHata("git bulunamadı (PATH'te yok).")
    claude = claude_bul(ortam)
    if not claude:
        raise GuncelleHata("claude.exe bulunamadı (CLAUDE_CODE_EXECPATH, %APPDATA%\\Claude\\claude-code, "
                           "%LOCALAPPDATA%\\Packages\\Claude_*\\LocalCache\\Roaming\\Claude\\claude-code ve PATH'te claude yok).")
    klon = pazar_klonu(ev)
    if not klon:
        raise GuncelleHata(f"{PAZAR} yayın klonu bulunamadı (known_marketplaces.json).")
    once = kurulu_pluginler(ev)
    if not once:
        raise GuncelleHata(f"kurulu {PAZAR} plugin'i bulunamadı (installed_plugins.json).")

    yaz("ORKESTRA GÜNCELLE")
    yaz(f"Yayın klonu : {klon}")
    yaz(f"claude      : {claude}")
    yaz("")
    eski, yeni = klon_ilerlet(klon, kuru, yaz)

    komutlar = [([claude, "plugin", "marketplace", "update", PAZAR], None)]
    for p in once:
        cwd = p["proje"] if p["kapsam"] == "project" and p["proje"] and os.path.isdir(p["proje"]) else None
        komutlar.append(([claude, "plugin", "update", p["ad"], "--scope", p["kapsam"]], cwd))
    basarisiz = []
    for i, (argv, cwd) in enumerate(komutlar):
        yaz("> claude " + " ".join(argv[1:]))
        if kuru:
            continue
        kod, cikti = kos(argv, cwd)
        for satir in cikti.splitlines():
            yaz("  " + satir)
        if kod != 0:
            if i == 0:
                raise GuncelleHata(f"pazar yeri güncellenemedi (çıkış {kod}).")
            basarisiz.append(f"{argv[3]} --scope {argv[5]} (çıkış {kod})")
    if basarisiz:
        raise GuncelleHata("plugin güncellenemedi: " + "; ".join(basarisiz))
    if kuru:
        yaz("")
        yaz("Kuru koşu: komutlar çalıştırılmadı.")
        return 0

    sonra = kurulu_pluginler(ev)
    degisen = []
    for s in sonra:
        o = next((x for x in once if x["ad"] == s["ad"] and x["kapsam"] == s["kapsam"]), None)
        if not o or o["surum"] != s["surum"]:
            degisen.append(f"{s['ad']} ({s['kapsam']}): {o['surum'] if o else '-'} → {s['surum']}")
    yaz("")
    if eski == yeni and not degisen:
        yaz(f"ZATEN GÜNCEL (klon {yeni}; kurulu plugin: {', '.join(sorted({s['surum'] for s in sonra}))})")
        return 0
    yaz(f"GÜNCELLENDİ (klon {eski} → {yeni})")
    for d in degisen:
        yaz(f"  plugin {d}")
    if eski != yeni:
        kod, log = kos(["git", "-C", klon, "log", "--oneline", f"{eski}..{yeni}"])
        for satir in (log.splitlines() if kod == 0 else []):
            yaz(f"  {satir}")
    yaz("Değişiklik yeni oturumda yüklenir: yeni oturum aç ya da /reload-plugins.")
    return 0
