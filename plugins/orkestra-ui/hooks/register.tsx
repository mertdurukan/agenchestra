import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { KartOzeti, UiOzet } from '../types'

const PANE = 'orkestra'
const veri = atom({ plugin: 'orkestra-ui', key: 'veri' } as const, null)
const bantGizli = atom({ plugin: 'orkestra-ui', key: 'bantGizli' } as const, false)

const DURUM_RENGI: Record<string, string> = {
  isleniyor: 'suggestion',
  denetimde: 'warning',
  reddedildi: 'error',
  onaylandi: 'success',
  teslim: 'inactive',
  beklemede: 'inactive',
  planlandi: 'subtle',
  iptal: 'inactive',
}

const IZLENEN = ['.claude/orkestra/maliyet.jsonl', '.claude/orkestra/ortak_defter.jsonl', '.claude/orkestra/gorevler', '.claude/orkestra/ruya']

function usd(n: number | undefined): string {
  return `$${(n ?? 0).toFixed(2)}`
}

function kes(s: string, n: number): string {
  return s.length <= n ? s : s.slice(0, Math.max(0, n - 1)) + '…'
}

// Modül düzeyi durum: yeniden yüklemede sıfırlanır, sorun değil (gösterilen veri $.state'te).
let sonImza = ''
let sonRet = 0
let calisiyor = false

async function imza($: EngineInterface): Promise<string> {
  const parcalar: string[] = []
  for (const yol of IZLENEN) {
    const st = await $.fs.stat(yol).catch(() => undefined)
    parcalar.push(st ? `${st.mtimeMs}:${st.size}` : '-')
  }
  return parcalar.join('|')
}

