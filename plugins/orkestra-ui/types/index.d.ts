export type KartOzeti = {
  id: string
  baslik: string
  durum: string
  basamak: string
  isci: number
  denetim: string
  usd: number
}

export type UiOzet = {
  acik: boolean
  kartlar?: KartOzeti[]
  sayac?: Record<string, number>
  maliyet?: { bugun: number; oturum: number; surec: Record<string, number>; model: Record<string, number> }
  defter?: string[]
  sohbetler?: { baslik: string; usd: number; kaynak: 'motor' | 'defter'; bu: boolean; son: string }[]
  ruya?: { zamani_geldi: boolean; rapor: boolean; calisiyor: boolean }
}

declare module 'claude-code' {
  interface PluginState {
    'orkestra-ui': { veri: UiOzet | null; bantGizli: boolean }
  }
}
