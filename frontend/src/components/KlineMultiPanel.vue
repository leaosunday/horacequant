<template>
  <div class="chart-wrap">
    <v-chart ref="chartRef" class="chart" :option="option" autoresize />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
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
  GraphicComponent,
  MarkLineComponent,
  MarkPointComponent,
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
  GraphicComponent,
  MarkLineComponent,
  MarkPointComponent,
])

defineOptions({ name: 'KlineMultiPanel' })

const props = defineProps<{
  daily: KlinePoint[]
  weekly: KlinePoint[]
  mode?: 'daily' | 'weekly' | 'overlay'
  // 初始展示窗口：最后 N 根 K（默认 60）
  initialCandles?: number
}>()

const chartRef = ref<any>(null)
let cleanupGestures: (() => void) | null = null
let cleanupZoomSync: (() => void) | null = null

// 让“最高/最低标注”跟随当前可视窗口（dataZoom）
// 用 NaN 作为“尚未从图表回读过”的哨兵值，避免覆盖默认 startPct
const zoomState = ref<{ start: number; end: number }>({ start: Number.NaN, end: Number.NaN })

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

function lastFiniteIndex(arr: Array<number | null>): number {
  for (let i = arr.length - 1; i >= 0; i--) {
    const v = arr[i] ?? null
    if (v !== null && Number.isFinite(v)) return i
  }
  return -1
}

function prevFiniteIndex(arr: Array<number | null>, from: number): number {
  for (let i = from; i >= 0; i--) {
    const v = arr[i] ?? null
    if (v !== null && Number.isFinite(v)) return i
  }
  return -1
}

function fmtVol(x: number | null): string {
  if (x === null || !Number.isFinite(x)) return '--'
  if (x >= 1e8) return `${(x / 1e8).toFixed(2)}亿`
  if (x >= 1e4) return `${(x / 1e4).toFixed(2)}万`
  return `${x.toFixed(0)}`
}

function weekdayCn(iso: string): string {
  const d = new Date(iso)
  // Safari 对 'YYYY-MM-DD' 解析不稳定，走替换
  const dd = Number.isNaN(d.getTime()) ? new Date(iso.split('-').join('/')) : d
  const map = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六']
  return map[dd.getDay()] ?? ''
}

