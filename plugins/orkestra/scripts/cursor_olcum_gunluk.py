"""Cursor IDE ölçüm kaydedicisi (issue #14, PR-2, P3).

Yalnız günlük yazar; hiçbir kararı etkilemez. Kullanım (hooks.json): cursor_olcum_gunluk.py <olay>
Günlük: $ORKESTRA_OLCUM_GUNLUK (varsayılan: <geçici klasör>/orkestra_ide_olcum/olcum.jsonl).
Gizlilik: user_email atılır, uzun metin alanları ilk 160 karaktere kısalır; yapı (anahtarlar) tam kalır.
Çıktı: izin isteyen olaylarda {"permission":"allow"}, diğerlerinde {}; çıkış kodu her zaman 0.
"""
import json
import os
import sys
import tempfile
import time

IZIN_OLAYLARI = {"preToolUse", "beforeShellExecution", "beforeMCPExecution", "subagentStart", "beforeReadFile"}
ORTAM_ANAHTARLARI = ("CURSOR_VERSION", "CURSOR_PLUGIN_ROOT", "CURSOR_PROJECT_DIR", "CURSOR_CONVERSATION_ID",
                     "CURSOR_TRACE_ID", "CLAUDE_PLUGIN_ROOT")


def kisalt(v, derinlik=0):
    if isinstance(v, str):
        return v if len(v) <= 160 else v[:160] + "…[%d]" % len(v)
    if isinstance(v, dict) and derinlik < 6:
        return {k: kisalt(x, derinlik + 1) for k, x in v.items()}
    if isinstance(v, list) and derinlik < 6:
        return [kisalt(x, derinlik + 1) for x in v[:20]]
    return v


def gunluk_yolu():
    return os.environ.get("ORKESTRA_OLCUM_GUNLUK") or os.path.join(tempfile.gettempdir(), "orkestra_ide_olcum", "olcum.jsonl")


def main():
    olay = sys.argv[1] if len(sys.argv) > 1 else ""
    t0 = time.time()
    ham = sys.stdin.buffer.read()
    try:
        yuk = json.loads(ham.decode("utf-8-sig") or "null")
    except ValueError:
        yuk = {"_gecersiz_json": True}
    if isinstance(yuk, dict):
        yuk.pop("user_email", None)
    kayit = {"t": t0, "olay": olay, "pid": os.getpid(), "yuk": kisalt(yuk),
             "ortam": {k: os.environ[k] for k in ORTAM_ANAHTARLARI if k in os.environ}}
    try:
        yol = gunluk_yolu()
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        kayit["sure_ms"] = round((time.time() - t0) * 1000, 2)
        with open(yol, "a", encoding="utf-8") as f:
            f.write(json.dumps(kayit, ensure_ascii=False) + "\n")
    except OSError:
        pass
    sys.stdout.write(json.dumps({"permission": "allow"} if olay in IZIN_OLAYLARI else {}))
    sys.exit(0)


if __name__ == "__main__":
    main()
