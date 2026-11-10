# P15 güvenlik incelemesi — PR-3 (G2, G3)

**Karar:** KOŞULLU GO (10.11.2026). Sahip kalan kararları ajana bıraktı; varsayılan zorlama deny kalır.

**Kanıt:** https://cursor.com/docs/hooks (bu tur); plugins/orkestra/scripts/cursor_hook.py:101-103; plugins/orkestra/hooks/cursor-hooks.json; plugins/orkestra/cursor/ide_olcum.md:13 ve :41.

## Bulgular

1. preToolUse çıktısında ask şemada kabul edilir, uygulanmaz (cursor.com/docs/hooks, preToolUse permission).
2. beforeShellExecution ve beforeMCPExecution allow, deny veya ask döner; failClosed varsayılan false (aynı belge).
3. Bugün ask, ORKESTRA_CURSOR_ASK varsayılan deny ile deny olur (cursor_hook.py:101-103).
4. cursor-hooks.json altı olay bağlar; beforeShell, beforeMCP ve failClosed yok.
5. IDE ask diyaloğu ölçülmedi (ide_olcum.md:41). Forumdaki “ask yok sayılır” iddiası zorlama dayanağı değil.

## Zorunlu kurallar (sonraki PR-3 kodu)

1. Koruma kancalarında failClosed true: beforeShellExecution, beforeMCPExecution ve yazma/silme deny yolu.
2. ask yalnız beforeShellExecution ve beforeMCPExecution. preToolUse ask zorlamaz; deny, allow veya updated_input.
3. Write, Delete ve Edit: deny artı user_message ve agent_message. ask yok.
4. ORKESTRA_CURSOR_ASK varsayılan deny. Değer ask yalnız opt-in ölçüm bayrağıdır.
5. Varsayılanı ask yapmak için IDE kanıtı gerekir: ask dönüşü diyalog açtı ve onay olmadan komut çalışmadı. Doğrulanmadı; deny kalır.
6. Kanca zaman aşımında failClosed eylemi keser. ide_olcum 18 zaman aşımı (10 sn); asılı kalan koruma kabul değil.
7. permissionDecisionReason sır veya token taşımaz. user_email günlüğe yazılmaz.
8. Aynı tool_use_id tekrarında karar idempotenttir; deny kazanır.
9. Eksik veya beklenmeyen mcp_server_name deny sayılır (resmi belge önerisi).

## Alternatifler

- Seçilen: deny varsayılan, failClosed zorunlu, ask opt-in. Neden: preToolUse ask uygulanmıyor; IDE ask ölçümü yok.
- Elenen: yalnız bugünkü ask→deny, yüzey ekleme. Neden elendi: G2 (beforeShell, beforeMCP, failClosed) açık kalır.
- Elenen: ask’ı varsayılan yapmak. Neden elendi: fail-open riski; PoC yok.

## Geri alma

PR-3 geri alınırsa cursor-hooks altı olaya döner; ORKESTRA_CURSOR_ASK yok sayılır ve deny kalır.
