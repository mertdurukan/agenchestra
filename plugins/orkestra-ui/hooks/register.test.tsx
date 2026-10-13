import { expect, test } from 'claude-code/testing'
import type { On } from 'claude-code'

import type { HamOzet } from '../types'

const BU = 'oturum-bu'

const HAM: HamOzet = {
  surum: 2, acik: true, uretim: '2026-10-13T11:30:05+03:00', proje: 'Ornek',
  kartlar: [
    { id: 'G-001', baslik: 'README satırı', durum: 'onaylandi', basamak: 'T1', isci: 1, denetim: 'onay', usd: 0.01, oturum: BU },
    { id: 'G-002', baslik: 'Kod taraması', durum: 'reddedildi', basamak: 'T2', isci: 1, denetim: 'ret', usd: 0.2, oturum: 'baska' },
    { id: 'G-003', baslik: 'Eski teslim', durum: 'teslim', basamak: 'T1', isci: 1, denetim: 'onay', usd: 0.05, oturum: 'baska' },
  ],
  sayac: { onaylandi: 1, reddedildi: 1 },
  maliyet: {
    bugun: 1.5, toplam: 20,
    surec: { is: 0.3 }, model: { 'sonnet-5-5': 0.3 },
    oturumlar: { [BU]: { usd: 0.42, surec: { is: 0.3, denetim: 0.12 }, model: { 'sonnet-5-5': 0.42 } } },
  },
  sohbetler: [
    { oturum: BU, baslik: 'Orkestrasyon', usd: 39.06, kaynak: 'defter', son: '2026-10-13T10:46+03:00' },
    { oturum: 'baska', baslik: 'Karar Defteri detaylı yapılandırması', usd: 8.21, kaynak: 'motor', son: '2026-10-13T10:40+03:00' },
  ],
  defter: [{ zaman: '2026-10-13T10:00:00+03:00', gorev: 'G-001', surec: 'is', ajan: 'orkestra:isci-t1', metin: 'README satırı eklendi' }],
  ruya: { zamani_geldi: false, rapor: true, calisiyor: false },
}

const PANE_PROPS = {
  title: 'Orkestra', isFocused: false, bodyColumns: 100, placement: 'dock' as const,
  scroll: { offset: 0, bodyRows: 40 }, view: {},
}
const BANT_PROPS = { hasSurvey: false, isWorking: false, maxRows: 5, bodyColumns: 100, scroll: { offset: 0, bodyRows: 5 }, view: {} }

// Test ortamında dosya sistemi yok: ozet.json'u ve oturumu taklit et.
function sahte(on: On, ham: HamOzet | null, argv: string[][] = []) {
  on('fs.stat', () => (ham === null ? { deny: 'yok' } : { value: { kind: 'file' as const, size: 10, mtimeMs: 5, isLink: false } }))
  on('fs.read', () => ({ value: JSON.stringify(ham) }))
  on('fs.exists', () => ({ value: true }))
  on('session.id', () => ({ value: BU }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('process.run', ($, e) => {
    argv.push([...e.argv])
    return { value: { exitCode: 0, stdout: 'http://127.0.0.1:8765/', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('ui.render', () => ({ type: 'Box', props: {}, children: [] }))  // motorun kendi (boş) çizimi
}

const metin = (agac: unknown): string => JSON.stringify(agac)

for (const surface of ['terminal', 'desktop'] as const) {
  test(`ozet.json'u okur, bu oturumun maliyetini ve sohbetleri çizer (${surface})`, async ($, on) => {
    sahte(on, HAM)
    await $.command.run({ command: 'orkestra', args: '' })
    const ui = await $.ui.mount({ plugin: 'orkestra-ui', surface, component: 'Pane', requestId: 'orkestra', props: PANE_PROPS })
    const t = metin(await ui.drawn())
    for (const parca of ['G-001', 'G-002', 'reddedildi', 'Bu oturum ', '$0.42', 'Sohbetler (bu çalışma alanı)', 'Orkestrasyon',
      '$39.06', 'Karar Defteri detaylı yapılandırması', '$8.21', 'README satırı eklendi', 'rüya raporu hazır']) {
      expect(t).toContain(parca)
    }
    expect(t).not.toContain('Eski teslim')  // başka oturumun teslim edilmiş kartı gösterilmez
  })

  test(`ozet.json yoksa nedenini gösterir (${surface})`, async ($, on) => {
    sahte(on, null)
    await $.command.run({ command: 'orkestra', args: '' })
    const ui = await $.ui.mount({ plugin: 'orkestra-ui', surface, component: 'Pane', requestId: 'orkestra', props: PANE_PROPS })
    expect(metin(await ui.drawn())).toContain('ozet.json henüz yok')
  })

  test(`bant özet satırı gösterir, Gizle ile kaybolur (${surface})`, async ($, on) => {
    sahte(on, HAM)
    await $.command.run({ command: 'orkestra', args: '' })
    const ui = await $.ui.mount({ plugin: 'orkestra-ui', surface, component: 'AbovePrompt', props: BANT_PROPS })
    const once = metin(await ui.drawn())
    expect(once).toContain('1 ret')
    expect(once).toContain('teslime hazır')
    await ui.press({ key: 'gizle' })
    const sonra = await ui.drawn().then(metin, () => '')
    expect(sonra).not.toContain('1 ret')
  })
}

test('/orkestra-web HTML paneli başlatır ve adresi verir', async ($, on) => {
  const argv: string[][] = []
  sahte(on, HAM, argv)
  const r = await $.command.run({ command: 'orkestra-web', args: '' })
  expect(argv.some(a => a.includes('panel'))).toBe(true)
  expect(JSON.stringify(r)).toContain('http://127.0.0.1:8765/')
})
