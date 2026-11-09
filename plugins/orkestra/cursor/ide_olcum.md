# Cursor IDE ölçümü (issue #14, PR-2, P3)

Ölçüm: 2026-11-09/10, Cursor 3.29.15, Windows, bu depo açıkken canlı ajan oturumu. Kaydedici yalnız günlük yazar, hiçbir izni reddetmez (`scripts/cursor_olcum_gunluk.py`); günlük `$TEMP/orkestra_ide_olcum/olcum.jsonl`, 179 kayıt. Çözümleme: `python araclar/cursor_olcum.py --analiz <gunluk>`.

İkinci kanıt: Cursor'un kendi hook günlüğü (`cursor.hooks.workspaceId-*.log`, 20:07–21:13 UTC). İki kaynak olay kümesinde uyuşuyor.

## 1. Olay yüzeyi (G2 girdisi)

Gerçek yükle görülen 13 olay: `beforeSubmitPrompt` (1), `preToolUse` (47), `postToolUse` (42), `postToolUseFailure` (5), `subagentStart` (3), `subagentStop` (3), `beforeShellExecution` (33), `afterShellExecution` (33), `beforeMCPExecution` (1), `afterMCPExecution` (1), `afterFileEdit` (1), `beforeReadFile` (7), `afterAgentThought` (2).

Bu oturumda tetiklenmeyen 5 olay: `sessionStart`, `sessionEnd`, `stop`, `afterAgentResponse`, `preCompact`. Kaydedici oturum başladıktan sonra kurulduğu için ilk üçü bu oturumda beklenmez; `preCompact` ve `afterAgentResponse` hiç ateşlenmedi (doğrulanmadı: olayın varlığı, yalnız bu oturumdaki davranışı).

`failClosed` davranışı ölçülmedi (doğrulanmadı).

## 2. "Doğrulanmayanlar" listesinin ölçülen kısmı (bölüm 9)

| # | İddia | Sonuç |
|---|-------|-------|
| 2 | Hook yükünde `agent_id` yok | **Doğrulandı (yok).** 179 kaydın hiçbirinde `agent_id` yok. Alt ajan kimliği `subagent_id` + `tool_call_id` (subagentStart), üst ajan `parent_agent_id` + `parent_tool_call_id` (preToolUse, postToolUse, beforeReadFile). `subagentStop` kimliği `subagent_id` ile taşıyor. |
| 4 | Token alanı yok | **Doğrulandı (yok).** `token`/`usage`/`cost` adlı alan 13 olayın hiçbirinde yok. `duration` (sn, afterShell/afterMCP/postToolUse) ve `duration_ms` (subagentStop, afterAgentThought) var. |
| 5 | Çift yüklemede çift tetik | **Kısmen.** Aynı `tool_use_id` ile iki `preToolUse` görüldü (toolu_0142…: biri Read, 4 sn sonra Write). Aynı aracın tekrarı değil, kimliklerin bağımsız olmadığına dair tek örnek; genelleme için yetersiz (doğrulanmadı). |
| 7 | Task paralelliği | **Doğrulandı.** Aynı anda başlatılan 3 alt ajan çakıştı: subagentStart 31.16 / 33.03 / 34.98 sn, subagentStop 45.49 / 46.58 / 47.81 sn (aynı kuşak). Üçü de `is_parallel_worker: false` ile geldi; bayrak paralelliği göstermiyor, zaman çakışması gösteriyor. |
| 8 | Hook gecikmesinin payı | **Ölçüldü.** Kaydedicinin kendi işi p50 2.85 ms, p95 32.1 ms (n=179). Adaptörün salt okuma yolu (Cursor'suz, yerel) p50 138.5 ms, p95 156.7 ms (n=15). IDE'nin süreç başına duvar saati (Cursor günlüğünden, başlatma dahil) p50: preToolUse 1533 ms (n=250), beforeShellExecution 1250 ms (n=24), subagentStart 220 ms (n=1); p95 preToolUse 2974 ms. 18 hook zaman aşımına düştü (10 sn sınır). |

## 3. Alan notları (sonraki PR'lar için)

- subagentStart alanları: `subagent_id`, `subagent_type`, `subagent_model`, `task`, `tool_call_id`, `parent_conversation_id`, `is_parallel_worker`. `agent_id`/`agent_type` yok; PR-4 belirteci bu alanlara dayanmalı.
- `model` her olayda var (ör. `claude-sonnet-5-5-high`); `model_id` ve `model_params` yalnız `beforeSubmitPrompt` ve `afterAgentThought`'ta. PR-6 eşlemesi bu dizgelere bakabilir.
- `session_id` ile `conversation_id` her kayıtta eşit (ADR-0172 bulgusuyla uyumlu, n=179).
- Ortam: yalnız `CURSOR_VERSION` ve `CURSOR_PROJECT_DIR` geldi. `CURSOR_PLUGIN_ROOT`, `CURSOR_CONVERSATION_ID`, `CURSOR_TRACE_ID` hook sürecine gelmedi (doğrulandı, bu kurulumda).

## 4. Gizlilik

Günlük ham yükü tutar: komut metinleri, dosya yolları, araç çıktıları (160 karakterden sonrası kesik), `user_email` atılmış halde. Günlük depoda değildir; `ide_olcum.md` yalnız yapı ve sayım taşır.

## 5. Geri alma

`python araclar/cursor_olcum.py --kaldir <hooks.json>` yedeği (`<dosya>.orkestra_yedek`) geri koyar. Kaydedici karar üretmez; kaldırılınca ölçüm durur, başka davranışı değiştirmez.

## 6. Kalan boşluk

`ask` kararı (madde 1), ajan frontmatter'ının okunması (madde 3) ve manifest `skills`/`agents` yolunun taramayı değiştirmesi (madde 6) bu ölçümde yok: üçü de kod değişikliği ya da kasıtlı deneme gerektirir, PR-3 ve PR-5'e aittir. `sessionStart`/`sessionEnd`/`stop`/`preCompact`/`afterAgentResponse` olaylarının yükü ölçülmedi.
