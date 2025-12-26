<template>
  <div class="chart-wrap">
    <v-chart class="chart" :option="option" autoresize />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { KlinePoint } from '../lib/api'

import VChart from 'vue-echarts'
import * as echarts from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, CandlestickChart, LineChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
  DataZoomComponent,
  AxisPointerComponent,
} from 'echarts/components'

echarts.use([
  CanvasRenderer,
  CandlestickChart,
  LineChart,
  BarChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  DataZoomComponent,
  AxisPointerComponent,
])

defineOptions({ name: 'KlineMultiPanel' })

const props = defineProps<{
  daily: KlinePoint[]
  weekly: KlinePoint[]
  // 初始展示窗口：最后 N 根日K（≈ 3 个月交易日 ~ 60）
  initialDailyCandles?: number
}>()

function n(v: unknown): number | null {
  if (v === null || v === undefined) return null
  const x = Number(v)
  return Number.isFinite(x) ? x : null
}

const option = computed(() => {
  const daily = props.daily ?? []
  const weekly = props.weekly ?? []
  const x = daily.map((d) => d.trade_date)

  const dailyOhlc = daily.map((d) => [n(d.open), n(d.close), n(d.low), n(d.high)])
  const dailyVol = daily.map((d) => n(d.volume))
  const dif = daily.map((d) => n(d.macd_dif))
  const dea = daily.map((d) => n(d.macd_dea))
  const hist = daily.map((d) => n(d.macd_hist))
  const k = daily.map((d) => n(d.kdj_k))
  const d2 = daily.map((d) => n(d.kdj_d))
  const j = daily.map((d) => n(d.kdj_j))
  const stl = daily.map((d) => n(d.short_trend_line))
  const bbl = daily.map((d) => n(d.bull_bear_line))

  // 周K：对齐到日K的 x 轴（仅在周K的 trade_date 对应那天画一根，其余置 null）
  const wkMap = new Map<string, KlinePoint>()
  for (const w of weekly) wkMap.set(w.trade_date, w)
  const weeklyOhlc = x.map((td) => {
    const w = wkMap.get(td)
    if (!w) return [null, null, null, null]
    return [n(w.open), n(w.close), n(w.low), n(w.high)]
  })

  const initialN = props.initialDailyCandles ?? 60
  const total = x.length
  const startPct = total > 0 ? Math.max(0, ((total - initialN) / total) * 100) : 0

  return {
    animation: false,
    backgroundColor: '#0b1220',
    textStyle: { color: '#cbd5e1', fontFamily: 'system-ui, -apple-system, Segoe UI, Roboto, sans-serif' },
    axisPointer: { link: [{ xAxisIndex: [0, 1, 2, 3] }] },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      backgroundColor: 'rgba(15, 23, 42, 0.92)',
      borderColor: '#334155',
      textStyle: { color: '#e2e8f0' },
    },
    grid: [
      { left: 60, right: 20, top: 10, height: '50%' }, // main
      { left: 60, right: 20, top: '62%', height: '10%' }, // vol
      { left: 60, right: 20, top: '74%', height: '12%' }, // macd
      { left: 60, right: 20, top: '88%', height: '10%' }, // kdj
    ],
    xAxis: [
      { type: 'category', data: x, gridIndex: 0, boundaryGap: false, axisLine: { lineStyle: { color: '#334155' } } },
      { type: 'category', data: x, gridIndex: 1, boundaryGap: false, axisLabel: { show: false }, axisLine: { lineStyle: { color: '#334155' } } },
      { type: 'category', data: x, gridIndex: 2, boundaryGap: false, axisLabel: { show: false }, axisLine: { lineStyle: { color: '#334155' } } },
      { type: 'category', data: x, gridIndex: 3, boundaryGap: false, axisLabel: { show: true }, axisLine: { lineStyle: { color: '#334155' } } },
    ],
    yAxis: [
      { scale: true, gridIndex: 0, axisLine: { lineStyle: { color: '#334155' } }, splitLine: { lineStyle: { color: 'rgba(51,65,85,0.35)' } } },
      { scale: true, gridIndex: 1, axisLine: { lineStyle: { color: '#334155' } }, splitLine: { show: false } },
      { scale: true, gridIndex: 2, axisLine: { lineStyle: { color: '#334155' } }, splitLine: { lineStyle: { color: 'rgba(51,65,85,0.25)' } } },
      { scale: true, gridIndex: 3, axisLine: { lineStyle: { color: '#334155' } }, splitLine: { lineStyle: { color: 'rgba(51,65,85,0.25)' } } },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1, 2, 3], start: startPct, end: 100 },
      { type: 'slider', xAxisIndex: [0, 1, 2, 3], start: startPct, end: 100, height: 18, bottom: 0 },
    ],
    series: [
      // 主图：日K
      {
        name: '日K',
        type: 'candlestick',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: dailyOhlc,
        itemStyle: {
          color: '#ef4444',
          color0: '#22c55e',
          borderColor: '#ef4444',
          borderColor0: '#22c55e',
        },
      },
      // 主图：周K（叠加，较透明）
      {
        name: '周K',
        type: 'candlestick',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: weeklyOhlc,
        itemStyle: {
          color: 'rgba(248, 113, 113, 0.35)',
          color0: 'rgba(34, 197, 94, 0.35)',
          borderColor: 'rgba(248, 113, 113, 0.35)',
          borderColor0: 'rgba(34, 197, 94, 0.35)',
        },
      },
      // 主图：短期趋势线、知行多空线
      { name: '短期趋势线', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: stl, showSymbol: false, smooth: true, lineStyle: { width: 1, color: '#60a5fa' } },
      { name: '知行多空线', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: bbl, showSymbol: false, smooth: true, lineStyle: { width: 1, color: '#f59e0b' } },
      // VOL
      { name: 'VOL', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: dailyVol, barWidth: '60%', itemStyle: { color: 'rgba(148,163,184,0.6)' } },
      // MACD
      { name: 'DIF', type: 'line', xAxisIndex: 2, yAxisIndex: 2, data: dif, showSymbol: false, smooth: true, lineStyle: { width: 1, color: '#a78bfa' } },
      { name: 'DEA', type: 'line', xAxisIndex: 2, yAxisIndex: 2, data: dea, showSymbol: false, smooth: true, lineStyle: { width: 1, color: '#f472b6' } },
      { name: 'HIST', type: 'bar', xAxisIndex: 2, yAxisIndex: 2, data: hist, barWidth: '60%', itemStyle: { color: (p: any) => (Number(p.value) >= 0 ? 'rgba(239,68,68,0.55)' : 'rgba(34,197,94,0.55)') } },
      // KDJ
      { name: 'K', type: 'line', xAxisIndex: 3, yAxisIndex: 3, data: k, showSymbol: false, smooth: true, lineStyle: { width: 1, color: '#22c55e' } },
      { name: 'D', type: 'line', xAxisIndex: 3, yAxisIndex: 3, data: d2, showSymbol: false, smooth: true, lineStyle: { width: 1, color: '#60a5fa' } },
      { name: 'J', type: 'line', xAxisIndex: 3, yAxisIndex: 3, data: j, showSymbol: false, smooth: true, lineStyle: { width: 1, color: '#f59e0b' } },
    ],
  }
})
</script>

<style scoped>
.chart-wrap {
  width: 100%;
  height: 100%;
  min-height: 520px;
}
.chart {
  width: 100%;
  height: 100%;
}
</style>

