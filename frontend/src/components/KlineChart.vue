<template>
  <div class="kline-chart-container">
    <!-- 股票信息头部 -->
    <div class="stock-header">
      <div class="stock-title">
        <span class="stock-code">{{ stockCode }}</span>
        <span class="stock-name">{{ stockName }} <span class="exchange">{{ exchange }}</span></span>
      </div>
    </div>

    <!-- 价格信息 -->
    <div class="price-info">
      <div class="price-main">
        <span class="current-price" :class="priceClass">{{ currentPrice }}</span>
        <span class="price-change" :class="priceClass">{{ priceChange }}</span>
      </div>
      <div class="price-grid">
        <div class="price-item">
          <span class="label">最高</span>
          <span class="value">{{ high }}</span>
        </div>
        <div class="price-item">
          <span class="label">今开</span>
          <span class="value">{{ open }}</span>
        </div>
        <div class="price-item">
          <span class="label">最低</span>
          <span class="value">{{ low }}</span>
        </div>
        <div class="price-item">
          <span class="label">昨收</span>
          <span class="value">{{ preClose }}</span>
        </div>
      </div>
      <div class="price-secondary">
        <div class="secondary-item">
          <span class="label">成交额</span>
          <span class="value">{{ amount }}</span>
        </div>
        <div class="secondary-item">
          <span class="label">换手率</span>
          <span class="value">{{ turnoverRate }}</span>
        </div>
        <div class="secondary-item">
          <span class="label">总市值</span>
          <span class="value">{{ marketCap }}</span>
        </div>
      </div>
    </div>

    <!-- 时间周期选择 -->
    <div class="period-selector">
      <button
        v-for="period in periods"
        :key="period.value"
        :class="['period-btn', { active: currentPeriod === period.value }]"
        @click="changePeriod(period.value)"
      >
        {{ period.label }}
      </button>
    </div>

    <!-- 图表容器 -->
    <div ref="chartRef" class="chart-container"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import * as echarts from 'echarts'
import type { ECharts } from 'echarts'
import type { KlinePoint } from '@/types/api'
import dayjs from 'dayjs'

interface Props {
  stockCode: string
  stockName: string
  exchange: string
  dailyData: KlinePoint[]
  weeklyData: KlinePoint[]
  marketCap?: number | null
}

const props = defineProps<Props>()

const chartRef = ref<HTMLDivElement>()
let chartInstance: ECharts | null = null

const currentPeriod = ref<'daily' | 'weekly'>('daily')
const periods = [
  { label: '日K', value: 'daily' as const },
  { label: '周K', value: 'weekly' as const }
]

// 当前显示的数据
const currentData = computed(() => {
  return currentPeriod.value === 'daily' ? props.dailyData : props.weeklyData
})

// 最新一根K线数据
const latestKline = computed(() => {
  const data = currentData.value
  return data && data.length > 0 ? data[data.length - 1] : null
})

// 格式化价格
const formatPrice = (val: number | null | undefined): string => {
  if (val === null || val === undefined) return '--'
  return val.toFixed(2)
}

// 格式化百分比
const formatPercent = (val: number | null | undefined): string => {
  if (val === null || val === undefined) return '--'
  const sign = val >= 0 ? '+' : ''
  return `${sign}${val.toFixed(2)}%`
}

// 格式化金额（亿元）
const formatAmount = (val: number | null | undefined): string => {
  if (val === null || val === undefined) return '--'
  return `${(val / 100000000).toFixed(2)}亿`
}

// 格式化市值
const formatMarketCap = (val: number | null | undefined): string => {
  if (val === null || val === undefined) return '--'
  return `${(val / 100000000).toFixed(2)}亿`
}

// 计算的值
const currentPrice = computed(() => formatPrice(latestKline.value?.close))

const priceChange = computed(() => {
  const latest = latestKline.value
  if (!latest || !latest.close || !latest.pct_change) return '--'
  const change = latest.change_amount || 0
  const pct = latest.pct_change || 0
  const sign = change >= 0 ? '+' : ''
  return `${sign}${change.toFixed(2)} ${formatPercent(pct)}`
})

const priceClass = computed(() => {
  const pct = latestKline.value?.pct_change || 0
  return pct > 0 ? 'up' : pct < 0 ? 'down' : 'neutral'
})

const high = computed(() => formatPrice(latestKline.value?.high))
const low = computed(() => formatPrice(latestKline.value?.low))
const open = computed(() => formatPrice(latestKline.value?.open))
const preClose = computed(() => {
  const latest = latestKline.value
  if (!latest || !latest.close || !latest.change_amount) return '--'
  return formatPrice(latest.close - (latest.change_amount || 0))
})

const amount = computed(() => formatAmount(latestKline.value?.amount))
const turnoverRate = computed(() => {
  const rate = latestKline.value?.turnover_rate
  return rate !== null && rate !== undefined ? `${rate.toFixed(2)}%` : '--'
})
const marketCap = computed(() => formatMarketCap(props.marketCap))

// 切换周期
const changePeriod = (period: 'daily' | 'weekly') => {
  currentPeriod.value = period
  renderChart()
}

