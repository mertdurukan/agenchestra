import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { HamOzet, KartOzeti, UiOzet } from '../types'

// Veri kaynağı: çekirdek plugin'in hook'ları ve CLI'ı her durum değişikliğinde `.claude/orkestra/ozet.json` yazar.
// Mod yalnız bu dosyayı okur (süreç başlatmaz); okuyamazsa nedenini panelde gösterir.
const OZET = '.claude/orkestra/ozet.json'
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
const ACIK = ['isleniyor', 'denetimde', 'reddedildi', 'onaylandi', 'beklemede', 'planlandi']

function usd(n: number | undefined): string {
  return `$${(n ?? 0).toFixed(2)}`
}

function kes(s: string, n: number): string {
  return s.length <= n ? s : s.slice(0, Math.max(0, n - 1)) + '…'
}

// Ham anlık görüntüyü bu oturumun gözünden panel verisine çevirir.
export function donustur(h: HamOzet, oturum: string): UiOzet {
  const ot = h.maliyet?.oturumlar?.[oturum]
  const kartlar: KartOzeti[] = (h.kartlar ?? [])
    .filter(k => ACIK.includes(k.durum) || k.oturum === oturum)
    .slice(0, 25)
    .map(k => ({ id: k.id, baslik: k.baslik, durum: k.durum, basamak: k.basamak, isci: k.isci, denetim: k.denetim, usd: k.usd }))
  return {
    acik: true,
    kartlar,
    sayac: h.sayac ?? {},
    maliyet: { bugun: h.maliyet?.bugun ?? 0, oturum: ot?.usd ?? 0, surec: ot?.surec ?? {}, model: ot?.model ?? {} },
    defter: (h.defter ?? []).slice(-6).map(r => `${(r.zaman ?? '').slice(11, 16)} ${r.gorev} ${r.surec} · ${r.ajan}: ${r.metin}`),
    sohbetler: (h.sohbetler ?? []).slice(0, 8).map(s => ({
      baslik: s.baslik, usd: s.usd, kaynak: s.kaynak, bu: s.oturum === oturum, son: (s.son ?? '').slice(5, 16).replace('T', ' '),
    })),
    ruya: h.ruya,
    uretim: h.uretim,
  }
}

// Modül düzeyi durum: yeniden yüklemede sıfırlanır (gösterilen veri $.state'te kalır).
let sonImza = ''
let sonRet = 0
let calisiyor = false

async function yenile($: EngineInterface, zorla: boolean): Promise<void> {
  if (calisiyor) return
  calisiyor = true
  try {
    const st = await $.fs.stat(OZET).catch(() => undefined)
    if (st === undefined) {
      const acik = await $.fs.exists('.claude/orkestra').catch(() => false)
      await update($, veri, () => (acik
        ? { acik: true, hata: 'ozet.json henüz yok: bir tur bitince oluşur (ya da Bash: orkestra ui-ozet --yaz).' }
        : { acik: false }))
      return
    }
    const imza = `${st.mtimeMs}:${st.size}`
    if (!zorla && imza === sonImza) return
    sonImza = imza
    const metin = await $.fs.read(OZET)
    const ham = JSON.parse(metin) as HamOzet
    const o = donustur(ham, await $.session.id())
    const ret = o.sayac?.reddedildi ?? 0
    if (ret > sonRet) $.ui.toast(`Orkestra: denetçi ${ret - sonRet} işi reddetti — düzeltme ya da yükseltme gerekiyor.`)
    sonRet = ret
    await update($, veri, () => o)
  } catch (hata) {
    const mesaj = hata instanceof Error ? hata.message : String(hata)
    await update($, veri, eski => ({ ...(eski ?? { acik: true }), hata: `Veri okunamadı: ${kes(mesaj, 200)}` }))
  } finally {
    calisiyor = false
  }
}

async function webPaneli($: EngineInterface): Promise<string> {
  const betik = `${$.plugin.root}/../orkestra/scripts/orkestra.py`
  const r = await $.process.run(['python', betik, 'panel'], { timeoutMs: 20000 })
  const cikti = (r.stdout || r.stderr).trim()
  return r.exitCode === 0 ? `HTML canlı panel: ${cikti} — tarayıcıda aç (Claude tarayıcı paneli ya da Chrome).`
    : `HTML panel başlatılamadı (${r.exitCode}): ${kes(cikti, 300)}. Terminalde dene: orkestra panel`
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({ name: 'orkestra', description: 'Orkestra panelini aç: görev kartları, denetim, sohbet ve süreç maliyeti, ortak defter' })
    await $.command.register({ name: 'orkestra-web', description: 'Orkestra HTML canlı panelini başlat ve adresini ver (zengin görünüm, tarayıcıda)' })
    await yenile($, true)
    $.clock.every(3000, () => void yenile($, false))
    return next(e)
  })

  on('command.run', { command: 'orkestra' }, async $ => {
    await yenile($, true)
    await update($, bantGizli, () => false)
    await $.ui.open({ id: PANE, title: 'Orkestra' })
    return { text: 'Orkestra paneli açıldı. Daha zengin canlı görünüm için /orkestra-web.' }
  })

  on('command.run', { command: 'orkestra-web' }, async $ => {
    try {
      return { text: await webPaneli($) }
    } catch (hata) {
      return { text: `HTML panel başlatılamadı: ${hata instanceof Error ? hata.message : String(hata)}. Terminalde dene: orkestra panel` }
    }
  })

  on('turn.complete', async ($, e, next) => {
    const sonuc = await next(e)
    await yenile($, true)
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
    if (o.kartlar === undefined) {
      return (
        <Box flexDirection="column">
          <Text color="error">{o.hata ?? 'Veri yok.'}</Text>
        </Box>
      )
    }
    const kartlar: KartOzeti[] = o.kartlar
    const m = o.maliyet
    const surec = Object.entries(m?.surec ?? {}).map(([k, v]) => `${k} ${usd(v)}`).join(' · ')
    const model = Object.entries(m?.model ?? {}).map(([k, v]) => `${k} ${usd(v)}`).join(' · ')
    const ruya = o.ruya?.calisiyor ? 'rüya çalışıyor' : o.ruya?.rapor ? 'rüya raporu hazır → /orkestra:ruya' : o.ruya?.zamani_geldi ? 'rüya zamanı geldi' : ''
    return (
      <Box flexDirection="column">
        {o.hata !== undefined && <Text color="error" wrap="truncate">{o.hata}</Text>}
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
        <Text dimColor>≈ açık sohbet: orkestra defteri; kapanınca Claude'un kendi hesabı. Zengin görünüm: /orkestra-web</Text>
        <Text> </Text>
        <Text bold>Ortak defter (son kayıtlar)</Text>
        {(o.defter ?? []).length === 0 && <Text dimColor>Henüz kayıt yok.</Text>}
        {(o.defter ?? []).map(s => <Text dimColor wrap="truncate">{kes(s, w)}</Text>)}
        {ruya !== '' && <Text> </Text>}
        {ruya !== '' && <Text color="suggestion">{ruya}</Text>}
        {o.uretim !== undefined && <Text dimColor>veri: {o.uretim.slice(11, 19)}</Text>}
      </Box>
    )
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const o = await read($, veri)
    if (e.props.hasSurvey || o === null || !o.acik || o.kartlar === undefined || (await read($, bantGizli))) return next(e)
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
