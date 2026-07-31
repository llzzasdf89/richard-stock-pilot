export interface FilterSpecification {
  min: number;
  max: number;
  step: number;
  defaultValue: number;
}

export const MARKET_CAP_SPEC: FilterSpecification = {
  min: 50_000_000_000,
  max: 2_000_000_000_000,
  step: 50_000_000_000,
  defaultValue: 200_000_000_000
};

export const AVG_VOLUME_SPEC: FilterSpecification = {
  min: 1_000_000,
  max: 100_000_000,
  step: 1_000_000,
  defaultValue: 10_000_000
};

export const PUSH_INTERVAL_SPEC: FilterSpecification = {
  min: 10,
  max: 120,
  step: 10,
  defaultValue: 60
};

export function formatLargeMoney(value: number): string {
  if (value >= 1_000_000_000_000) return `${(value / 1_000_000_000_000).toFixed(2)}万亿`;
  if (value >= 100_000_000) return `${(value / 100_000_000).toFixed(0)}亿`;
  return new Intl.NumberFormat("zh-CN").format(value);
}

export function formatVolume(value: number): string {
  if (value >= 100_000_000) return `${(value / 100_000_000).toFixed(1)}亿`;
  if (value >= 10_000) return `${(value / 10_000).toFixed(0)}万`;
  return new Intl.NumberFormat("zh-CN").format(value);
}

export function formatPushInterval(value: number): string {
  return `每 ${value} 分钟`;
}
