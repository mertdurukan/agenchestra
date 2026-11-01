"""Entegrasyon şeridi (I-323 P3; sözleşme S2, S3, S6, S8): kuyruktaki teslimleri tek tam koşuyla sınar.

Akış (`entegre_et`):
  1. Tek-koşucu kilidini alır (kuyruk.kosucu_al); canlı başka koşucu varsa hiçbir şey yapmaz ("mesgul").
     Önceki ölü koşucunun bıraktığı `kosuyor` teslimleri `bekliyor`a döndürür (kuyruk.kurtar).
  2. `bekliyor` teslimleri sıra numarasıyla alır, `kosuyor` yapar; geçici bir git worktree'de hedef dalın (main) ucuna
     sırayla birleştirir. Birleşmeyen (çakışan ya da bulunmayan dal) teslim doğrudan karantinaya gider.
  3. Tam paketi BİR KEZ koşar. Yeşilse `git update-ref refs/heads/<hedef> NEW OLD` ile yalnız ileri alır (eski değer
     kilidi: arada main ilerlediyse yazım reddedilir). Reddedilirse yeni uca yeniden temellendirir ve yeniden koşar
     (en çok FF_DENEME tur).
  4. Kırmızıysa bir kez yeniden koşar (flaky ayrımı). Yine kırmızıysa önek ikiye bölmesiyle ilk kırmızı öneki bulur:
     suçlu, kendinden öncekilerle yeşil olup kendisi eklenince kırmızılaşan teslimdir. Bu, etkileşim hatasında
     (ayrı yeşil, birlikte kırmızı) son ekleneni sorumlu atar. Suçlu karantinaya alınır, kalanlar yeniden koşulur;
     bilinen yeşil önek korunur, ikinci suçlu aynı yolla bulunur.
  5. Her suçlu için `kanca(bilgi)` çağrılır (bilgi: teslim, oturum, dal, neden, gunluk). Bildirim (P4) buraya bağlanır;
     bu modül not göndermez.

Ortak git indeksi: birleştirmeler geçici worktree'nin kendi indeksinde yapılır, ana çalışma ağacının indeksine
dokunulmaz; hedef dal bir çalışma ağacında çıkılıysa (checkout) ilerletilmez ("hedef_cikili"), çünkü update-ref o
ağacın dosyalarını eski bırakır. Model çağırmaz.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from typing import Callable

import kuyruk as K

VARSAYILAN_TEST = "plugins/orkestra/scripts/test_paralel.py"  # depo köküne göre; orkestra eklenti deposu düzeni
FF_DENEME = 3
TAZELE_S = 10.0  # kilit nabzı; K.BAYAT_S (30 sn) altında kalmalı, tam paket 30 sn'den uzun sürer
GUNLUK_SINIR = 4000
_GIT_KIMLIK = ["-c", "user.name=orkestra-entegrasyon", "-c", "user.email=entegrasyon@orkestra.invalid"]
_GIT_SIZINTI = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY")


class EntegrasyonHatasi(RuntimeError):
    """Git ya da ortam hatası; mesaj kullanıcıya gösterilir."""


def _git(cwd: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in _GIT_SIZINTI}
    r = subprocess.run(["git", "-c", "safe.directory=*", *_GIT_KIMLIK, *args], cwd=cwd, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", env=env)
    if check and r.returncode:
        raise EntegrasyonHatasi(f"git {' '.join(args)}: {(r.stderr or r.stdout).strip()[:500]}")
    return r


def _sha(cwd: str, ref: str) -> str | None:
    r = _git(cwd, "rev-parse", "-q", "--verify", f"{ref}^{{commit}}", check=False)
    return r.stdout.strip() if r.returncode == 0 else None


def _cikili_mi(depo: str, hedef: str) -> bool:
    satirlar = _git(depo, "worktree", "list", "--porcelain").stdout.splitlines()
    return f"branch refs/heads/{hedef}" in (s.strip() for s in satirlar)


TestSonucu = "bool | tuple[bool, str]"


def _test_fn(test_komutu) -> Callable[[str], tuple[bool, str]]:
    """test_komutu: None (varsayılan tam paket), komut listesi ya da callable(agac_yolu) -> bool | (bool, gunluk)."""
    if callable(test_komutu):
        def cagir(agac: str) -> tuple[bool, str]:
            r = test_komutu(agac)
            return (bool(r[0]), str(r[1] or "")) if isinstance(r, tuple) else (bool(r), "")
        return cagir
    komut = list(test_komutu) if test_komutu else [sys.executable, VARSAYILAN_TEST]

    def kos(agac: str) -> tuple[bool, str]:
        env = {k: v for k, v in os.environ.items() if k not in _GIT_SIZINTI}
        env["PYTHONUTF8"] = "1"
        r = subprocess.run(komut, cwd=agac, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=env)
        return r.returncode == 0, ((r.stdout or "") + (r.stderr or ""))[-GUNLUK_SINIR:]
    return kos


class _Agac:
    """Geçici worktree (ayrık HEAD). Kendi indeksini kullanır; çıkışta kaldırılır."""

    def __init__(self, depo: str, uc: str):
        self.depo = depo
        self.yol = tempfile.mkdtemp(prefix="ork-entegrasyon-")
        _git(depo, "worktree", "add", "-q", "--detach", self.yol, uc)

    def kur(self, taban: str, dallar: list[str]) -> tuple[str, list[int]]:
        """Tabana dalları sırayla birleştirir; dönen (HEAD, birleşmeyen indisler). Birleşmeyen atlanır."""
        _git(self.yol, "checkout", "-q", "-f", "--detach", taban)
        _git(self.yol, "reset", "-q", "--hard", taban)
        _git(self.yol, "clean", "-q", "-fdx")
        olmayan = []
        for i, dal in enumerate(dallar):
            if not _sha(self.depo, dal) or _git(self.yol, "merge", "-q", "--no-edit", dal, check=False).returncode:
                _git(self.yol, "merge", "--abort", check=False)
                _git(self.yol, "reset", "-q", "--hard", "HEAD")
                olmayan.append(i)
        return _sha(self.yol, "HEAD") or taban, olmayan

    def kapat(self) -> None:
        if _git(self.depo, "worktree", "remove", "--force", self.yol, check=False).returncode:
            shutil.rmtree(self.yol, ignore_errors=True)
            _git(self.depo, "worktree", "prune", check=False)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.kapat()


class _Nabiz(threading.Thread):
    """Koşu sürerken tek-koşucu kilidini tazeler; kilit kaybedilirse `kayip` olur ve main ilerletilmez."""

    def __init__(self, sd: str, sahip: str):
        super().__init__(daemon=True)
        self.sd, self.sahip, self.dur, self.kayip = sd, sahip, threading.Event(), False

    def run(self):
        while not self.dur.wait(TAZELE_S):
            if not K.kosucu_tazele(self.sd, self.sahip):
                self.kayip = True
                return


class _Kosu:
    def __init__(self, agac: _Agac, test: Callable[[str], tuple[bool, str]]):
        self.agac, self.test = agac, test
        self.sayi = self.bisect = 0
        self.flaky = False

    def _kos(self, bisect: bool = False) -> tuple[bool, str]:
        self.sayi += 1
        self.bisect += int(bisect)
        return self.test(self.agac.yol)

    def tur(self, taban: str, adaylar: list[dict]):
        """Dönen (yeşil HEAD | None, yeşil teslimler, suçlular[(teslim, neden, gunluk)])."""
        kalan, suclular, yesil_onek = list(adaylar), [], 0
        while kalan:
            sha, olmayan = self.agac.kur(taban, [t["dal"] for t in kalan])
            for i in reversed(olmayan):
                suclular.append((kalan.pop(i), "birleştirme çakışması ya da dal bulunamadı", ""))
                yesil_onek -= int(i < yesil_onek)
            if not kalan:
                break
            ok, gunluk = self._kos()
            if not ok:
                ok, gunluk2 = self._kos()  # kırmızı bir kez yeniden koşulur
                self.flaky = self.flaky or ok
                gunluk = gunluk2 or gunluk
            if ok:
                return sha, kalan, suclular
            alt, ust = yesil_onek, len(kalan)  # kalan[:alt] yeşil, kalan[:ust] kırmızı
            while ust - alt > 1:
                orta = (alt + ust) // 2
                self.agac.kur(taban, [t["dal"] for t in kalan[:orta]])
                ok_o, gunluk_o = self._kos(bisect=True)
                if ok_o:
                    alt = orta
                else:
                    ust, gunluk = orta, gunluk_o
            neden = ("ilk kırmızı önek: öncekilerle yeşil, kendisi eklenince kırmızı"
                     + (" (etkileşimde son eklenen sorumlu)" if ust > 1 else ""))
            suclular.append((kalan.pop(ust - 1), neden, gunluk))
            yesil_onek = ust - 1
        return None, [], suclular


def _karantina(sd: str, t: dict, neden: str, gunluk: str, kanca, sonuc: dict) -> None:
    K.gecis(sd, t["teslim"], "karantina", neden=neden)
    bilgi = {"teslim": t["teslim"], "oturum": t.get("oturum"), "dal": t.get("dal"), "neden": neden, "gunluk": gunluk}
    sonuc["karantina"].append({a: bilgi[a] for a in ("teslim", "oturum", "neden")})
    if kanca:
        try:
            kanca(bilgi)
        except Exception as e:  # bildirim hatası entegrasyonu durdurmaz
            sonuc.setdefault("kanca_hata", []).append(f"{t['teslim']}: {e}")


def entegre_et(sd: str, depo: str, test_komutu=None, sahip: str | None = None, hedef: str = "main",
               kanca: Callable[[dict], None] | None = None, ff_deneme: int = FF_DENEME) -> dict:
    """Kuyruğu bir tur işler. Dönen: durum (birlesti|karantina|bos|mesgul|hedef_cikili|ff_basarisiz|kilit_kayip),
    birlesen, karantina [{teslim, oturum, neden}], kosu (tam paket koşu sayısı), bisect_kosu, flaky, yeniden_temel,
    hedef_sha, geri_donen (bitmeden bekliyor'a dönenler)."""
    sahip = sahip or f"entegrasyon-{os.getpid()}-{uuid.uuid4().hex[:6]}"
    sonuc: dict = {"durum": "bos", "birlesen": [], "karantina": [], "kosu": 0, "bisect_kosu": 0, "flaky": False,
                   "yeniden_temel": 0, "hedef_sha": None, "geri_donen": []}
    if not K.kosucu_al(sd, sahip):
        return {**sonuc, "durum": "mesgul", "kosucu": K.kosucu(sd)}
    nabiz = _Nabiz(sd, sahip)
    nabiz.start()
    try:
        sonuc["kurtarilan"] = K.kurtar(sd, sahip=sahip)
        if _cikili_mi(depo, hedef):
            return {**sonuc, "durum": "hedef_cikili"}
        uc = _sha(depo, f"refs/heads/{hedef}")
        if not uc:
            raise EntegrasyonHatasi(f"hedef dal yok: {hedef}")
        adaylar = K.liste(sd, "bekliyor")
        if not adaylar:
            return sonuc
        for t in adaylar:
            K.gecis(sd, t["teslim"], "kosuyor")
        test = _test_fn(test_komutu)
        with _Agac(depo, uc) as agac:
            kosu = _Kosu(agac, test)
            try:
                sonuc["durum"] = "ff_basarisiz"
                for _ in range(max(1, ff_deneme)):
                    eski = _sha(depo, f"refs/heads/{hedef}")
                    sha, adaylar, suclular = kosu.tur(eski, adaylar)
                    for t, neden, gunluk in suclular:
                        _karantina(sd, t, neden, gunluk, kanca, sonuc)
                    if not adaylar:
                        sonuc["durum"] = "karantina"
                        break
                    if nabiz.kayip:
                        sonuc["durum"] = "kilit_kayip"
                        break
                    if _git(depo, "update-ref", f"refs/heads/{hedef}", sha, eski, check=False).returncode == 0:
                        for t in adaylar:
                            K.gecis(sd, t["teslim"], "birlesti")
                        sonuc.update(durum="birlesti", birlesen=[t["teslim"] for t in adaylar], hedef_sha=sha)
                        break
                    sonuc["yeniden_temel"] += 1  # main arada ilerledi: yeni uca yeniden temellendir, yeniden koş
            finally:
                sonuc.update(kosu=kosu.sayi, bisect_kosu=kosu.bisect, flaky=kosu.flaky)
        return sonuc
    finally:
        nabiz.dur.set()
        sonuc["geri_donen"] = K.kurtar(sd, sahip=sahip)  # bitmeyenler (ff_basarisiz, hata) kuyruğa geri döner
        K.kosucu_birak(sd, sahip)
