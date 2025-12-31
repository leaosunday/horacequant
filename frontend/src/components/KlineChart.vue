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
import { init, dispose } from 'klinecharts'
import type { KLineData } from 'klinecharts'
import type { KlinePoint } from '@/types/api'

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
let chartInstance: any = null

const currentPeriod = ref<'daily' | 'weekly'>('daily')
const periods = [
  { label: '日K', value: 'daily' as const },
  { label: '周K', value: 'weekly' as const }
]

// 当前显示的数据（用于图表）
const currentData = computed(() => {
  return currentPeriod.value === 'daily' ? props.dailyData : props.weeklyData
})

// 最新一根K线数据（固定使用日K数据，用于表头显示）
const latestKline = computed(() => {
  const data = props.dailyData
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
  if (!latest || latest.close === null || latest.close === undefined) return '--'
  if (latest.pct_change === null || latest.pct_change === undefined) return '--'
  if (latest.change_amount === null || latest.change_amount === undefined) return '--'
  
  const change = latest.change_amount
  const pct = latest.pct_change
  const sign = change >= 0 ? '+' : ''
  return `${sign}${change.toFixed(2)} ${formatPercent(pct)}`
})

const priceClass = computed(() => {
  const pct = latestKline.value?.pct_change
  if (pct === null || pct === undefined) return 'neutral'
  return pct > 0 ? 'up' : pct < 0 ? 'down' : 'neutral'
})

const high = computed(() => formatPrice(latestKline.value?.high))
const low = computed(() => formatPrice(latestKline.value?.low))
const open = computed(() => formatPrice(latestKline.value?.open))
const preClose = computed(() => {
  const latest = latestKline.value
  if (!latest || latest.close === null || latest.close === undefined) return '--'
  if (latest.change_amount === null || latest.change_amount === undefined) return '--'
  return formatPrice(latest.close - latest.change_amount)
})

const amount = computed(() => formatAmount(latestKline.value?.amount))
const turnoverRate = computed(() => {
  const rate = latestKline.value?.turnover_rate
  return rate !== null && rate !== undefined ? `${rate.toFixed(2)}%` : '--'
})
const marketCap = computed(() => formatMarketCap(props.marketCap))

// 转换数据格式为 KLineChart 需要的格式
const convertToKLineData = (data: KlinePoint[]): KLineData[] => {
  return data.map(d => {
    const timestamp = new Date(d.trade_date).getTime()
    return {
      timestamp,
      open: Number(d.open) || 0,
      high: Number(d.high) || 0,
      low: Number(d.low) || 0,
      close: Number(d.close) || 0,
      volume: Number(d.volume) || 0,
      turnover: Number(d.amount) || 0,
      // 保存趋势线数据到扩展字段
      shortTrendLine: d.short_trend_line,
      bullBearLine: d.bull_bear_line
    }
  })
}

// 创建自定义指标 - ZX（包含 Short 和 Long 两条线）
const createZXIndicator = () => {
  return {
    name: 'ZX',
    shortName: 'ZX',
    calcParams: [],
    figures: [
      { key: 'short', title: 'Short: ', type: 'line', color: '#ffd700' },
      { key: 'long', title: 'Long: ', type: 'line', color: '#ff8c00' }
    ],
    calc: (kLineDataList: any[]) => {
      return kLineDataList.map(kLineData => {
        const shortValue = kLineData.shortTrendLine
        const longValue = kLineData.bullBearLine
        return {
          short: (shortValue !== null && shortValue !== undefined && !isNaN(shortValue)) ? Number(shortValue) : null,
          long: (longValue !== null && longValue !== undefined && !isNaN(longValue)) ? Number(longValue) : null
        }
      })
    },
    regenerateFigures: () => {
      return [
        { key: 'short', title: 'Short: ', type: 'line', color: '#ffd700' },
        { key: 'long', title: 'Long: ', type: 'line', color: '#ff8c00' }
      ]
    },
    shouldFormatBigNumber: true,
    visible: true,
    zLevel: 0,
    createTooltipDataSource: ({ indicator }: any) => {
      const result = indicator.result
      if (!result || result.length === 0) {
        return { name: 'ZX', calcParamsText: '', values: [] }
      }
      const lastData = result[result.length - 1]
      const values = []
      
      if (lastData.short !== null && lastData.short !== undefined) {
        values.push({ 
          title: 'Short: ', 
          value: lastData.short.toFixed(2),
          color: '#ffd700'
        })
      }
      
      if (lastData.long !== null && lastData.long !== undefined) {
        values.push({ 
          title: 'Long: ', 
          value: lastData.long.toFixed(2),
          color: '#ff8c00'
        })
      }
      
      return {
        name: 'ZX',
        calcParamsText: '',
        values
      }
    }
  }
}

