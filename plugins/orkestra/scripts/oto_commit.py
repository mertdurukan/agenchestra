"""PostToolUse (Edit|Write|MultiEdit|NotebookEdit): değişen dosyayı otomatik commit eder; proje bazında açılır.

Açma: projenin `.claude/settings.json` `env` bloğunda `ORKESTRA_OTO_COMMIT=1`. Varsayılan kapalıdır; kapalıyken
hiçbir modül yüklemeden çıkar (her düzenlemede çalıştığı için hook.py'den ayrı ve hafif tutulur).
Atıf satırı: `ORKESTRA_OTO_COMMIT_ATIF` (yoksa genel Claude satırı).

Yalnız o dosya commit edilir (pathspec); başka oturumların değişiklikleri ve paylaşılan indeksteki diğer girdiler
etkilenmez. Depo kökü dosyanın klasöründen bulunur (proje dışındaki depolarda da çalışır). .gitignore'daki
dosyalar atlanır. Hata olursa sessiz çıkar, aracı bloklamaz.
"""
import os
import sys

ATIF_VARSAYILAN = "Co-Authored-By: Claude <noreply@anthropic.com>"


def acik() -> bool:
    return (os.environ.get("ORKESTRA_OTO_COMMIT") or "").strip().lower() in ("1", "true", "evet", "acik", "açık")


def depo_koku(klasor):
    """Üst klasörlere çıkıp .git (klasör ya da worktree dosyası) arar; süreç başlatmaz."""
    while True:
        if os.path.exists(os.path.join(klasor, ".git")):
            return klasor
        ust = os.path.dirname(klasor)
        if ust == klasor:
            return None
        klasor = ust


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
        atif = (os.environ.get("ORKESTRA_OTO_COMMIT_ATIF") or "").strip() or ATIF_VARSAYILAN
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
