/** Portuguese labels for status values the backend returns in English. */
export const RECORDING_STATUS: Record<string, string> = {
  imported: "importada",
  analyzing: "analisando",
  analyzed: "analisada",
  error: "com erro",
};

export const RUN_STATUS: Record<string, string> = {
  running: "em andamento",
  done: "concluída",
  error: "com erro",
  cancelled: "cancelada",
};

export const LEVEL_LABEL: Record<string, string> = {
  leve: "Leve",
  padrao: "Padrão",
  detalhado: "Detalhado",
  completo: "Completo",
};

export function labelOf(map: Record<string, string>, key: string): string {
  return map[key] ?? key;
}
