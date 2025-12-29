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
  mode?: 'daily' | 'weekly' | 'overlay'
  // 初始展示窗口：最后 N 根 K（默认 60）
  initialCandles?: number
}>()

function n(v: unknown): number | null {
  if (v === null || v === undefined) return null
  const x = Number(v)
  return Number.isFinite(x) ? x : null
}

function lastFinite(arr: Array<number | null>): number | null {
  for (let i = arr.length - 1; i >= 0; i--) {
    const v = arr[i] ?? null
    if (v !== null && Number.isFinite(v)) return v
  }
  return null
}

const option = computed(() => {
  const mode = props.mode ?? 'daily'
  const daily = props.daily ?? []
  const weekly = props.weekly ?? []

  const base = mode === 'weekly' ? weekly : daily
  const x = base.map((d) => d.trade_date)

  const ohlc = base.map((d) => [n(d.open), n(d.close), n(d.low), n(d.high)])
  const vol = base.map((d) => n(d.volume))
  const dif = base.map((d) => n(d.macd_dif))
  const dea = base.map((d) => n(d.macd_dea))
  const hist = base.map((d) => n(d.macd_hist))
  const k = base.map((d) => n(d.kdj_k))
  const d2 = base.map((d) => n(d.kdj_d))
  const j = base.map((d) => n(d.kdj_j))
  const stl = base.map((d) => n(d.short_trend_line))
  const bbl = base.map((d) => n(d.bull_bear_line))

  const stlLast = lastFinite(stl)
  const bblLast = lastFinite(bbl)
  const difLast = lastFinite(dif)
  const deaLast = lastFinite(dea)
  const histLast = lastFinite(hist)
  const kLast = lastFinite(k)
  const dLast = lastFinite(d2)
  const jLast = lastFinite(j)
  const volLast = lastFinite(vol)

  // VOL 柱子按涨跌着色（参考富途）
  const volColor = base.map((d) => {
    const o = n(d.open)
    const c = n(d.close)
    if (o === null || c === null) return 'rgba(148,163,184,0.45)'
    return c >= o ? 'rgba(255,77,79,0.65)' : 'rgba(34,197,94,0.65)'
  })

  // overlay 模式：叠加显示周K（对齐到日K时间轴：仅在周线 trade_date 对应日显示一根）
  const weeklyOhlc = (() => {
    if (mode !== 'overlay') return []
    const dailyX = daily.map((d) => d.trade_date)
    const wkMap = new Map<string, KlinePoint>()
    for (const w of weekly) wkMap.set(w.trade_date, w)
    return dailyX.map((td) => {
      const w = wkMap.get(td)
      if (!w) return [null, null, null, null]
      return [n(w.open), n(w.close), n(w.low), n(w.high)]
    })
  })()

  const initialN = props.initialCandles ?? 60
  const total = x.length
  const startPct = total > 0 ? Math.max(0, ((total - initialN) / total) * 100) : 0

  return {
    animation: false,
    backgroundColor: '#0b0f14',
    textStyle: { color: '#cbd5e1', fontFamily: 'system-ui, -apple-system, Segoe UI, Roboto, sans-serif' },
    axisPointer: { link: [{ xAxisIndex: [0, 1, 2, 3] }] },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      backgroundColor: 'rgba(15, 23, 42, 0.92)',
      borderColor: '#334155',
      textStyle: { color: '#e2e8f0' },
    },
    legend: {
      top: 6,
      left: 60,
      itemWidth: 10,
      itemHeight: 6,
      textStyle: { color: 'rgba(255,255,255,0.75)' },
      selectedMode: false,
    },
    graphic: [
      {
        type: 'group',
        left: 60,
        top: 8,
        silent: true,
        children: [
          {
            type: 'text',
            style: {
              text:
                `ZX  SHORT:${stlLast !== null ? stlLast.toFixed(3) : '--'}   ` +
                `LONG:${bblLast !== null ? bblLast.toFixed(3) : '--'}`,
              fill: 'rgba(255,255,255,0.78)',
              fontSize: 12,
              fontWeight: 600,
            },
          },
        ],
      },
      {
        type: 'text',
        left: 60,
        top: '62%',
        silent: true,
        style: {
          text: `成交量 VOL:${volLast !== null ? volLast.toFixed(3) : '--'}`,
          fill: 'rgba(255,255,255,0.62)',
          fontSize: 12,
          fontWeight: 600,
        },
      },
      {
        type: 'text',
        left: 60,
        top: '74%',
        silent: true,
        style: {
          text:
            `MACD(12,26,9)  DIF:${difLast !== null ? difLast.toFixed(3) : '--'}  ` +
            `DEA:${deaLast !== null ? deaLast.toFixed(3) : '--'}  ` +
            `MACD:${histLast !== null ? histLast.toFixed(3) : '--'}`,
          fill: 'rgba(255,255,255,0.62)',
          fontSize: 12,
          fontWeight: 600,
        },
      },
      {
        type: 'text',
        left: 60,
        top: '88%',
        silent: true,
        style: {
          text:
            `KDJ(9,3,3)  K:${kLast !== null ? kLast.toFixed(3) : '--'}  ` +
            `D:${dLast !== null ? dLast.toFixed(3) : '--'}  ` +
            `J:${jLast !== null ? jLast.toFixed(3) : '--'}`,
          fill: 'rgba(255,255,255,0.62)',
          fontSize: 12,
          fontWeight: 600,
        },
      },
    ],
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
      {
        type: 'inside',
        xAxisIndex: [0, 1, 2, 3],
        start: startPct,
        end: 100,
        // 交互策略（富途风格）：
        // - 双指左右拖动：移动日期窗口
        // - 捏合：缩放
        // - 关闭“滚轮缩放”（避免触控板上下滚动变成缩放）
        zoomOnMouseWheel: false,
        moveOnMouseWheel: true,
        moveOnMouseMove: true,
        preventDefaultMouseMove: true,
      },
    ],
    series: [
      // 主图：日K
      {
        name: mode === 'weekly' ? '周K' : '日K',
        type: 'candlestick',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: ohlc,
        barMaxWidth: 10,
        itemStyle: {
          color: '#ef4444',
          color0: '#22c55e',
          borderColor: '#ef4444',
          borderColor0: '#22c55e',
        },
      },
      // 主图：周K（叠加，较透明）
      {
        name: '周K(叠加)',
        type: 'candlestick',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: weeklyOhlc,
        silent: true,
        barMaxWidth: 10,
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
      {
        name: 'VOL',
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: vol,
        barWidth: '60%',
        itemStyle: { color: (p: any) => volColor[p.dataIndex] ?? 'rgba(148,163,184,0.45)' },
      },
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
  min-height: 0;
}
.chart {
  width: 100%;
  height: 100%;
}
</style>

