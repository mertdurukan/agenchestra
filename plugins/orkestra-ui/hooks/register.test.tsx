import { expect, test } from 'claude-code/testing'
import type { On } from 'claude-code'

import type { UiOzet } from '../types'

const ORNEK: UiOzet = {
  acik: true,
  kartlar: [
    { id: 'G-001', baslik: 'README satırı', durum: 'onaylandi', basamak: 'T1', isci: 1, denetim: 'onay', usd: 0.01 },
    { id: 'G-002', baslik: 'Kod taraması', durum: 'reddedildi', basamak: 'T2', isci: 1, denetim: 'ret', usd: 0.2 },
  ],
  sayac: { onaylandi: 1, reddedildi: 1 },
  maliyet: { bugun: 1.5, oturum: 0.42, surec: { is: 0.3, denetim: 0.12 }, model: { 'sonnet-5-5': 0.3 } },
  defter: ['10:00 G-001 is · orkestra:isci-t1: README satırı eklendi'],
  ruya: { zamani_geldi: false, rapor: true, calisiyor: false },
}

const PANE_PROPS = {
  title: 'Orkestra', isFocused: false, bodyColumns: 100, placement: 'dock' as const,
  scroll: { offset: 0, bodyRows: 40 }, view: {},
}
const BANT_PROPS = { hasSurvey: false, isWorking: false, maxRows: 5, bodyColumns: 100, scroll: { offset: 0, bodyRows: 5 }, view: {} }

// Test ortamında süreç ve dosya sistemi yok: modun çağırdığı `orkestra ui-ozet` çıktısını ve dosya imzasını taklit et.
function sahte(on: On, deger: UiOzet, argv: string[][]) {
  on('process.run', ($, e) => {
    argv.push([...e.argv])
    return { value: { exitCode: 0, stdout: JSON.stringify(deger), stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('fs.stat', () => ({ value: { kind: 'file' as const, size: 1, mtimeMs: 1, isLink: false } }))
  on('session.id', () => ({ value: 'test-oturum' }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.render', () => ({ type: 'Box', props: {}, children: [] }))  // motorun kendi (boş) çizimi
}

function metin(agac: unknown): string {
  return JSON.stringify(agac)
}

for (const surface of ['terminal', 'desktop'] as const) {
  test(`/orkestra veriyi çeker ve panel kartları, maliyeti, defteri çizer (${surface})`, async ($, on) => {
    const argv: string[][] = []
    sahte(on, ORNEK, argv)
    await $.command.run({ command: 'orkestra', args: '' })
    expect(argv.length).toBeGreaterThan(0)
    expect(argv[0]?.slice(-3)).toEqual(['ui-ozet', '--oturum', 'test-oturum'])
    const ui = await $.ui.mount({ plugin: 'orkestra-ui', surface, component: 'Pane', requestId: 'orkestra', props: PANE_PROPS })
    const t = metin(await ui.drawn())
    for (const parca of ['G-001', 'reddedildi', 'Bu oturum ', '$0.42', 'rüya raporu hazır', 'README satırı eklendi']) {
      expect(t).toContain(parca)
    }
  })

  test(`kapalı projede bilgilendirir (${surface})`, async ($, on) => {
    sahte(on, { acik: false }, [])
    await $.command.run({ command: 'orkestra', args: '' })
    const ui = await $.ui.mount({ plugin: 'orkestra-ui', surface, component: 'Pane', requestId: 'orkestra', props: PANE_PROPS })
    expect(metin(await ui.drawn())).toContain('orkestra kapalı')
  })

  test(`bant özet satırı gösterir, Gizle ile kaybolur (${surface})`, async ($, on) => {
    sahte(on, ORNEK, [])
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
