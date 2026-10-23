// Orkestra bandı: istem kutusunun üstünde tur ya da arka plan görevi sürerken "N/M yapıldı · işlem devam ediyor" yazar.
// Neden: bant yalnız arka plan görevi varken çiziliyordu, ön planda süren tur bandı açmıyordu (ADR-0073).
// Sayaç: oturumun görev listesi (TodoWrite ve update_plan çağrıları), $.session.messages() kayıtlarından hesaplanır.
// tool.call olayı yalnız anında tazeleme içindir; olay gelmese de kayıtlardan sayaç doğru çıkar.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, SessionMessage } from 'claude-code'

import type { ArkaPlanGorevi } from '../types'

const gorevler = atom({ plugin: 'orkestra', key: 'arkaPlanGorevleri' } as const, [] as ArkaPlanGorevi[])
const surum = atom({ plugin: 'orkestra', key: 'bantSurumu' } as const, 0)

const kisalt = (s: string) => (s.length > 70 ? `${s.slice(0, 67)}...` : s)

export type Gorev = { durum: string }
export type PlanCagri = { tool: string; input: Record<string, unknown> }

const PLAN_ARACI = 'mcp__ccd_turn__update_plan'
const WRAP_ARACI = 'mcp__ccd_turn__wrap_up'
const YENILEME_MS = 2000

const dizi = (x: unknown): unknown[] => (Array.isArray(x) ? x : [])

const gorevlere = (x: unknown): Gorev[] =>
  dizi(x).map(g => ({ durum: typeof (g as { status?: unknown })?.status === 'string' ? (g as { status: string }).status : 'pending' }))

// Bir görev listesi çağrısını listeye uygular: items listeyi değiştirir; advance, done ve start 1 tabanlı sıra ile çalışır.
export function planUygula(liste: Gorev[], cagri: PlanCagri): Gorev[] {
  if (cagri.tool === 'TodoWrite') {
    return gorevlere(cagri.input.todos)
  }

  if (cagri.tool === WRAP_ARACI) {
    return liste.map(() => ({ durum: 'completed' }))
  }

  if (cagri.tool !== PLAN_ARACI) {
    return liste
  }

  const yeni = Array.isArray(cagri.input.items) ? gorevlere(cagri.input.items) : liste.map(g => ({ ...g }))

  for (const n of dizi(cagri.input.done)) {
    if (typeof n === 'number' && yeni[n - 1]) {
      yeni[n - 1] = { durum: 'completed' }
    }
  }

  if (cagri.input.advance === true) {
    const i = yeni.findIndex(g => g.durum === 'in_progress')

    if (i >= 0) {
      yeni[i] = { durum: 'completed' }
    }

    const siradaki = yeni.findIndex(g => g.durum === 'pending')

    if (siradaki >= 0) {
      yeni[siradaki] = { durum: 'in_progress' }
    }
  }

  if (typeof cagri.input.start === 'number' && yeni[cagri.input.start - 1]) {
    yeni[cagri.input.start - 1] = { durum: 'in_progress' }
  }

  return yeni
}

const tamamiBitti = (liste: Gorev[]) => liste.length > 0 && liste.every(g => g.durum === 'completed')

// Ana sohbetin kayıtlarını sırayla oynatır; yeni kullanıcı isteğinde tamamı bitmiş liste temizlenir (eski "5/5" yanıltmasın).
export function listeyiKayittanCikar(mesajlar: readonly SessionMessage[]): Gorev[] {
  let liste: Gorev[] = []

  for (const m of mesajlar) {
    if (m.role === 'user' && m.text !== '' && tamamiBitti(liste)) {
      liste = []
    }

    for (const u of m.toolUses ?? []) {
      liste = planUygula(liste, { tool: u.tool, input: u.input })
    }
  }

  return liste
}

