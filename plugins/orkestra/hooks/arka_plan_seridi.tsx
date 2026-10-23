// Orkestra arka plan şeridi: istem kutusunun üstünde bu sohbetin arka plan görevlerinin sayısını gösterir.
// Neden: arka plan görevleri yalnız Orkestra panelinde görünüyordu; sohbetten bakan kullanıcı ne sürdüğünü göremiyordu.
// Kaynak: tur sonunda motorun verdiği background_tasks listesi yetkilidir; tur içinde başlayan görevler geçici eklenir.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { ArkaPlanGorevi } from '../types'

const gorevler = atom({ plugin: 'orkestra', key: 'arkaPlanGorevleri' } as const, [] as ArkaPlanGorevi[])

const kisalt = (s: string) => (s.length > 70 ? `${s.slice(0, 67)}...` : s)

type HamIs = { biten?: number; toplam?: number; oturumlar?: string[] }

// Yalnız bu oturuma bağlı işlerin todo'ları sayılır; oturum bilgisi ya da ozet.json yoksa 0/0.
export function todoSayimi(isler: HamIs[] | undefined, oturum: string): { biten: number; toplam: number } {
  const benim = (isler ?? []).filter(x => x.oturumlar?.includes(oturum) === true)

  return {
    biten: benim.reduce((a, x) => a + (x.biten ?? 0), 0),
    toplam: benim.reduce((a, x) => a + (x.toplam ?? 0), 0),
  }
}

async function sohbetTodosu($: EngineInterface): Promise<{ biten: number; toplam: number }> {
  try {
    const ham = JSON.parse(await $.fs.read('.claude/orkestra/ozet.json')) as { isler?: HamIs[] }

    return todoSayimi(ham.isler, await $.session.id())
  } catch {
    return { biten: 0, toplam: 0 }
  }
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

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const liste = await read($, gorevler)

    if (e.props.hasSurvey || liste.length === 0) {
      return next(e)
    }

    const { Text } = $.ui.resolve(e)
    const { biten, toplam } = await sohbetTodosu($)

    return <Text dimColor>{biten}/{toplam} yapıldı · Arka plan görevleri sürüyor · {liste.length}</Text>
  })
}