const option = computed(() => {
  const mode = props.mode ?? 'daily'
  const daily = props.daily ?? []
  const weekly = props.weekly ?? []

  const base = mode === 'weekly' ? weekly : daily
  const x = base.map((d) => d.trade_date)

  const ohlc = base.map((d) => [n(d.open), n(d.close), n(d.low), n(d.high)])
  const vol = base.map((d) => n(d.volume))
  const closeArr = base.map((d) => n(d.close))
  const highArr = base.map((d) => n(d.high))
  const lowArr = base.map((d) => n(d.low))
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

  // 使用当前 zoomState（可视窗口）决定“最高/最低”标注范围
  const z = zoomState.value
  const startP = Number.isFinite(z.start) ? z.start : startPct
  const endP = Number.isFinite(z.end) ? z.end : 100
  const len = x.length
  const i0 = len > 0 ? Math.max(0, Math.floor((startP / 100) * (len - 1))) : 0
  const i1 = len > 0 ? Math.min(len - 1, Math.ceil((endP / 100) * (len - 1))) : -1

  // 主图右侧百分比刻度：以“昨收”为基准（以最后一个有效 close 的前一根 close 为准）
  const lastIdx = lastFiniteIndex(closeArr)
  const prevIdx = lastIdx >= 0 ? prevFiniteIndex(closeArr, lastIdx - 1) : -1
  const lastClose = lastIdx >= 0 ? (closeArr[lastIdx] ?? null) : null
  const refClose = prevIdx >= 0 ? (closeArr[prevIdx] ?? null) : lastClose

  // 最高/最低点（强制标注，避免 ECharts 自动 max/min 在缺失值/缩放下不显示）
  let maxHigh: number | null = null
  let maxIdx = -1
  for (let i = i0; i <= i1; i++) {
    const v = highArr[i] ?? null
    if (v === null || !Number.isFinite(v)) continue
    if (maxHigh === null || v > maxHigh) {
      maxHigh = v
      maxIdx = i
    }
  }
  let minLow: number | null = null
  let minIdx = -1
  for (let i = i0; i <= i1; i++) {
    const v = lowArr[i] ?? null
    if (v === null || !Number.isFinite(v)) continue
    if (minLow === null || v < minLow) {
      minLow = v
      minIdx = i
    }
  }

  // 主图固定 y 轴范围（让右侧百分比轴与价格轴刻度对齐）
  const yMin = minLow !== null && maxHigh !== null ? minLow - (maxHigh - minLow) * 0.06 : null
  const yMax = minLow !== null && maxHigh !== null ? maxHigh + (maxHigh - minLow) * 0.10 : null

  // 极值标注：只显示数字 + 小斜指示线（更像富途）
  const idxMid = Math.floor((i0 + i1) / 2)
  const maxDir = maxIdx > idxMid ? -1 : 1
  const minDir = minIdx > idxMid ? -1 : 1
  const maxIdx2 = Math.max(0, Math.min(x.length - 1, maxIdx + maxDir * 2))
  const minIdx2 = Math.max(0, Math.min(x.length - 1, minIdx + minDir * 2))
  // 预留：用于右侧百分比标签等更像富途的细化
  // const lastPct = refClose !== null && lastClose !== null && refClose !== 0 ? ((lastClose - refClose) / refClose) * 100 : null

  return {
    animation: false,
    backgroundColor: '#0b0f14',
    textStyle: { color: '#cbd5e1', fontFamily: 'system-ui, -apple-system, Segoe UI, Roboto, sans-serif' },
    axisPointer: {
      link: [{ xAxisIndex: [0, 1, 2, 3] }],
      lineStyle: { color: 'rgba(255,255,255,0.35)', type: 'dashed' },
      label: { backgroundColor: 'rgba(15,23,42,0.92)', color: '#e2e8f0' },
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross', lineStyle: { type: 'dashed', color: 'rgba(255,255,255,0.35)' } },
      backgroundColor: 'rgba(15, 23, 42, 0.92)',
      borderColor: 'rgba(255,255,255,0.10)',
      borderWidth: 1,
      padding: [10, 10, 10, 10],
      textStyle: { color: '#e2e8f0', fontSize: 12 },
      extraCssText: 'box-shadow: 0 8px 24px rgba(0,0,0,0.35); border-radius: 8px;',
      formatter: (params: any) => {
        const p = Array.isArray(params) ? params : [params]
        const k = p.find((x: any) => x?.seriesType === 'candlestick' && x?.data) ?? p[0]
        const idx = Number(k?.dataIndex ?? 0)
        const row = base[idx]
        const td = String(row?.trade_date ?? '')
        const o = n(row?.open)
        const h = n(row?.high)
        const l = n(row?.low)
        const c = n(row?.close)
        const prevC = idx > 0 ? n(base[idx - 1]?.close) : null
        const chg = c !== null && prevC !== null ? c - prevC : n(row?.change_amount)
        const pct = c !== null && prevC !== null && prevC !== 0 ? (chg! / prevC) * 100 : n(row?.pct_change)
        const volV = n(row?.volume)
        const amtV = n(row?.amount)
        const tr = n(row?.turnover_rate)

        function clr(v: number | null): string {
          if (v === null || prevC === null) return 'rgba(226,232,240,0.92)'
          if (v > prevC) return '#ff4d4f'
          if (v < prevC) return '#22c55e'
          return 'rgba(226,232,240,0.92)'
        }
        const sChg = chg === null || !Number.isFinite(chg) ? '--' : `${chg > 0 ? '+' : ''}${chg.toFixed(2)}`
        const sPct = pct === null || !Number.isFinite(pct) ? '--' : `${pct > 0 ? '+' : ''}${pct.toFixed(2)}%`

        return `
          <div style="min-width: 220px">
            <div style="color: rgba(255,255,255,0.78); font-weight: 700; margin-bottom: 8px;">
              ${td.split('-').join('/')}&nbsp;&nbsp;${weekdayCn(td)}
            </div>
            <div style="display:grid; grid-template-columns: 84px 1fr; row-gap: 6px; column-gap: 10px;">
              <div style="color: rgba(255,255,255,0.62)">开盘</div><div style="color:${clr(o)}; font-weight:700; text-align:right">${o === null ? '--' : o.toFixed(2)}</div>
              <div style="color: rgba(255,255,255,0.62)">最高</div><div style="color:${clr(h)}; font-weight:700; text-align:right">${h === null ? '--' : h.toFixed(2)}</div>
              <div style="color: rgba(255,255,255,0.62)">最低</div><div style="color:${clr(l)}; font-weight:700; text-align:right">${l === null ? '--' : l.toFixed(2)}</div>
              <div style="color: rgba(255,255,255,0.62)">收盘</div><div style="color:${clr(c)}; font-weight:700; text-align:right">${c === null ? '--' : c.toFixed(2)}</div>
              <div style="color: rgba(255,255,255,0.62)">涨跌额</div><div style="color:${chg !== null && chg > 0 ? '#ff4d4f' : '#22c55e'}; font-weight:700; text-align:right">${sChg}</div>
              <div style="color: rgba(255,255,255,0.62)">涨跌幅</div><div style="color:${pct !== null && pct > 0 ? '#ff4d4f' : '#22c55e'}; font-weight:700; text-align:right">${sPct}</div>
              <div style="color: rgba(255,255,255,0.62)">成交量</div><div style="color: rgba(226,232,240,0.92); font-weight:700; text-align:right">${fmtVol(volV)}</div>
              <div style="color: rgba(255,255,255,0.62)">成交额</div><div style="color: rgba(226,232,240,0.92); font-weight:700; text-align:right">${fmtVol(amtV)}</div>
              <div style="color: rgba(255,255,255,0.62)">换手率</div><div style="color: rgba(226,232,240,0.92); font-weight:700; text-align:right">${tr === null ? '--' : tr.toFixed(3) + '%'}</div>
            </div>
          </div>
        `
      },
    },
    legend: { show: false },
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
              rich: {
                a: { fill: 'rgba(255,255,255,0.78)', fontSize: 12, fontWeight: 700 },
                s: { fill: '#ffffff', fontSize: 12, fontWeight: 800 },
                l: { fill: '#f59e0b', fontSize: 12, fontWeight: 800 },
              },
              text:
                `{a|ZX  }{s|SHORT:${stlLast !== null ? stlLast.toFixed(3) : '--'}}` +
                `   {l|LONG:${bblLast !== null ? bblLast.toFixed(3) : '--'}}`,
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
      // 给顶部 ZX/标题留出空间，避免压住K线
      { left: 60, right: 20, top: 34, height: '46%' }, // main
      { left: 60, right: 20, top: '62%', height: '10%' }, // vol
      { left: 60, right: 20, top: '74%', height: '12%' }, // macd
      { left: 60, right: 20, top: '88%', height: '10%' }, // kdj
    ],
    xAxis: [
      { type: 'category', data: x, gridIndex: 0, boundaryGap: false, axisLabel: { color: '#a8b3c6' }, axisLine: { lineStyle: { color: '#334155' } } },
      { type: 'category', data: x, gridIndex: 1, boundaryGap: false, axisLabel: { show: false, color: '#a8b3c6' }, axisLine: { lineStyle: { color: '#334155' } } },
      { type: 'category', data: x, gridIndex: 2, boundaryGap: false, axisLabel: { show: false, color: '#a8b3c6' }, axisLine: { lineStyle: { color: '#334155' } } },
      { type: 'category', data: x, gridIndex: 3, boundaryGap: false, axisLabel: { show: true, color: '#a8b3c6' }, axisLine: { lineStyle: { color: '#334155' } } },
    ],
    yAxis: [
      // 0: 主图价格轴（左）
      {
        scale: true,
        gridIndex: 0,
        min: yMin ?? undefined,
        max: yMax ?? undefined,
        axisLine: { lineStyle: { color: '#334155' } },
        axisLabel: { color: '#a8b3c6' },
        splitLine: { lineStyle: { color: 'rgba(51,65,85,0.35)' } },
      },
      // 1: 主图百分比轴（右，基于昨收）
      {
        scale: true,
        gridIndex: 0,
        position: 'right',
        min: yMin ?? undefined,
        max: yMax ?? undefined,
        axisLine: { lineStyle: { color: '#334155' } },
        axisLabel: {
          color: '#a8b3c6',
          formatter: (v: number) => {
            if (!refClose || !Number.isFinite(refClose) || refClose === 0) return ''
            const pct = ((v - refClose) / refClose) * 100
            const s = pct > 0 ? '+' : ''
            return `${s}${pct.toFixed(2)}%`
          },
        },
        splitLine: { show: false },
      },
      // 2: VOL
      { scale: true, gridIndex: 1, axisLine: { lineStyle: { color: '#334155' } }, axisLabel: { color: '#a8b3c6' }, splitLine: { show: false } },
      // 3: MACD
      { scale: true, gridIndex: 2, axisLine: { lineStyle: { color: '#334155' } }, axisLabel: { color: '#a8b3c6' }, splitLine: { lineStyle: { color: 'rgba(51,65,85,0.25)' } } },
      // 4: KDJ
      { scale: true, gridIndex: 3, axisLine: { lineStyle: { color: '#334155' } }, axisLabel: { color: '#a8b3c6' }, splitLine: { lineStyle: { color: 'rgba(51,65,85,0.25)' } } },
    ],
    dataZoom: [
      {
        type: 'inside',
        xAxisIndex: [0, 1, 2, 3],
        start: startP,
        end: endP,
        // 交互策略（富途风格）：
        // - 双指左右拖动：移动日期窗口（由自定义 wheel 处理）
        // - 捏合：缩放（由自定义 ctrl+wheel 处理）
        // - 关闭内置 wheel 行为，避免“上下滚动=缩放/平移”
        zoomOnMouseWheel: false,
        moveOnMouseWheel: false,
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
        clip: false,
        itemStyle: {
          // 富途风格：上涨（红）空心
          color: 'rgba(0,0,0,0)',
          color0: '#22c55e',
          borderColor: '#ff4d4f',
          borderColor0: '#22c55e',
        },
        markLine: {
          symbol: 'none',
          silent: true,
          z: 10,
          data: [
            // 极值（数字 + 小斜指示线）
            ...(maxIdx >= 0 && maxHigh !== null && x[maxIdx] && x[maxIdx2] && yMax !== null && yMin !== null
              ? [
                  [
                    { coord: [x[maxIdx], maxHigh], lineStyle: { color: 'rgba(255,255,255,0.55)', width: 1 } },
                    {
                      coord: [x[maxIdx2], maxHigh + (yMax - yMin) * 0.03],
                      lineStyle: { color: 'rgba(255,255,255,0.55)', width: 1 },
                      label: {
                        show: true,
                        position: 'end',
                        color: 'rgba(255,255,255,0.9)',
                        fontWeight: 800,
                        formatter: () => maxHigh.toFixed(2),
                      },
                    },
                  ],
                ]
              : []),
            ...(minIdx >= 0 && minLow !== null && x[minIdx] && x[minIdx2] && yMax !== null && yMin !== null
              ? [
                  [
                    { coord: [x[minIdx], minLow], lineStyle: { color: 'rgba(255,255,255,0.55)', width: 1 } },
                    {
                      coord: [x[minIdx2], minLow - (yMax - yMin) * 0.03],
                      lineStyle: { color: 'rgba(255,255,255,0.55)', width: 1 },
                      label: {
                        show: true,
                        position: 'end',
                        color: 'rgba(255,255,255,0.9)',
                        fontWeight: 800,
                        formatter: () => minLow.toFixed(2),
                      },
                    },
                  ],
                ]
              : []),
            // 昨收参考线（灰虚线）
            ...(refClose
              ? [
                  {
                    yAxis: refClose,
                    lineStyle: { color: 'rgba(255,255,255,0.28)', type: 'dashed', width: 1 },
                    label: { show: false },
                  },
                ]
              : []),
            // 最新价（绿点线 + 左侧价格标签 + 右侧百分比标签）
            ...(lastClose !== null
              ? [
                  {
                    yAxis: lastClose,
                    lineStyle: { color: 'rgba(34,197,94,0.85)', type: 'dotted', width: 1.2 },
                    label: {
                      show: true,
                      position: 'end',
                      color: '#0b0f14',
                      fontWeight: 800,
                      fontSize: 12,
                      padding: [2, 5],
                      backgroundColor: '#22c55e',
                      borderRadius: 4,
                      formatter: () => (typeof lastClose === 'number' ? lastClose.toFixed(2) : ''),
                    },
                  },
                ]
              : []),
          ],
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
          color: 'rgba(0,0,0,0)',
          color0: 'rgba(34, 197, 94, 0.35)',
          borderColor: 'rgba(255, 77, 79, 0.55)',
          borderColor0: 'rgba(34, 197, 94, 0.35)',
        },
      },
      // 主图：短期趋势线、知行多空线
      { name: 'ZX Short', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: stl, showSymbol: false, smooth: true, lineStyle: { width: 1.2, color: '#ffffff' } },
      { name: 'ZX Long', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: bbl, showSymbol: false, smooth: true, lineStyle: { width: 1.2, color: '#f59e0b' } },
      // VOL
      {
        name: 'VOL',
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 2,
        data: vol,
        barWidth: '60%',
        itemStyle: { color: (p: any) => volColor[p.dataIndex] ?? 'rgba(148,163,184,0.45)' },
      },
      // MACD
      { name: 'DIF', type: 'line', xAxisIndex: 2, yAxisIndex: 3, data: dif, showSymbol: false, smooth: true, lineStyle: { width: 1, color: '#a78bfa' } },
      { name: 'DEA', type: 'line', xAxisIndex: 2, yAxisIndex: 3, data: dea, showSymbol: false, smooth: true, lineStyle: { width: 1, color: '#f472b6' } },
      { name: 'HIST', type: 'bar', xAxisIndex: 2, yAxisIndex: 3, data: hist, barWidth: '60%', itemStyle: { color: (p: any) => (Number(p.value) >= 0 ? 'rgba(239,68,68,0.55)' : 'rgba(34,197,94,0.55)') } },
      // KDJ
      { name: 'K', type: 'line', xAxisIndex: 3, yAxisIndex: 4, data: k, showSymbol: false, smooth: true, lineStyle: { width: 1, color: '#22c55e' } },
      { name: 'D', type: 'line', xAxisIndex: 3, yAxisIndex: 4, data: d2, showSymbol: false, smooth: true, lineStyle: { width: 1, color: '#60a5fa' } },
      { name: 'J', type: 'line', xAxisIndex: 3, yAxisIndex: 4, data: j, showSymbol: false, smooth: true, lineStyle: { width: 1, color: '#f59e0b' } },
    ],
  }
})

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v))
}

