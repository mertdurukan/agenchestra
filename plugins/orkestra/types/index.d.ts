export type ArkaPlanGorevi = { id: string; kind: string; label: string }

declare module 'claude-code' {
  interface PluginState {
    orkestra: { arkaPlanGorevleri: ArkaPlanGorevi[]; bantSurumu: number }
  }
}
