"""Testler için CLI koşucusu: orkestra.py / hook.py çağrılarını SÜREÇ İÇİNDE koşar (alt süreç yerine).

Neden: her alt süreç ~0,4-0,7 sn (Python açılışı + modül içe aktarımı); entegrasyon testleri test başına 4-10 CLI
çağrısı yapıyor ve takımın çoğu süresi buydu. Süreç içi çağrı aynı argv, cwd, ortam ve stdin ile main()'i koşar,
çıkış kodunu SystemExit'ten alır, stdout/stderr'i yakalar; subprocess.CompletedProcess döner (çağıranlar değişmez).

Alt sürece düşen durumlar (davranış farkı riski):
- komut orkestra.py / hook.py değilse (test betiği, git, node);
- ortam HOME/USERPROFILE'ı değiştiriyorsa (GENEL_DIZIN içe aktarımda hesaplanır);
- ORKESTRA_IC_KOS=0 ise (uçtan uca doğrulama: tüm takım gerçek alt süreçle koşar).
Uçtan uca kalan testler kendi subprocess.run çağrılarını kullanır (ör. test_hook_python, test_yayin).
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import subprocess
import sys
import threading
import traceback

# Süreç içi yol sys.argv/os.environ/cwd/stdin/stdout'u süreç genelinde değiştirir; eşzamanlı iş parçacıkları
# birbirinin durumunu ezmesin diye tek kilit altında seri koşar (alt süreç yolu kilitsiz).
# Mevcut testler teknik not vermez: varsayılan kapı kapalı (yeni testler açıkça '1' yapar).
os.environ.setdefault("ORKESTRA_TEKNIK_KAPISI", "0")
os.environ.setdefault("ORKESTRA_MEVCUT_KAPISI", "0")  # mevcut-durum kapısı: yeni testler açıkça '1' yapar
os.environ.setdefault("ORKESTRA_SIRA_KAPISI", "0")  # iş sırası kapısı (P-005): yeni testler açıkça '1' yapar
os.environ.setdefault("ORKESTRA_DOKTOR_OTOMATIK", "0")  # hızlı yol arka plan doktoru başlatmasın (I-026 P9)
os.environ.setdefault("ORKESTRA_OZET_KAPISI", "0")  # kapanış özet kapısı (P-009): yeni testler açıkça '1' yapar
os.environ.setdefault("ORKESTRA_ADR_KAPISI", "0")  # kapanış ADR kapısı (P-015): eski testler ADR satırsız kapatır; ADR testleri '1' yapar
os.environ.setdefault("ORKESTRA_DOGRULAMA_KAPISI", "0")  # plan ✅/❌ kapısı: yeni testler açıkça '1' yapar
# Eklenti kural katmanı: testler gerçek depoyu görmesin (conftest.py ile aynı varsayılan; unittest ile koşulunca da geçerli)
import tempfile as _tempfile  # noqa: E402
os.environ.setdefault("ORKESTRA_EKLENTI_KURALLARI",
                      os.path.join(_tempfile.gettempdir(), "orkestra_test_eklenti_yok", "kurallar", "eklenti_kurallari.json"))
_KILIT = threading.RLock()
_MODULLER: dict = {}
_EV_ANAHTARLARI = ("USERPROFILE", "HOME", "HOMEDRIVE", "HOMEPATH")


def _modul(yol: str):
    yol = os.path.abspath(yol)
    m = _MODULLER.get(yol)
    if m is None:
        kok = os.path.dirname(yol)
        if kok not in sys.path:
            sys.path.insert(0, kok)
        ad = "_ic_kos_" + os.path.splitext(os.path.basename(yol))[0]
        spec = importlib.util.spec_from_file_location(ad, yol)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        _MODULLER[yol] = m
        # İçe aktarımda ev yolu hesaplayan modüller gerçek evle ŞİMDİ yüklensin; çağrı içinde ilk kez (testin
        # ortamıyla) yüklenirse sabitleri o testin geçici evine bağlı kalırdı.
        for ad in sorted(os.listdir(kok)):
            if ad.endswith(".py") and ad[:-3] not in sys.modules and ad not in ("orkestra.py", "hook.py"):
                try:
                    importlib.import_module(ad[:-3])
                except Exception:
                    pass
    return m


def _ic_mi(args: list) -> bool:
    if os.environ.get("ORKESTRA_IC_KOS") == "0" or not args:
        return False
    return os.path.basename(str(args[0])) in ("orkestra.py", "hook.py")


def _ev(ortam) -> str:
    return ortam.get("USERPROFILE") or ortam.get("HOME") or os.path.expanduser("~")


@contextlib.contextmanager
def _ev_degisimi(env: dict | None, betik_koku: str):
    """Ortam ev dizinini değiştiriyorsa içe aktarımda hesaplanmış ev yollarını (GENEL_DIZIN ve türevleri) geçici
    olarak yeni eve çevirir; çağrı bitince geri yükler."""
    if env is None or all(env.get(k) == os.environ.get(k) for k in _EV_ANAHTARLARI):
        yield
        return
    eski_ev, yeni_ev = os.path.normcase(os.path.abspath(_ev(os.environ))), os.path.abspath(_ev(env))
    geri = []
    for m in list(sys.modules.values()):
        dosya = getattr(m, "__file__", None)
        if not dosya or os.path.normcase(os.path.dirname(os.path.abspath(dosya))) != os.path.normcase(betik_koku):
            continue
        for ad, v in list(vars(m).items()):
            if isinstance(v, str) and ad.isupper() and os.path.normcase(v).startswith(eski_ev + os.sep):
                geri.append((m, ad, v))
                setattr(m, ad, yeni_ev + v[len(eski_ev):])
    try:
        yield
    finally:
        for m, ad, v in geri:
            setattr(m, ad, v)


def kos(args: list, cwd: str | None = None, env: dict | None = None, input: str | None = None,
        timeout: float | None = None) -> subprocess.CompletedProcess:
    """`[sys.executable] + args` ile aynı sözleşme; metin kipinde CompletedProcess döner."""
    if not _ic_mi(args):
        return subprocess.run([sys.executable] + list(args), cwd=cwd, env=env, input=input, capture_output=True,
                              text=True, encoding="utf-8", timeout=timeout)
    with _KILIT:
        return _ic_kos(args, cwd, env, input)


def _ic_kos(args: list, cwd: str | None, env: dict | None, input: str | None) -> subprocess.CompletedProcess:
    m = _modul(args[0])
    eski = (list(sys.argv), dict(os.environ), os.getcwd(), sys.stdin)
    out, err = io.StringIO(), io.StringIO()
    kod = 0
    try:
        if env is not None:
            os.environ.clear()
            os.environ.update(env)
        if cwd:
            os.chdir(cwd)
        sys.argv = [str(args[0])] + [str(a) for a in args[1:]]
        sys.stdin = io.TextIOWrapper(io.BytesIO((input or "").encode("utf-8")), encoding="utf-8")
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                _ev_degisimi(env, os.path.dirname(os.path.abspath(args[0]))):
            try:
                m.main()
            except SystemExit as e:
                if isinstance(e.code, int) or e.code is None:
                    kod = e.code or 0
                else:  # sys.exit("mesaj"): mesaj stderr'e, çıkış 1 (yorumlayıcıyla aynı)
                    print(e.code, file=sys.stderr)
                    kod = 1
            except Exception:
                traceback.print_exc()
                kod = 1
    finally:
        sys.argv, sys.stdin = eski[0], eski[3]
        os.chdir(eski[2])
        os.environ.clear()
        os.environ.update(eski[1])
    return subprocess.CompletedProcess([sys.executable] + list(args), kod, out.getvalue(), err.getvalue())
