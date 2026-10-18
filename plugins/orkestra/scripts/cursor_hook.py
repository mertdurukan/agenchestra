"""Cursor hook adaptörü: Cursor olayını Claude biçimine çevirip hook.py'yi çağırır, çıktıyı Cursor biçimine geri çevirir.

Kullanım (hooks/cursor-hooks.json): cursor_hook.py <cursorOlayAdı>   (stdin: Cursor JSON'u, BOM'lu olabilir)

hook.py değişmez; Cursor'a özgü tüm farklar burada toplanır:
- girdi: BOM, olay adı (camelCase → PascalCase), cwd (workspace_roots), araç adı (Shell → Bash), tool_output → tool_response
- çıktı: hookSpecificOutput → Cursor alanları (additional_context, permission, followup_message)
- salt okuma araçları ve ilgisiz PostToolUse çağrıları hook.py başlatılmadan geçilir (süre tasarrufu)
"""
import json
import os
import subprocess
import sys

OLAY_ESLEME = {
    "sessionStart": "SessionStart", "sessionEnd": "SessionEnd", "beforeSubmitPrompt": "UserPromptSubmit",
    "preToolUse": "PreToolUse", "postToolUse": "PostToolUse", "stop": "Stop",
    "subagentStart": "SubagentStart", "subagentStop": "SubagentStop",
}
ARAC_ESLEME = {"Shell": "Bash", "StrReplace": "Edit", "Delete": "Bash"}
SALT_OKUMA = {"Read", "Grep", "Glob", "LS", "SemanticSearch", "ReadLints", "TodoWrite"}
POST_ILGILI = {"Task", "Skill", "Agent", "Workflow"}


def _kok_dizin():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _yol_duzelt(y):
    """IDE workspace_roots'u başında bölü işaretiyle ('/<sürücü>:/...') verir; Windows yoluna çevirir."""
    if isinstance(y, str) and len(y) > 3 and y[0] == "/" and y[2] == ":":
        y = y[1:]
    return y


def girdi_donustur(cursor_olay, g):
    """Cursor payload'ını Claude hook girdisine çevirir."""
    c = dict(g)
    c.pop("user_email", None)  # kişisel veri: hook.py'ye, kanıta ve günlüklere geçmez
    c["hook_event_name"] = OLAY_ESLEME.get(cursor_olay, cursor_olay)
    kokler = g.get("workspace_roots")
    kokler = kokler if isinstance(kokler, list) else []
    proje = os.environ.get("CURSOR_PROJECT_DIR") or os.environ.get("CLAUDE_PROJECT_DIR") or (
        _yol_duzelt(kokler[0]) if kokler else "")
    if proje and not c.get("cwd"):
        c["cwd"] = proje
    ad = g.get("tool_name")
    if ad in ARAC_ESLEME:
        c["tool_name"] = ARAC_ESLEME[ad]
    ti = g.get("tool_input")
    if isinstance(ti, str):
        try:
            c["tool_input"] = json.loads(ti)
        except ValueError:
            c["tool_input"] = {"raw": ti}
    if "tool_output" in g and "tool_response" not in g:
        c["tool_response"] = g["tool_output"]
    return c


def atla(cursor_olay, g):
    """Hook.py'nin hiçbir şey yapmayacağı çağrılar (Claude eklentisindeki matcher'ların karşılığı)."""
    ad = g.get("tool_name")
    if cursor_olay == "preToolUse" and ad in SALT_OKUMA:
        return True
    if cursor_olay == "postToolUse" and ad not in POST_ILGILI:
        return True
    return False


