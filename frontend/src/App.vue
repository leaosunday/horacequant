<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import type { PickBundleItem } from './lib/api'
import { fetchPicksBundle } from './lib/api'
import KlineMultiPanel from './components/KlineMultiPanel.vue'

const ruleName = ref('b1')
const tradeDate = ref(dayjs().format('YYYY-MM-DD'))

const loading = ref(false)
const items = ref<PickBundleItem[]>([])
const selectedCode = ref<string>('')

const selected = computed(() => items.value.find((x) => x.code === selectedCode.value) ?? items.value[0])

function fmt2(v: unknown): string {
  const n = Number(v)
  if (!Number.isFinite(n)) return '--'
  return n.toFixed(2)
}

function fmtPct(v: unknown): string {
  const n = Number(v)
  if (!Number.isFinite(n)) return '--'
  return `${n.toFixed(2)}%`
}

function fmtCap(v: unknown): string {
  const n = Number(v)
  if (!Number.isFinite(n)) return '--'
  // 元 -> 亿
  return `${(n / 1e8).toFixed(2)}亿`
}

function latestSnapshot(item: PickBundleItem | undefined) {
  if (!item || !item.daily || item.daily.length === 0) return null
  const last = item.daily[item.daily.length - 1]
  if (!last) return null
  const prev = item.daily.length >= 2 ? item.daily[item.daily.length - 2] : null
  const close = Number(last.close ?? NaN)
  const prevClose = Number(prev?.close ?? NaN)
  const change = Number.isFinite(close) && Number.isFinite(prevClose) ? close - prevClose : Number(last.change_amount ?? NaN)
  const pct = Number.isFinite(close) && Number.isFinite(prevClose) && prevClose !== 0 ? (change / prevClose) * 100 : Number(last.pct_change ?? NaN)
  return {
    code: item.code,
    name: item.name,
    close,
    change,
    pct,
    high: last.high,
    low: last.low,
    open: last.open,
    prevClose,
    turnover_rate: last.turnover_rate,
    market_cap: item.market_cap,
  }
}

const tableRows = computed(() => {
  return items.value.map((it) => {
    const s = latestSnapshot(it)
    return {
      ...it,
      _s: s,
    }
  })
})

async function load() {
  loading.value = true
  try {
    const r = await fetchPicksBundle({
      ruleName: ruleName.value,
      tradeDate: tradeDate.value,
      windowDays: 365, // 拉一年，默认缩放到最近 3 个月，支持向左拖
      limit: 200,
    })
    if (r.code !== 0) throw new Error(r.message || 'api_error')
    items.value = r.data.items || []
    selectedCode.value = items.value[0]?.code ?? ''
  } catch (e: any) {
    console.error(e)
    ElMessage.error(`加载失败：${String(e?.message ?? e)}`)
  } finally {
    loading.value = false
  }
}

onMounted(() => void load())
</script>

<template>
  <div class="app">
    <div class="topbar">
      <div class="title">HoraceQuant</div>
      <div class="controls">
        <el-input v-model="ruleName" style="width: 120px" placeholder="策略(b1)" />
        <el-date-picker v-model="tradeDate" type="date" value-format="YYYY-MM-DD" format="YYYY-MM-DD" />
        <el-button type="primary" :loading="loading" @click="load">加载</el-button>
      </div>
    </div>

    <div class="content">
      <div class="left">
        <el-table
          v-loading="loading"
          :data="tableRows"
          height="100%"
          style="width: 100%"
          @row-click="(row:any) => (selectedCode = row.code)"
        >
          <el-table-column prop="code" label="代码" width="90" />
          <el-table-column prop="name" label="名称" width="120" show-overflow-tooltip />
          <el-table-column label="最新价" width="90">
            <template #default="{ row }">{{ fmt2(row._s?.close) }}</template>
          </el-table-column>
          <el-table-column label="涨跌额" width="90">
            <template #default="{ row }">{{ fmt2(row._s?.change) }}</template>
          </el-table-column>
          <el-table-column label="涨跌幅" width="90">
            <template #default="{ row }">{{ fmtPct(row._s?.pct) }}</template>
          </el-table-column>
          <el-table-column label="最高" width="90">
            <template #default="{ row }">{{ fmt2(row._s?.high) }}</template>
          </el-table-column>
          <el-table-column label="最低" width="90">
            <template #default="{ row }">{{ fmt2(row._s?.low) }}</template>
          </el-table-column>
          <el-table-column label="今开" width="90">
            <template #default="{ row }">{{ fmt2(row._s?.open) }}</template>
          </el-table-column>
          <el-table-column label="昨收" width="90">
            <template #default="{ row }">{{ fmt2(row._s?.prevClose) }}</template>
          </el-table-column>
          <el-table-column label="换手率" width="90">
            <template #default="{ row }">{{ fmtPct(row._s?.turnover_rate) }}</template>
          </el-table-column>
          <el-table-column label="总市值" width="100">
            <template #default="{ row }">{{ fmtCap(row._s?.market_cap) }}</template>
          </el-table-column>
        </el-table>
      </div>

      <div class="right">
        <div class="header" v-if="selected">
          <div class="h1">
            <span class="code">{{ selected.code }}</span>
            <span class="name">{{ selected.name }}</span>
            <span class="meta">({{ selected.exchange }})</span>
          </div>
        </div>
        <div class="chart" v-if="selected">
          <KlineMultiPanel :daily="selected.daily" :weekly="selected.weekly" :initial-daily-candles="60" />
        </div>
        <div class="empty" v-else>无数据</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.app {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #0b1220;
  color: #e2e8f0;
}
.topbar {
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  border-bottom: 1px solid rgba(51, 65, 85, 0.6);
}
.title {
  font-weight: 700;
  letter-spacing: 0.2px;
}
.controls {
  display: flex;
  gap: 10px;
  align-items: center;
}
.content {
  flex: 1;
  display: grid;
  grid-template-columns: 540px 1fr;
  gap: 10px;
  padding: 10px;
  min-height: 0;
}
.left {
  min-height: 0;
  border: 1px solid rgba(51, 65, 85, 0.6);
  border-radius: 8px;
  overflow: hidden;
  background: rgba(15, 23, 42, 0.35);
}
.right {
  min-height: 0;
  border: 1px solid rgba(51, 65, 85, 0.6);
  border-radius: 8px;
  overflow: hidden;
  background: rgba(15, 23, 42, 0.35);
  display: flex;
  flex-direction: column;
}
.header {
  padding: 10px 12px;
  border-bottom: 1px solid rgba(51, 65, 85, 0.6);
}
.h1 {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.code {
  font-weight: 800;
  font-size: 18px;
}
.name {
  font-weight: 600;
  font-size: 16px;
}
.meta {
  color: #94a3b8;
}
.chart {
  flex: 1;
  min-height: 0;
  padding: 8px;
}
.empty {
  padding: 16px;
  color: #94a3b8;
}
</style>
