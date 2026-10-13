// Orkestra token sayacı: motorun her tur sonunda bildirdiği KESİN kullanımı (turn.complete.usage) deftere yazar.
// Ana döngü ve her alt ajan (agentId) için ayrı satır; görev/süreç eşlemesini CLI yapar.
// Neden: alt ajan transkriptleri yanıtın başındaki kullanım anlık görüntüsünü tutar, çıkış tokenı eksik kalır.
import type { EngineInterface, Register } from 'claude-code'

type Kullanim = {
  model: string
  input_tokens: number
  output_tokens: number
  cache_read_input_tokens: number
  cache_creation_input_tokens: number
}

async function kaydet($: EngineInterface, agentId: string | undefined, u: Kullanim, sureMs: number): Promise<void> {
  // Orkestra kapalı projede hiçbir şey yapma.
  if (!(await $.fs.exists('.claude/orkestra'))) return
  const oturum = await $.session.id()
  const argv = [
    'python', `${$.plugin.root}/scripts/orkestra.py`, 'maliyet', 'tur',
    '--oturum', oturum, '--model', u.model,
    '--giris', String(u.input_tokens ?? 0), '--cikis', String(u.output_tokens ?? 0),
    '--onb-okuma', String(u.cache_read_input_tokens ?? 0), '--onb-yazma', String(u.cache_creation_input_tokens ?? 0),
    '--sure-ms', String(Math.round(sureMs ?? 0)),
  ]
  if (agentId !== undefined) argv.push('--agent-id', agentId)
  await $.process.run(argv, { timeoutMs: 20000 })
}

export const register: Register = on => {
  on('turn.complete', async ($, e, next) => {
    const sonuc = await next(e)
    if (e.usage !== undefined) {
      try {
        await kaydet($, e.agentId, e.usage, e.durationMs)
      } catch {
        // Sayaç hatası turu asla bozmaz; transkript tabanlı hook kaydı yedek olarak durur.
      }
    }
    return sonuc
  })
}
