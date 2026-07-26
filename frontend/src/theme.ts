// OpenCode 默认主题 ≈ Catppuccin Mocha
// 集中配色，所有组件统一引用本文件，避免散落写死 hex。
// 这是把 RxyCode 前端 UI 换成 opencode 风格的核心依据。
export const C = {
  bg: '#1e1e2e',
  surface0: '#313244',
  surface1: '#45475a',
  surface2: '#585b70',
  overlay2: '#6c7086',
  subtext: '#a6adc8',
  text: '#cdd6f4',
  primary: '#89b4fa', // 蓝
  accent: '#f38ba8',  // 粉红
  mauve: '#cba6f7',
  green: '#a6e3a1',
  yellow: '#f9e2af',
  teal: '#94e2d5',
  sky: '#89dceb',
  red: '#f38ba8',
  border: '#585b70',
  borderDim: '#313244',
} as const;

export type CatColor = (typeof C)[keyof typeof C];
