export type KartOzeti = {
  id: string
  baslik: string
  durum: string
  basamak: string
  isci: number
  denetim: string
  usd: number
}

export type SohbetOzeti = { baslik: string; usd: number; kaynak: 'motor' | 'defter'; bu: boolean; son: string }

// Panelin gösterdiği, bu oturumun gözünden veri.
export type UiOzet = {
  acik: boolean
  hata?: string
  uretim?: string
  kartlar?: KartOzeti[]
  sayac?: Record<string, number>
  maliyet?: { bugun: number; oturum: number; surec: Record<string, number>; model: Record<string, number> }
  defter?: string[]
  sohbetler?: SohbetOzeti[]
  ruya?: { zamani_geldi: boolean; rapor: boolean; calisiyor: boolean }
}

// Çekirdeğin yazdığı ham anlık görüntü (.claude/orkestra/ozet.json, surum 2).
export type HamOzet = {
  surum: number
  acik: boolean
  uretim: string
  proje: string
  kartlar?: (KartOzeti & { oturum?: string; bagimli?: string[] })[]
  sayac?: Record<string, number>
  maliyet?: {
    bugun: number
    toplam: number
    surec: Record<string, number>
    model: Record<string, number>
    oturumlar?: Record<string, { usd: number; surec: Record<string, number>; model: Record<string, number> }>
  }
  sohbetler?: { oturum: string; baslik: string; usd: number; kaynak: 'motor' | 'defter'; son: string }[]
  defter?: { zaman?: string; gorev: string; surec: string; ajan: string; metin: string }[]
  ruya?: { zamani_geldi: boolean; rapor: boolean; calisiyor: boolean }
}

declare module 'claude-code' {
  interface PluginState {
    'orkestra-ui': { veri: UiOzet | null; bantGizli: boolean }
  }
}
