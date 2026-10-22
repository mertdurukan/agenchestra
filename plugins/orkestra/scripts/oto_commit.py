"""PostToolUse (Edit|Write|MultiEdit|NotebookEdit): değişen dosyayı otomatik commit eder; proje bazında açılır.

Açma: projenin `.claude/settings.json` `env` bloğunda `ORKESTRA_OTO_COMMIT=1`. Varsayılan kapalıdır; kapalıyken
hiçbir modül yüklemeden çıkar (her düzenlemede çalıştığı için hook.py'den ayrı ve hafif tutulur).
Atıf satırı: `ORKESTRA_OTO_COMMIT_ATIF`; yoksa transcript'teki son assistant modelinden türetilir
(claude-sonnet-5-5 → "Claude Sonnet 5.5"); transcript okunamazsa genel Claude satırı.

Yalnız o dosya commit edilir (pathspec); başka oturumların değişiklikleri ve paylaşılan indeksteki diğer girdiler
etkilenmez. Depo kökü dosyanın klasöründen bulunur (proje dışındaki depolarda da çalışır). .gitignore'daki
dosyalar atlanır. Hata olursa sessiz çıkar, aracı bloklamaz.
"""
import os
import sys

ATIF_VARSAYILAN = "Co-Authored-By: Claude <noreply@anthropic.com>"


def acik() -> bool:
    return (os.environ.get("ORKESTRA_OTO_COMMIT") or "").strip().lower() in ("1", "true", "evet", "acik", "açık")


def model_atfi(transcript_yolu):
    """Transcript'in son assistant modelinden 'Co-Authored-By: Claude <Aile> <sürüm> <...>' satırı; bulunamazsa None."""
    import json
    import re
    if not transcript_yolu or not os.path.isfile(transcript_yolu):
        return None
    son = ""
    with open(transcript_yolu, "rb") as f:
        f.seek(0, 2)
        boy = f.tell()
        f.seek(max(0, boy - 400000))
        for ham in f.read().splitlines():
            try:
                o = json.loads(ham)
            except Exception:
                continue
            ms = o.get("message") if isinstance(o, dict) else None
            if isinstance(ms, dict) and ms.get("role") == "assistant" and isinstance(ms.get("model"), str):
                son = ms["model"]
    m = re.match(r"claude-([a-z]+)-(\d+)(?:-(\d+))?", son)
    if not m:
        return None
    surum = ".".join(x for x in (m.group(2), m.group(3)) if x)
    return f"Co-Authored-By: Claude {m.group(1).capitalize()} {surum} <noreply@anthropic.com>"


def depo_koku(klasor):
    """Üst klasörlere çıkıp .git (klasör ya da worktree dosyası) arar; süreç başlatmaz."""
    while True:
        if os.path.exists(os.path.join(klasor, ".git")):
            return klasor
        ust = os.path.dirname(klasor)
        if ust == klasor:
            return None
        klasor = ust


def _git(repo, *args):
    import subprocess
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, encoding="utf-8")


def klasorleri_commit(repo, onekler, atif_kaynagi, git=None, etiket="kabuk"):
    """Depo köküne göre `onekler` altındaki değişmiş .md/.json dosyalarını tek commit'te kaydeder; commit edilen yolları döndürür."""
    import time
    git = git or _git
    onekler = [o.replace("\\", "/").strip("/") + "/" for o in onekler if o]
    if not onekler or not repo:
        return []
    yollar = []
    for kayit in git(repo, "status", "--porcelain", "-z", "-uall").stdout.split("\0"):
        yol = kayit[3:].strip('"')
        if len(kayit) > 3 and yol.endswith((".md", ".json")) and any(yol.startswith(o) for o in onekler):
            yollar.append(yol)
    if not yollar:
        return []
    atif = (os.environ.get("ORKESTRA_OTO_COMMIT_ATIF") or "").strip() or model_atfi(atif_kaynagi) or ATIF_VARSAYILAN
    govde = "\n".join(yollar[:20])
    msg = f"Otomatik commit: {len(yollar)} dosya ({etiket})\n\n{govde}\n\n{atif}"
    for _ in range(5):  # paralel oturumlarda index.lock bekle
        a = git(repo, "add", "--", *yollar)
        c = git(repo, "commit", "-m", msg, "--", *yollar) if a.returncode == 0 else a
        if c.returncode == 0 or "index.lock" not in (c.stderr or ""):
            break
        time.sleep(1)
    return yollar


def kabuk_commit(veri, git):
    """Kabuk komutundan sonra, ORKESTRA_OTO_COMMIT_BASH_YOLLAR öneklerinin altındaki .md/.json değişikliklerini kaydeder."""
    onekler = [y.strip() for y in (os.environ.get("ORKESTRA_OTO_COMMIT_BASH_YOLLAR") or "").split(",") if y.strip()]
    cwd = veri.get("cwd")
    klasorleri_commit(depo_koku(cwd) if cwd else None, onekler, veri.get("transcript_path"), git)


def cli_sonrasi(klasorler):
    """`orkestra is|plan` komutundan sonra: iş kaydındaki klasörlerin .md/.json belgelerini commit eder (ayar gerekmez).
    Anahtar kapalıysa, depo yoksa ya da klasör depo dışındaysa sessiz çıkar; komutu bozmaz."""
    try:
        if not acik():
            return
        gruplar = {}
        for k in klasorler:
            if k and os.path.isdir(k):
                repo = depo_koku(os.path.abspath(k))
                if repo:
                    gruplar.setdefault(repo, []).append(os.path.relpath(os.path.abspath(k), repo))
        for repo, goreli in gruplar.items():
            klasorleri_commit(repo, [g for g in goreli if not g.startswith("..")], None, etiket="orkestra")
    except Exception:
        pass


def main():
    if not acik():
        return
    import json
    import subprocess
    import time

    def git(repo, *args):
        return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, encoding="utf-8")

    try:
        veri = json.load(sys.stdin)
        g = veri.get("tool_input") or {}
        if veri.get("tool_name") in ("Bash", "PowerShell"):
            kabuk_commit(veri, git)
            return
        yol = g.get("file_path") or g.get("notebook_path")
        if not yol or not os.path.isfile(yol):
            return
        yol = os.path.abspath(yol)
        repo = depo_koku(os.path.dirname(yol))
        if not repo:
            return
        # .gitignore'daki izlenmeyen dosya status'ta görünmez; ayrı check-ignore çağrısı gerekmez
        durum = git(repo, "status", "--porcelain", "--", yol).stdout
        if not durum.strip():
            return
        yeni = durum.startswith("??")  # yalnız izlenmeyen dosya add ister; izlenen dosyada commit pathspec'i yeter
        rel = os.path.relpath(yol, repo).replace("\\", "/")
        atif = (os.environ.get("ORKESTRA_OTO_COMMIT_ATIF") or "").strip()             or model_atfi(veri.get("transcript_path")) or ATIF_VARSAYILAN
        msg = f"Otomatik commit: {rel}\n\n{atif}"
        for _ in range(5):  # paralel oturumlarda index.lock bekle
            a = git(repo, "add", "--", yol) if yeni else None
            c = git(repo, "commit", "-m", msg, "--", yol) if a is None or a.returncode == 0 else a
            if c.returncode == 0 or "index.lock" not in (c.stderr or ""):
                break
            time.sleep(1)
    except Exception:
        pass


if __name__ == "__main__":
    main()