// 切换周期
const changePeriod = (period: 'daily' | 'weekly') => {
  currentPeriod.value = period
  renderChart()
}

// 渲染图表
const renderChart = () => {
  if (!chartInstance) return

  const data = currentData.value
  if (!data || data.length === 0) return

  const klineData = convertToKLineData(data)
  
  try {
    chartInstance.applyNewData(klineData)
    
    // 滚动到最新数据并设置默认显示90根K线
    setTimeout(() => {
      chartInstance.scrollToRealTime()
      // 设置显示最后90根K线
      const barCount = Math.min(90, klineData.length)
      chartInstance.setBarSpace(chartRef.value!.offsetWidth / barCount)
    }, 100)
  } catch (e) {
    console.error('Failed to render chart:', e)
  }
}

// 初始化图表
const initChart = async () => {
  if (!chartRef.value) return

  try {
    // 注册自定义指标
    const klinecharts = await import('klinecharts')
    const { registerIndicator } = klinecharts
    registerIndicator(createZXIndicator() as any)
    
    chartInstance = init(chartRef.value, {
      styles: {
        grid: {
          horizontal: {
            color: '#1a1a1a'
          },
          vertical: {
            show: false
          }
        },
        candle: {
          bar: {
            upColor: '#ee4b4b',
            downColor: '#3dd598',
            noChangeColor: '#8a8a8a',
            upBorderColor: '#ee4b4b',
            downBorderColor: '#3dd598',
            noChangeBorderColor: '#8a8a8a',
            upWickColor: '#ee4b4b',
            downWickColor: '#3dd598',
            noChangeWickColor: '#8a8a8a'
          },
          priceMark: {
            high: {
              color: '#ee4b4b'
            },
            low: {
              color: '#3dd598'
            },
            last: {
              upColor: '#ee4b4b',
              downColor: '#3dd598',
              noChangeColor: '#8a8a8a',
              text: {
                color: '#ffffff'
              }
            }
          }
        },
        xAxis: {
          axisLine: {
            color: '#3a3a3a'
          },
          tickText: {
            color: '#8a8a8a',
            size: 10
          }
        },
        yAxis: {
          axisLine: {
            color: '#3a3a3a'
          },
          tickText: {
            color: '#8a8a8a',
            size: 10
          }
        },
        crosshair: {
          horizontal: {
            line: {
              color: '#5a5a5a'
            },
            text: {
              color: '#ffffff',
              backgroundColor: '#2a2a2a'
            }
          },
          vertical: {
            line: {
              color: '#5a5a5a'
            },
            text: {
              color: '#ffffff',
              backgroundColor: '#2a2a2a'
            }
          }
        }
      }
    } as any)

    if (!chartInstance) return

    // 创建副图 - 成交量（指定固定高度）
    chartInstance.createIndicator('VOL', true, { height: 100 })
    
    // 创建副图 - MACD
    chartInstance.createIndicator('MACD', true, { height: 100 })
    
    // 创建副图 - KDJ
    chartInstance.createIndicator('KDJ', true, { height: 100 })
    
    // 添加ZX指标到主图（包含 Short 和 Long 两条线）
    chartInstance.createIndicator('ZX', false, { id: 'candle_pane' })

    // 延迟渲染，确保图表完全初始化
    setTimeout(() => {
      renderChart()
    }, 100)
  } catch (e) {
    console.error('Failed to init chart:', e)
  }
}

// 生命周期
onMounted(() => {
  initChart()
})

onUnmounted(() => {
  if (chartInstance && chartRef.value) {
    dispose(chartRef.value)
    chartInstance = null
  }
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
  display: inline-flex;
  margin-bottom: 12px;
}

.period-btn {
  padding: 4px 12px;
  background: transparent;
  border: 1px solid #3a3a3a;
  color: #8a8a8a;
  font-size: 12px;
  cursor: pointer;
  border-radius: 0;
  transition: all 0.2s;
  margin-left: -1px;
}

.period-btn:first-child {
  margin-left: 0;
  border-top-left-radius: 4px;
  border-bottom-left-radius: 4px;
}

.period-btn:last-child {
  border-top-right-radius: 4px;
  border-bottom-right-radius: 4px;
}

.period-btn:hover {
  background-color: #1a1a1a;
}

.period-btn.active {
  background-color: #2a2a2a;
  color: #ffffff;
  border-color: #4a4a4a;
  z-index: 1;
  position: relative;
}

.chart-container {
  flex: 1;
  min-height: 700px;
  height: 700px;
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
