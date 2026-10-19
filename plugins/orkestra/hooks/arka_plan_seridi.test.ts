import { expect, test } from 'claude-code/testing'

const GOREV = { id: 't1', type: 'shell', description: 'Uzun ölçüm', status: 'running' }
const PROPS = { hasSurvey: false, isWorking: false, maxRows: 5, bodyColumns: 80 } as never

async function cizim($: Parameters<Parameters<typeof test>[1]>[0], gorevler: (typeof GOREV)[]) {
  await $.classic.Stop({ stop_hook_active: false, background_tasks: gorevler } as never)

  try {
    const m = await $.ui.mount({ plugin: 'orkestra', surface: 'terminal', component: 'AbovePrompt', props: PROPS })

    return JSON.stringify(await m.drawn())
  } catch {
    // Şerit çizmeyip next(e) dediğinde altında motor çizimi yoktur; testte bu "çizilmedi" demektir.
    return ''
  }
}

test('görev varken şerit görev sayısını gösterir', async ($, on) => {
  on('classic.Stop', () => ({}))
  const metin = await cizim($, [GOREV, { ...GOREV, id: 't2' }])
  expect(metin).toContain('Arka plan görevleri sürüyor')
  expect(metin).toContain('2')
})

test('görev yokken şerit çizilmez', async ($, on) => {
  on('classic.Stop', () => ({}))
  const metin = await cizim($, [])
  expect(metin).not.toContain('Arka plan görevleri')
})