// 渲染图表
const renderChart = () => {
  if (!chartInstance || !chartRef.value) return

  const data = currentData.value
  if (!data || data.length === 0) {
    chartInstance.clear()
    return
  }

  // 准备数据
  const dates = data.map(d => d.trade_date)
  const klineData = data.map(d => [d.open, d.close, d.low, d.high])
  const volumes = data.map(d => d.volume || 0)
  const macdDif = data.map(d => d.macd_dif)
  const macdDea = data.map(d => d.macd_dea)
  const macdHist = data.map(d => d.macd_hist)
  const kdjK = data.map(d => d.kdj_k)
  const kdjD = data.map(d => d.kdj_d)
  const kdjJ = data.map(d => d.kdj_j)
  const shortTrend = data.map(d => d.short_trend_line)
  const bullBear = data.map(d => d.bull_bear_line)

  const option: echarts.EChartsOption = {
    backgroundColor: 'transparent',
    animation: false,
    grid: [
      { left: '3%', right: '3%', top: '8%', height: '40%' }, // K线主图
      { left: '3%', right: '3%', top: '52%', height: '12%' }, // 成交量
      { left: '3%', right: '3%', top: '68%', height: '12%' }, // MACD
      { left: '3%', right: '3%', top: '84%', height: '12%' }  // KDJ
    ],
    xAxis: [
      {
        type: 'category',
        data: dates,
        boundaryGap: true,
        axisLine: { lineStyle: { color: '#3a3a3a' } },
        axisLabel: {
          color: '#8a8a8a',
          fontSize: 10,
          formatter: (value: string) => dayjs(value).format('MM/DD')
        },
        splitLine: { show: false },
        gridIndex: 0
      },
      {
        type: 'category',
        data: dates,
        gridIndex: 1,
        axisLabel: { show: false },
        axisLine: { show: false },
        splitLine: { show: false }
      },
      {
        type: 'category',
        data: dates,
        gridIndex: 2,
        axisLabel: { show: false },
        axisLine: { show: false },
        splitLine: { show: false }
      },
      {
        type: 'category',
        data: dates,
        gridIndex: 3,
        axisLabel: {
          color: '#8a8a8a',
          fontSize: 10,
          formatter: (value: string) => dayjs(value).format('MM/DD')
        },
        axisLine: { lineStyle: { color: '#3a3a3a' } },
        splitLine: { show: false }
      }
    ],
    yAxis: [
      {
        scale: true,
        position: 'right',
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: '#8a8a8a', fontSize: 10 },
        splitLine: { lineStyle: { color: '#1a1a1a' } },
        gridIndex: 0
      },
      {
        scale: true,
        position: 'right',
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: '#8a8a8a', fontSize: 10 },
        splitLine: { show: false },
        gridIndex: 1
      },
      {
        scale: true,
        position: 'right',
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: '#8a8a8a', fontSize: 10 },
        splitLine: { lineStyle: { color: '#1a1a1a' } },
        gridIndex: 2
      },
      {
        scale: true,
        position: 'right',
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: '#8a8a8a', fontSize: 10 },
        splitLine: { lineStyle: { color: '#1a1a1a' } },
        gridIndex: 3
      }
    ],
    dataZoom: [
      {
        type: 'inside',
        xAxisIndex: [0, 1, 2, 3],
        start: 70,
        end: 100,
        moveOnMouseWheel: true,
        zoomOnMouseWheel: true,
      },
      {
        type: 'slider',
        xAxisIndex: [0, 1, 2, 3],
        bottom: '1%',
        start: 70,
        end: 100,
        height: 20,
        backgroundColor: '#1a1a1a',
        fillerColor: 'rgba(58, 58, 58, 0.5)',
        borderColor: '#3a3a3a',
        handleStyle: { color: '#5a5a5a' },
        textStyle: { color: '#8a8a8a' },
      },

    ],
    series: [
      // K线
      {
        name: 'K线',
        type: 'candlestick',
        data: klineData,
        xAxisIndex: 0,
        yAxisIndex: 0,
        itemStyle: {
          color: '#ee4b4b',
          color0: '#3dd598',
          borderColor: '#ee4b4b',
          borderColor0: '#3dd598'
        }
      },
      // ZX SHORT (短期趋势线)
      {
        name: 'ZX SHORT',
        type: 'line',
        data: shortTrend,
        xAxisIndex: 0,
        yAxisIndex: 0,
        smooth: true,
        lineStyle: { color: '#ffd700', width: 1 },
        showSymbol: false
      },
      // ZX LONG (多空线)
      {
        name: 'ZX LONG',
        type: 'line',
        data: bullBear,
        xAxisIndex: 0,
        yAxisIndex: 0,
        smooth: true,
        lineStyle: { color: '#ff8c00', width: 1 },
        showSymbol: false
      },
      // 成交量
      {
        name: '成交量',
        type: 'bar',
        data: volumes.map((vol, idx) => {
          const kline = data[idx]
          const color = (kline.close || 0) >= (kline.open || 0) ? '#ee4b4b' : '#3dd598'
          return { value: vol, itemStyle: { color } }
        }),
        xAxisIndex: 1,
        yAxisIndex: 1,
        barWidth: '60%'
      },
      // MACD DIF
      {
        name: 'DIF',
        type: 'line',
        data: macdDif,
        xAxisIndex: 2,
        yAxisIndex: 2,
        smooth: false,
        lineStyle: { color: '#ffd700', width: 1 },
        showSymbol: false
      },
      // MACD DEA
      {
        name: 'DEA',
        type: 'line',
        data: macdDea,
        xAxisIndex: 2,
        yAxisIndex: 2,
        smooth: false,
        lineStyle: { color: '#00bfff', width: 1 },
        showSymbol: false
      },
      // MACD HIST
      {
        name: 'MACD',
        type: 'bar',
        data: macdHist.map(val => {
          const color = (val || 0) >= 0 ? '#ee4b4b' : '#3dd598'
          return { value: val, itemStyle: { color } }
        }),
        xAxisIndex: 2,
        yAxisIndex: 2,
        barWidth: '60%'
      },
      // KDJ K
      {
        name: 'K',
        type: 'line',
        data: kdjK,
        xAxisIndex: 3,
        yAxisIndex: 3,
        smooth: false,
        lineStyle: { color: '#ffd700', width: 1 },
        showSymbol: false
      },
      // KDJ D
      {
        name: 'D',
        type: 'line',
        data: kdjD,
        xAxisIndex: 3,
        yAxisIndex: 3,
        smooth: false,
        lineStyle: { color: '#00bfff', width: 1 },
        showSymbol: false
      },
      // KDJ J
      {
        name: 'J',
        type: 'line',
        data: kdjJ,
        xAxisIndex: 3,
        yAxisIndex: 3,
        smooth: false,
        lineStyle: { color: '#ff69b4', width: 1 },
        showSymbol: false
      }
    ],
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'cross',
        lineStyle: { color: '#5a5a5a' }
      },
      backgroundColor: 'rgba(26, 26, 26, 0.95)',
      borderColor: '#3a3a3a',
      textStyle: { color: '#ffffff', fontSize: 12 }
    },
    legend: {
      show: false
    }
  }

  chartInstance.setOption(option, true)
}

