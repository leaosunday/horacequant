// API响应类型定义

export interface ApiResponse<T> {
  code: number
  message: string
  request_id: string | null
  data: T
}

export interface KlinePoint {
  trade_date: string
  open: number | null
  high: number | null
  low: number | null
  close: number | null
  volume: number | null
  amount: number | null
  amplitude: number | null
  pct_change: number | null
  change_amount: number | null
  turnover_rate: number | null
  macd_dif: number | null
  macd_dea: number | null
  macd_hist: number | null
  kdj_k: number | null
  kdj_d: number | null
  kdj_j: number | null
  short_trend_line: number | null
  bull_bear_line: number | null
}

export interface PickBundleItem {
  code: string
  name: string
  exchange: string
  trade_date: string
  rule_name: string
  adjust: string
  market_cap: number | null
  metrics: Record<string, any>
  daily: KlinePoint[]
  weekly: KlinePoint[]
}

export interface PicksBundle {
  rule_name: string
  trade_date: string
  next_cursor: string
  total: number
  items: PickBundleItem[]
}

export interface StreamMeta {
  type: 'meta'
  data: {
    rule_name: string
    trade_date: string
    next_cursor: string
    total: number
    request_id: string | null
  }
}

export interface StreamItem {
  type: 'item'
  data: PickBundleItem
}

export type StreamMessage = StreamMeta | StreamItem

