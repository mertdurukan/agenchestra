export type KartOzeti = {
  id: string
  baslik: string
  durum: string
  basamak: string
  isci: number
  denetim: string
  usd: number
}

export type DefterSatiri = { saat: string; gorev: string; metin: string }

// Panelin gösterdiği, bu oturumun gözünden veri.
export type UiOzet = {
  acik: boolean
  hata?: string
  uretim?: string
  kartlar?: KartOzeti[]
  sayac?: Record<string, number>
  maliyet?: { bugun: number; oturum: number }
  // Eylem bekleyen kartlar (reddedildi/onaylandi) "durum:id" olarak sıralı; bant durum imzası bundan kurulur.
  eylem?: string[]
  // Teslim edilmiş kartlar yalnız sayı olarak; son teslim "açık iş yok" satırı için.
  teslim?: { sayi: number; sonId?: string; sonSaat?: string }
  defter?: DefterSatiri[]  // olay olmayan, temiz son 3 satır
  ruya?: { zamani_geldi: boolean; rapor: boolean; calisiyor: boolean }
}

// Çekirdeğin yazdığı ham anlık görüntü (.claude/orkestra/ozet.json, surum 2).
export type HamOzet = {
  surum: number
  acik: boolean
  uretim: string
  proje: string
  kartlar?: (KartOzeti & { oturum?: string; bagimli?: string[]; guncelleme?: string })[]
  sayac?: Record<string, number>
  maliyet?: {
    bugun: number
    toplam: number
    surec: Record<string, number>
    model: Record<string, number>
    oturumlar?: Record<string, { usd: number; surec: Record<string, number>; model: Record<string, number> }>
  }
  sohbetler?: { oturum: string; baslik: string; usd: number; kaynak: 'motor' | 'defter'; son: string }[]
  defter?: { zaman?: string; gorev: string; surec: string; ajan: string; metin: string; oturum?: string | null; olay?: boolean }[]
  ruya?: { zamani_geldi: boolean; rapor: boolean; calisiyor: boolean }
}

declare module 'claude-code' {
  interface PluginState {
    'orkestra-ui': { veri: UiOzet | null; bantGizli: string }
  }
}