// 初始化图表
const initChart = () => {
  if (!chartRef.value) return

  chartInstance = echarts.init(chartRef.value)
  renderChart()

  // 响应式
  const resizeObserver = new ResizeObserver(() => {
    chartInstance?.resize()
  })
  resizeObserver.observe(chartRef.value)

  return () => {
    resizeObserver.disconnect()
  }
}

// 生命周期
onMounted(() => {
  initChart()
})

onUnmounted(() => {
  chartInstance?.dispose()
  chartInstance = null
})

// 监听数据变化
watch(() => [props.dailyData, props.weeklyData], () => {
  renderChart()
}, { deep: true })
</script>

<style scoped>
.kline-chart-container {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: #0a0a0a;
  color: #ffffff;
  padding: 12px;
}

.stock-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.stock-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.stock-code {
  font-size: 18px;
  font-weight: 600;
}

.stock-name {
  font-size: 16px;
  color: #ffffff;
}

.exchange {
  font-size: 12px;
  color: #8a8a8a;
  font-weight: 400;
}

.price-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}

.price-main {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.current-price {
  font-size: 32px;
  font-weight: 600;
}

.price-change {
  font-size: 16px;
}

.up {
  color: #ee4b4b;
}

.down {
  color: #3dd598;
}

.neutral {
  color: #8a8a8a;
}

.price-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}

.price-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.price-item .label {
  font-size: 12px;
  color: #8a8a8a;
}

.price-item .value {
  font-size: 14px;
  color: #ffffff;
}

.price-secondary {
  display: flex;
  gap: 16px;
  padding: 8px 0;
  border-top: 1px solid #1a1a1a;
}

.secondary-item {
  display: flex;
  gap: 8px;
  font-size: 12px;
}

.secondary-item .label {
  color: #8a8a8a;
}

.secondary-item .value {
  color: #ffffff;
}

.period-selector {
  display: flex;
  gap: 4px;
  margin-bottom: 12px;
  justify-content: flex-start;
}

.period-btn {
  padding: 4px 12px;
  background: #1a1a1a;
  border: 1px solid #3a3a3a;
  color: #8a8a8a;
  font-size: 12px;
  cursor: pointer;
  border-radius: 4px;
  transition: all 0.2s;
}

.period-btn:hover {
  background-color: #2a2a2a;
  border-color: #4a4a4a;
}

.period-btn.active {
  background-color: #3a3a3a;
  color: #ffffff;
  border-color: #5a5a5a;
}

.chart-container {
  flex: 1;
  min-height: 500px;
}

/* 移动端适配 */
@media (max-width: 768px) {
  .kline-chart-container {
    padding: 8px;
  }

  .stock-code {
    font-size: 16px;
  }

  .stock-name {
    font-size: 14px;
  }

  .current-price {
    font-size: 24px;
  }

  .price-change {
    font-size: 14px;
  }

  .price-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .chart-container {
    min-height: 400px;
  }
}
</style>