function getZoom(inst: any): { start: number; end: number } {
  const opt = inst?.getOption?.() ?? {}
  const dz = Array.isArray(opt.dataZoom) ? opt.dataZoom[0] : null
  const start = typeof dz?.start === 'number' ? dz.start : 0
  const end = typeof dz?.end === 'number' ? dz.end : 100
  return { start, end }
}

function setZoom(inst: any, start: number, end: number) {
  inst?.dispatchAction?.({ type: 'dataZoom', start, end })
}

function bindZoomSync() {
  const inst = chartRef.value?.getEchartsInstance?.()
  if (!inst) return

  const onZoom = () => {
    const z = getZoom(inst)
    zoomState.value = { start: z.start, end: z.end }
  }

  // init
  onZoom()
  inst.on?.('datazoom', onZoom)
  cleanupZoomSync = () => {
    inst.off?.('datazoom', onZoom)
  }
}

function bindGestures() {
  const inst = chartRef.value?.getEchartsInstance?.()
  if (!inst) return
  const dom = inst.getDom?.()
  if (!dom) return

  // 解决“PC 触控板捏合不触发/无法 preventDefault”的兼容问题：
  // - 用 window capture 监听 wheel（只在鼠标悬停 chart 时拦截 ctrl/meta）
  // - 避免事件 target 不在 chart dom 上导致监听不到
  let hovered = false
  const onEnter = () => {
    hovered = true
  }
  const onLeave = () => {
    hovered = false
  }
  dom.addEventListener('pointerenter', onEnter)
  dom.addEventListener('pointerleave', onLeave)

  const onWheel = (e: WheelEvent) => {
    // 仅处理：
    // - ctrlKey wheel（触控板捏合/浏览器缩放手势）=> 缩放
    // - horizontal wheel（双指左右）=> 平移日期窗口
    // 其它滚动交给页面（用于下拉加载/滚动列表）
    const { start, end } = getZoom(inst)
    const win = end - start
    if (e.ctrlKey || e.metaKey) {
      // pinch zoom: deltaY<0 通常表示放大（Chrome/Edge）
      e.preventDefault()
      const center = (start + end) / 2
      const factor = Math.exp(-e.deltaY * 0.002)
      const nextWin = clamp(win / factor, 2, 100)
      let ns = center - nextWin / 2
      let ne = center + nextWin / 2
      if (ns < 0) {
        ne -= ns
        ns = 0
      }
      if (ne > 100) {
        ns -= ne - 100
        ne = 100
      }
      ns = clamp(ns, 0, 100)
      ne = clamp(ne, 0, 100)
      if (ne - ns >= 2) setZoom(inst, ns, ne)
      return
    }

    const dx = e.deltaX
    const dy = e.deltaY
    const isHorizontal = Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 0.1
    if (isHorizontal) {
      e.preventDefault()
      // 平移：按窗口宽度比例移动（更符合“拖动日期”感觉）
      const shift = (dx / 600) * win
      let ns = start + shift
      let ne = end + shift
      if (ns < 0) {
        ne -= ns
        ns = 0
      }
      if (ne > 100) {
        ns -= ne - 100
        ne = 100
      }
      ns = clamp(ns, 0, 100)
      ne = clamp(ne, 0, 100)
      setZoom(inst, ns, ne)
    }
  }

  const onWheelCapture = (e: WheelEvent) => {
    if (!hovered) return
    // 仅在图表区域内拦截 pinch / 横向滑动
    if (e.ctrlKey || e.metaKey || Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
      onWheel(e)
    }
  }

  // Safari(尤其 iOS) pinch 可能走 gesture* 事件
  let lastScale = 1
  const onGestureStart = (e: any) => {
    lastScale = e?.scale ?? 1
  }
  const onGestureChange = (e: any) => {
    if (typeof e?.scale !== 'number') return
    e.preventDefault?.()
    const { start, end } = getZoom(inst)
    const win = end - start
    const center = (start + end) / 2
    const factor = e.scale / lastScale
    lastScale = e.scale
    const nextWin = clamp(win / factor, 2, 100)
    let ns = center - nextWin / 2
    let ne = center + nextWin / 2
    if (ns < 0) {
      ne -= ns
      ns = 0
    }
    if (ne > 100) {
      ns -= ne - 100
      ne = 100
    }
    setZoom(inst, clamp(ns, 0, 100), clamp(ne, 0, 100))
  }

  // 触摸双指：pinch 缩放 + 横向平移（移动日期）
  let tActive = false
  let tStartDist = 0
  let tStartMidX = 0
  let tStartZoom: { start: number; end: number } | null = null

  const dist = (a: Touch, b: Touch) => Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY)
  const midX = (a: Touch, b: Touch) => (a.clientX + b.clientX) / 2

  const onTouchStart = (e: TouchEvent) => {
    if (e.touches.length === 2) {
      const a = e.touches[0]
      const b = e.touches[1]
      if (!a || !b) return
      tActive = true
      tStartDist = dist(a, b)
      tStartMidX = midX(a, b)
      tStartZoom = getZoom(inst)
    }
  }

  const onTouchMove = (e: TouchEvent) => {
    if (!tActive || e.touches.length !== 2 || !tStartZoom) return
    const a = e.touches[0]
    const b = e.touches[1]
    if (!a || !b) return
    e.preventDefault()

    const nowDist = dist(a, b)
    const nowMidX = midX(a, b)

    const { start, end } = tStartZoom
    const win0 = end - start
    const center0 = (start + end) / 2

    // pinch 缩放
    const scale = nowDist / (tStartDist || nowDist || 1)
    const nextWin = clamp(win0 / scale, 2, 100)
    let ns = center0 - nextWin / 2
    let ne = center0 + nextWin / 2

    // 双指横向平移：midX 位移映射到百分比窗口移动
    const dx = nowMidX - tStartMidX
    const shift = (-dx / 600) * nextWin
    ns += shift
    ne += shift

    if (ns < 0) {
      ne -= ns
      ns = 0
    }
    if (ne > 100) {
      ns -= ne - 100
      ne = 100
    }
    setZoom(inst, clamp(ns, 0, 100), clamp(ne, 0, 100))
  }

  const onTouchEnd = (e: TouchEvent) => {
    if (e.touches.length < 2) {
      tActive = false
      tStartZoom = null
    }
  }

  dom.addEventListener('wheel', onWheel, { passive: false })
  dom.addEventListener('gesturestart', onGestureStart as any, { passive: false } as any)
  dom.addEventListener('gesturechange', onGestureChange as any, { passive: false } as any)
  dom.addEventListener('touchstart', onTouchStart as any, { passive: false } as any)
  dom.addEventListener('touchmove', onTouchMove as any, { passive: false } as any)
  dom.addEventListener('touchend', onTouchEnd as any, { passive: false } as any)
  dom.addEventListener('touchcancel', onTouchEnd as any, { passive: false } as any)
  window.addEventListener('wheel', onWheelCapture as any, { passive: false, capture: true } as any)

  cleanupGestures = () => {
    dom.removeEventListener('wheel', onWheel as any)
    dom.removeEventListener('gesturestart', onGestureStart as any)
    dom.removeEventListener('gesturechange', onGestureChange as any)
    dom.removeEventListener('touchstart', onTouchStart as any)
    dom.removeEventListener('touchmove', onTouchMove as any)
    dom.removeEventListener('touchend', onTouchEnd as any)
    dom.removeEventListener('touchcancel', onTouchEnd as any)
    dom.removeEventListener('pointerenter', onEnter)
    dom.removeEventListener('pointerleave', onLeave)
    window.removeEventListener('wheel', onWheelCapture as any, true as any)
  }
}

function bindWhenReady() {
  const inst = chartRef.value?.getEchartsInstance?.()
  if (inst) {
    // 先清理再绑定，避免热更新/多实例导致的重复绑定
    cleanupGestures?.()
    cleanupGestures = null
    cleanupZoomSync?.()
    cleanupZoomSync = null
    bindGestures()
    bindZoomSync()
    return
  }
  // 等待 echarts 实例创建（vue-echarts 可能在 onMounted 后才 ready）
  setTimeout(bindWhenReady, 60)
}

onMounted(() => bindWhenReady())
onUnmounted(() => {
  cleanupGestures?.()
  cleanupGestures = null
  cleanupZoomSync?.()
  cleanupZoomSync = null
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
  /* 允许页面纵向滚动，但由组件接管双指 pinch / 横向平移 */
  touch-action: pan-y;
}
</style>

