import { expect, test } from 'claude-code/testing'

import { bantMetni, listeyiKayittanCikar, planUygula } from './arka_plan_seridi'

const GOREV = { id: 't1', type: 'shell', description: 'Uzun ölçüm', status: 'running' }
const PLAN = 'mcp__ccd_turn__update_plan'
const WRAP = 'mcp__ccd_turn__wrap_up'

const liste = (...d: string[]) => d.map(durum => ({ durum }))
const items = (...d: string[]) => ({ items: d.map((status, i) => ({ content: `adim ${i + 1}`, status })) })
const asistan = (...toolUses: { tool: string; input: Record<string, unknown> }[]) =>
  ({ role: 'assistant', text: '', toolUses: toolUses.map((t, i) => ({ tool_use_id: `u${i}`, ...t })) }) as never
const kullanici = (text: string) => ({ role: 'user', text, toolUses: [] }) as never

async function cizim($: Parameters<Parameters<typeof test>[1]>[0], props: Record<string, unknown>, gorevler: (typeof GOREV)[] = []) {
  await $.classic.Stop({ stop_hook_active: false, background_tasks: gorevler } as never)

  try {
    const m = await $.ui.mount({
      plugin: 'orkestra',
      surface: 'terminal',
      component: 'AbovePrompt',
      props: { hasSurvey: false, isWorking: false, maxRows: 5, bodyColumns: 80, ...props } as never,
    })

    return JSON.stringify(await m.drawn())
  } catch {
    // Bant çizmeyip next(e) dediğinde altında motor çizimi yoktur; testte bu "çizilmedi" demektir.
    return ''
  }
}

test('ön plan tur sürerken arka plan görevi olmasa da bant çizilir', async ($, on) => {
  on('classic.Stop', () => ({}))
  const metin = await cizim($, { isWorking: true })
  expect(metin).toContain('işlem devam ediyor')
  expect(metin).not.toContain('arka plan')
})

test('arka plan görevi varken bant görev sayısını da yazar', async ($, on) => {
  on('classic.Stop', () => ({}))
  const metin = await cizim($, { isWorking: false }, [GOREV, { ...GOREV, id: 't2' }])
  expect(metin).toContain('işlem devam ediyor')
  expect(metin).toContain('arka plan 2')
})

test('tur yok ve arka plan görevi yokken bant çizilmez', async ($, on) => {
  on('classic.Stop', () => ({}))
  const metin = await cizim($, { isWorking: false })
  expect(metin).not.toContain('işlem devam ediyor')
})

test('anket açıkken bant çizilmez', async ($, on) => {
  on('classic.Stop', () => ({}))
  const metin = await cizim($, { isWorking: true, hasSurvey: true })
  expect(metin).not.toContain('işlem devam ediyor')
})

test('bant metni: sayaç yoksa yalnız işlem devam ediyor; varsa N/M ve arka plan', () => {
  expect(bantMetni([], 0)).toBe('işlem devam ediyor')
  expect(bantMetni(liste('completed', 'in_progress', 'pending'), 0)).toBe('1/3 yapıldı · işlem devam ediyor')
  expect(bantMetni(liste('completed'), 2)).toBe('1/1 yapıldı · işlem devam ediyor · arka plan 2')
})

test('planUygula: items listeyi baştan kurar', () => {
  const yeni = planUygula([], { tool: PLAN, input: items('in_progress', 'pending', 'pending') })
  expect(yeni).toEqual(liste('in_progress', 'pending', 'pending'))
})

test('planUygula: advance biteni kapatır, sıradakini başlatır', () => {
  const yeni = planUygula(liste('in_progress', 'pending', 'pending'), { tool: PLAN, input: { advance: true } })
  expect(yeni).toEqual(liste('completed', 'in_progress', 'pending'))
})

test('planUygula: done ve start 1 tabanlı sıra ile çalışır', () => {
  const yeni = planUygula(liste('pending', 'pending', 'pending', 'pending'), { tool: PLAN, input: { done: [1, 2], start: 4 } })
  expect(yeni).toEqual(liste('completed', 'completed', 'pending', 'in_progress'))
})

test('planUygula: advance sonrası son madde bitince hepsi tamamlanmış kalır', () => {
  const yeni = planUygula(liste('completed', 'in_progress'), { tool: PLAN, input: { advance: true } })
  expect(yeni).toEqual(liste('completed', 'completed'))
})

test('planUygula: wrap_up hepsini tamamlar, boş listede boş kalır', () => {
  expect(planUygula(liste('in_progress', 'pending'), { tool: WRAP, input: {} })).toEqual(liste('completed', 'completed'))
  expect(planUygula([], { tool: WRAP, input: {} })).toEqual([])
})

test('planUygula: TodoWrite todos listesini alır; ilgisiz araç listeyi değiştirmez', () => {
  const todos = [
    { content: 'a', status: 'completed', activeForm: 'a' },
    { content: 'b', status: 'in_progress', activeForm: 'b' },
  ]
  expect(planUygula([], { tool: 'TodoWrite', input: { todos } })).toEqual(liste('completed', 'in_progress'))
  expect(planUygula(liste('pending'), { tool: 'Read', input: {} })).toEqual(liste('pending'))
})

test('kayıttan çıkarma: çağrılar sırayla uygulanır', () => {
  const kayit = [
    kullanici('başla'),
    asistan({ tool: PLAN, input: items('in_progress', 'pending') }),
    asistan({ tool: PLAN, input: { advance: true } }),
  ]
  expect(listeyiKayittanCikar(kayit)).toEqual(liste('completed', 'in_progress'))
})

test('kayıttan çıkarma: tamamı bitmiş liste yeni kullanıcı isteğinde temizlenir', () => {
  const bitmis = [kullanici('bir'), asistan({ tool: PLAN, input: items('completed', 'completed') })]
  expect(listeyiKayittanCikar(bitmis)).toEqual(liste('completed', 'completed'))
  expect(listeyiKayittanCikar([...bitmis, kullanici('iki')])).toEqual([])
})

test('kayıttan çıkarma: yarım liste yeni kullanıcı isteğinde korunur; araç sonucu satırı temizlemez', () => {
  const yarim = [kullanici('bir'), asistan({ tool: PLAN, input: items('completed', 'pending') })]
  expect(listeyiKayittanCikar([...yarim, kullanici('iki')])).toEqual(liste('completed', 'pending'))

  const bitmis = [kullanici('bir'), asistan({ tool: PLAN, input: items('completed') }), { role: 'user', text: '', toolUses: [] } as never]
  expect(listeyiKayittanCikar(bitmis)).toEqual(liste('completed'))
})

test('olay yolu: update_plan tool.call olayı gelince bant N/M değerini çizer', async ($, on) => {
  on('classic.Stop', () => ({}))
  await $.tool.call({ tool: PLAN, input: items('completed', 'in_progress', 'pending') } as never).catch(() => undefined)
  const metin = await cizim($, { isWorking: true })
  expect(metin).toContain('1/3 yapıldı · işlem devam ediyor')
})

test('olaysız yol: yalnız oturum kaydındaki update_plan çağrısından N/M çıkar', async ($, on) => {
  on('classic.Stop', () => ({}))
  on('session.messages', () => ({
    value: [
      kullanici('başla'),
      asistan({ tool: PLAN, input: items('completed', 'completed', 'in_progress', 'pending') }),
    ],
  }) as never)
  const metin = await cizim($, { isWorking: true })
  expect(metin).toContain('2/4 yapıldı · işlem devam ediyor')
})