export function bantMetni(liste: Gorev[], arka: number): string {
  const sayac = liste.length > 0 ? `${liste.filter(g => g.durum === 'completed').length}/${liste.length} yapıldı · ` : ''
  const arkaMetin = arka > 0 ? ` · arka plan ${arka}` : ''

  return `${sayac}işlem devam ediyor${arkaMetin}`
}

// Modül düzeyi durum: liste kayıttan ya da olaydan gelir, sonYenileme kayıt okumasını 2 sn'de bire düşürür.
const ic = { liste: [] as Gorev[], sonYenileme: 0 }

async function yenile($: EngineInterface) {
  ic.sonYenileme = Date.now()

  try {
    ic.liste = listeyiKayittanCikar(await $.session.messages())
  } catch {
    // Kayıt okunamazsa mevcut liste kalır; bant en kötü "işlem devam ediyor" yazar.
  }
}

async function cagriOlayi($: EngineInterface, e: { tool: string; input?: Record<string, unknown>; agentId?: string }) {
  if (e.agentId !== undefined) {
    return
  }

  ic.liste = planUygula(ic.liste, { tool: e.tool, input: e.input ?? {} })
  ic.sonYenileme = Date.now()
  await update($, surum, n => n + 1)
}

export const register: Register = on => {
  let sira = 0

  const gecici = (tur: string, metin: string): ArkaPlanGorevi => {
    sira += 1

    return { id: `gecici-${sira}`, kind: tur, label: kisalt(metin) }
  }

  const motordan = (liste: { id: string; type: string; description: string; command?: string }[] | undefined): ArkaPlanGorevi[] =>
    (liste ?? []).map(t => ({ id: t.id, kind: t.type, label: kisalt(t.description || t.command || t.type) }))

  on('classic.Stop', async ($, e, next) => {
    await update($, gorevler, () => motordan(e.background_tasks))

    return next(e)
  }).catch(($, e, next) => next(e))

  on('classic.SubagentStop', async ($, e, next) => {
    await update($, gorevler, () => motordan(e.background_tasks))

    return next(e)
  }).catch(($, e, next) => next(e))

  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    if (e.run_in_background) {
      await update($, gorevler, liste => [...liste, gecici('shell', e.description || e.command)])
    }

    return next(e)
  }).catch(($, e, next) => next(e))

  on('tool.call', { tool: 'PowerShell' }, async ($, e, next) => {
    if (e.run_in_background) {
      await update($, gorevler, liste => [...liste, gecici('shell', e.description || e.command)])
    }

    return next(e)
  }).catch(($, e, next) => next(e))

  on('agent.spawn', async ($, e, next) => {
    if (e.background) {
      await update($, gorevler, liste => [...liste, gecici('subagent', e.description)])
    }

    return next(e)
  }).catch(($, e, next) => next(e))

  on('tool.call', { tool: 'TodoWrite' }, async ($, e, next) => {
    await cagriOlayi($, e as never)

    return next(e)
  }).catch(($, e, next) => next(e))

  on('tool.call', { tool: PLAN_ARACI }, async ($, e, next) => {
    await cagriOlayi($, e as never)

    return next(e)
  }).catch(($, e, next) => next(e))

  on('tool.call', { tool: WRAP_ARACI }, async ($, e, next) => {
    await cagriOlayi($, e as never)

    return next(e)
  }).catch(($, e, next) => next(e))

  on('turn.start', async ($, e, next) => {
    if (e.agentId === undefined) {
      ic.sonYenileme = 0
      await update($, surum, n => n + 1)
    }

    return next(e)
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const arka = (await read($, gorevler)).length

    await read($, surum)

    if (e.props.hasSurvey || (!e.props.isWorking && arka === 0)) {
      return next(e)
    }

    if (Date.now() - sonYenileme >= YENILEME_MS) {
      await yenile($)
    }

    const { Text } = $.ui.resolve(e)

    return <Text dimColor>{bantMetni(liste, arka)}</Text>
  })
}