async function yenile($: EngineInterface, zorla: boolean): Promise<void> {
  if (calisiyor) return
  calisiyor = true
  try {
    const yeni = await imza($)
    if (!zorla && yeni === sonImza) return
    sonImza = yeni
    const betik = `${$.plugin.root}/../orkestra/scripts/orkestra.py`
    const oturum = await $.session.id()
    const r = await $.process.run(['python', betik, 'ui-ozet', '--oturum', oturum], { timeoutMs: 20000 })
    if (r.exitCode !== 0) return
    const o = JSON.parse(r.stdout) as UiOzet
    const ret = o.sayac?.reddedildi ?? 0
    if (ret > sonRet) $.ui.toast(`Orkestra: denetçi ${ret - sonRet} işi reddetti — düzeltme/yükseltme gerekiyor.`)
    sonRet = ret
    await update($, veri, () => o)
  } catch {
    // Arayüz sessizce eski veriyle kalır; orkestra çekirdeği etkilenmez.
  } finally {
    calisiyor = false
  }
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({ name: 'orkestra', description: 'Orkestra panelini aç: görev kartları, denetim, maliyet, ortak defter' })
    await yenile($, true)
    $.clock.every(4000, () => void yenile($, false))
    return next(e)
  })

  on('command.run', { command: 'orkestra' }, async $ => {
    await yenile($, true)
    await update($, bantGizli, () => false)
    await $.ui.open({ id: PANE, title: 'Orkestra' })
    return { text: 'Orkestra paneli açıldı.' }
  })

  on('turn.complete', async ($, e, next) => {
    const sonuc = await next(e)
    void yenile($, true)
    return sonuc
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const o = await read($, veri)
    const w = Math.max(40, e.props.bodyColumns ?? 80)
    if (o === null) {
      return <Box><Text dimColor>Orkestra verisi yükleniyor…</Text></Box>
    }
    if (!o.acik) {
      return (
        <Box flexDirection="column">
          <Text>Bu projede orkestra kapalı.</Text>
          <Text dimColor>/orkestra:baslat ile aç.</Text>
        </Box>
      )
    }
    const kartlar: KartOzeti[] = o.kartlar ?? []
    const m = o.maliyet
    const surec = Object.entries(m?.surec ?? {}).map(([k, v]) => `${k} ${usd(v)}`).join(' · ')
    const model = Object.entries(m?.model ?? {}).map(([k, v]) => `${k} ${usd(v)}`).join(' · ')
    const ruya = o.ruya?.calisiyor ? 'rüya çalışıyor' : o.ruya?.rapor ? 'rüya raporu hazır → /orkestra:ruya' : o.ruya?.zamani_geldi ? 'rüya zamanı geldi' : ''
    return (
      <Box flexDirection="column">
        <Text bold>Görev kartları</Text>
        {kartlar.length === 0 && <Text dimColor>Açık kart yok. İş başlatmak için /orkestra:is &lt;istek&gt;</Text>}
        {kartlar.map(k => (
          <Text wrap="truncate">
            <Text color={DURUM_RENGI[k.durum] ?? 'text'}>{k.id.padEnd(6)} {k.durum.padEnd(10)}</Text>
            <Text dimColor> {k.basamak} işçi:{k.isci} den:{k.denetim} {usd(k.usd)} </Text>
            {kes(k.baslik, w - 48)}
          </Text>
        ))}
        <Text> </Text>
        <Text bold>Token ve maliyet</Text>
        <Text>Bu oturum {usd(m?.oturum)} · bugün {usd(m?.bugun)}</Text>
        {surec !== '' && <Text dimColor wrap="truncate">Süreç: {surec}</Text>}
        {model !== '' && <Text dimColor wrap="truncate">Model: {model}</Text>}
        <Text> </Text>
        <Text bold>Sohbetler (bu çalışma alanı)</Text>
        {(o.sohbetler ?? []).length === 0 && <Text dimColor>Henüz maliyetli sohbet yok.</Text>}
        {(o.sohbetler ?? []).map(s => (
          <Text wrap="truncate">
            <Text color={s.bu ? 'claude' : 'text'}>{s.bu ? '▸ ' : '  '}{usd(s.usd).padStart(8)} </Text>
            {kes(s.baslik, w - 30)}
            <Text dimColor> {s.son}{s.kaynak === 'defter' ? ' ≈' : ''}</Text>
          </Text>
        ))}
        <Text dimColor>≈ açık sohbet: orkestra defteri; kapanınca motorun kendi hesabı gösterilir.</Text>
        <Text> </Text>
        <Text bold>Ortak defter (son kayıtlar)</Text>
        {(o.defter ?? []).length === 0 && <Text dimColor>Henüz kayıt yok.</Text>}
        {(o.defter ?? []).map(s => <Text dimColor wrap="truncate">{kes(s, w)}</Text>)}
        {ruya !== '' && <Text> </Text>}
        {ruya !== '' && <Text color="suggestion">{ruya}</Text>}
      </Box>
    )
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const o = await read($, veri)
    if (e.props.hasSurvey || o === null || !o.acik || (await read($, bantGizli))) return next(e)
    const s = o.sayac ?? {}
    const acik = (s.isleniyor ?? 0) + (s.denetimde ?? 0) + (s.reddedildi ?? 0) + (s.onaylandi ?? 0)
    const oturum = o.maliyet?.oturum ?? 0
    if (acik === 0 && oturum === 0 && !o.ruya?.rapor) return next(e)
    const { Box, Button, Text } = $.ui.resolve(e)
    const parca: string[] = []
    if (s.isleniyor) parca.push(`${s.isleniyor} işleniyor`)
    if (s.denetimde) parca.push(`${s.denetimde} denetimde`)
    if (s.reddedildi) parca.push(`${s.reddedildi} ret`)
    if (s.onaylandi) parca.push(`${s.onaylandi} teslime hazır`)
    parca.push(`oturum ${usd(oturum)}`)
    if (o.ruya?.rapor) parca.push('rüya raporu hazır')
    return (
      <Box>
        <Text dimColor>Orkestra · {parca.join(' · ')} </Text>
        <Button key="panel" label="Panel" onPress={() => $.ui.open({ id: PANE, title: 'Orkestra' })} />
        <Button key="gizle" label="Gizle" onPress={() => update($, bantGizli, () => true)} />
      </Box>
    )
  })
}