def cikti_donustur(cursor_olay, claude):
    """hook.py çıktısını (Claude JSON'u ya da None) Cursor çıktısına çevirir."""
    if not claude or not isinstance(claude, dict):
        return {}
    ho = claude.get("hookSpecificOutput")
    ho = ho if isinstance(ho, dict) else {}
    ek = ho.get("additionalContext") or claude.get("additional_context")
    if cursor_olay == "sessionStart":
        return {"additional_context": ek} if ek else {}
    if cursor_olay == "beforeSubmitPrompt":
        o = {"continue": claude.get("continue", True)}
        if ek:
            o["additional_context"] = ek
        return o
    if cursor_olay == "preToolUse":
        karar = ho.get("permissionDecision")
        o = {}
        if karar:
            if karar == "ask" and os.environ.get("ORKESTRA_CURSOR_ASK", "deny") == "deny":
                karar = "deny"  # Cursor 'ask' kararını uygulamıyor (019 ölçümü); güvenli taraf: reddet
                neden = (ho.get("permissionDecisionReason") or "") + " (Cursor onay sormaz; kullanıcıya sor, onaylarsa kendisi çalıştırsın.)"
            else:
                neden = ho.get("permissionDecisionReason") or ""
            o["permission"] = karar
            if neden:
                o["user_message"] = neden
                o["agent_message"] = neden
        if ho.get("updatedInput") is not None:
            o["updated_input"] = ho["updatedInput"]
        if ek and "agent_message" not in o:
            o["agent_message"] = ek
        return o
    if cursor_olay == "postToolUse":
        return {"additional_context": ek} if ek else {}
    if cursor_olay == "stop":
        if claude.get("decision") == "block" or ho.get("decision") == "block":
            return {"followup_message": str(claude.get("reason") or ho.get("reason") or "")}
        return {}
    return {}


def _hook_py():
    return os.environ.get("ORKESTRA_CURSOR_HOOK_PY") or os.path.join(_kok_dizin(), "scripts", "hook.py")


def calistir(cursor_olay, ham):
    """Dönüş: (stdout_metni, çıkış_kodu, stderr_metni)."""
    try:
        g = json.loads(ham.decode("utf-8-sig") or "{}")
    except ValueError:
        return "{}", 0, ""
    if not isinstance(g, dict):  # stop aborted/error olaylarında gövde null/dizi gelebilir
        return "{}", 0, ""
    if atla(cursor_olay, g):
        return "{}", 0, ""
    claude_girdi = girdi_donustur(cursor_olay, g)
    env = dict(os.environ)
    env.setdefault("CLAUDE_PLUGIN_ROOT", _kok_dizin())
    if claude_girdi.get("cwd"):
        env.setdefault("CLAUDE_PROJECT_DIR", claude_girdi["cwd"])
    p = subprocess.run([sys.executable, _hook_py(), claude_girdi["hook_event_name"]],
                       input=json.dumps(claude_girdi).encode("utf-8"), capture_output=True, env=env)
    cikis = p.stdout.decode("utf-8", "replace").strip()
    try:
        claude = json.loads(cikis) if cikis else None
    except ValueError:
        claude = None
    return json.dumps(cikti_donustur(cursor_olay, claude), ensure_ascii=False), p.returncode, p.stderr.decode("utf-8", "replace")


def main():
    cursor_olay = sys.argv[1] if len(sys.argv) > 1 else ""
    ham = sys.stdin.buffer.read()
    metin, kod, hata = calistir(cursor_olay, ham)
    gunluk = os.environ.get("ORKESTRA_CURSOR_DEBUG")  # tanı: hangi olay geldi, ne döndü (dosya yolu)
    if gunluk:
        try:
            with open(gunluk, "a", encoding="utf-8") as f:
                f.write(json.dumps({"olay": cursor_olay, "kod": kod, "cikti": metin[:300], "hata": hata[-300:],
                                    "kok": os.environ.get("CURSOR_PLUGIN_ROOT"), "cwd": os.getcwd()}, ensure_ascii=False) + "\n")
        except OSError:
            pass
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hata:
        sys.stderr.write(hata)
    sys.stdout.write(metin)
    sys.exit(kod)


if __name__ == "__main__":
    main()
