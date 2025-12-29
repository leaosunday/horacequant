<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import type { PickBundleItem } from './lib/api'
import { fetchPicksBundle } from './lib/api'
import KlineMultiPanel from './components/KlineMultiPanel.vue'

const ruleName = ref('b1')
const tradeDate = ref(dayjs().format('YYYY-MM-DD'))
const kMode = ref<'daily' | 'weekly' | 'overlay'>('daily')

const loading = ref(false)
const items = ref<PickBundleItem[]>([])
const selectedCode = ref<string>('')

const selected = computed(() => items.value.find((x) => x.code === selectedCode.value) ?? items.value[0])

function clsUpDown(v: unknown): string {
  const n = Number(v)
  if (!Number.isFinite(n) || n === 0) return 'flat'
  return n > 0 ? 'up' : 'down'
}

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

function fmtSigned2(v: unknown): string {
  const n = Number(v)
  if (!Number.isFinite(n)) return '--'
  const s = n > 0 ? '+' : ''
  return `${s}${n.toFixed(2)}`
}

function fmtSignedPct(v: unknown): string {
  const n = Number(v)
  if (!Number.isFinite(n)) return '--'
  const s = n > 0 ? '+' : ''
  return `${s}${n.toFixed(2)}%`
}

function fmtCap(v: unknown): string {
  const n = Number(v)
  if (!Number.isFinite(n)) return '--'
  // 元 -> 亿
  return `${(n / 1e8).toFixed(2)}亿`
}

function fmtAmount(v: unknown): string {
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
    amount: last.amount,
    ts: last.trade_date,
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
    // 后端 limit 最大 50；这里用 cursor 分页拉取更多条
    const pageSize = 50
    const maxItems = 200
    let cursor = ''
    const all: PickBundleItem[] = []
    while (all.length < maxItems) {
      const r = await fetchPicksBundle({
        ruleName: ruleName.value,
        tradeDate: tradeDate.value,
        windowDays: 365, // 拉一年，默认缩放到最近 3 个月，支持向左拖
        limit: pageSize,
        cursor,
      })
      if (r.code !== 0) throw new Error(r.message || 'api_error')
      const got = r.data.items || []
      all.push(...got)
      if (!r.data.next_cursor || got.length === 0) break
      cursor = r.data.next_cursor
    }
    items.value = all.slice(0, maxItems)
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
          class="hq-table"
          @row-click="(row:any) => (selectedCode = row.code)"
        >
          <el-table-column prop="code" label="代码" width="90" />
          <el-table-column prop="name" label="名称" width="120" show-overflow-tooltip />
          <el-table-column label="最新价" width="90" align="right" sortable :sort-method="(a:any,b:any)=>Number(a._s?.close??-1)-Number(b._s?.close??-1)">
            <template #default="{ row }">
              <span :class="['num', clsUpDown(row._s?.change)]">{{ fmt2(row._s?.close) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="涨跌额" width="90" align="right" sortable :sort-method="(a:any,b:any)=>Number(a._s?.change??0)-Number(b._s?.change??0)">
            <template #default="{ row }">
              <span :class="['num', clsUpDown(row._s?.change)]">{{ fmtSigned2(row._s?.change) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="涨跌幅" width="90" align="right" sortable :sort-method="(a:any,b:any)=>Number(a._s?.pct??0)-Number(b._s?.pct??0)">
            <template #default="{ row }">
              <span :class="['num', clsUpDown(row._s?.pct)]">{{ fmtSignedPct(row._s?.pct) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="最高" width="90" align="right">
            <template #default="{ row }">{{ fmt2(row._s?.high) }}</template>
          </el-table-column>
          <el-table-column label="最低" width="90" align="right">
            <template #default="{ row }">{{ fmt2(row._s?.low) }}</template>
          </el-table-column>
          <el-table-column label="今开" width="90" align="right">
            <template #default="{ row }">{{ fmt2(row._s?.open) }}</template>
          </el-table-column>
          <el-table-column label="昨收" width="90" align="right">
            <template #default="{ row }">{{ fmt2(row._s?.prevClose) }}</template>
          </el-table-column>
          <el-table-column label="换手率" width="90" align="right">
            <template #default="{ row }">{{ fmtPct(row._s?.turnover_rate) }}</template>
          </el-table-column>
          <el-table-column label="总市值" width="100" align="right">
            <template #default="{ row }">{{ fmtCap(row._s?.market_cap) }}</template>
          </el-table-column>
        </el-table>
      </div>

      <div class="right">
        <div class="quote" v-if="selected">
          <div class="q-left">
            <div class="q-title">
              <span class="q-code">{{ selected.code }}</span>
              <span class="q-name">{{ selected.name }}</span>
              <span class="q-sub">{{ selected.exchange }}</span>
            </div>
            <div class="q-time" v-if="latestSnapshot(selected)">
              已收盘 {{ latestSnapshot(selected)?.ts }}
            </div>

            <div class="q-price" v-if="latestSnapshot(selected)">
              <div :class="['q-big', clsUpDown(latestSnapshot(selected)?.change)]">
                {{ fmt2(latestSnapshot(selected)?.close) }}
              </div>
              <div class="q-delta">
                <span :class="['q-small', clsUpDown(latestSnapshot(selected)?.change)]">{{ fmtSigned2(latestSnapshot(selected)?.change) }}</span>
                <span :class="['q-small', clsUpDown(latestSnapshot(selected)?.pct)]">{{ fmtSignedPct(latestSnapshot(selected)?.pct) }}</span>
              </div>
            </div>
          </div>

          <div class="q-right" v-if="latestSnapshot(selected)">
            <div class="q-metrics">
              <div class="m">
                <div class="k">最高</div>
                <div class="v">{{ fmt2(latestSnapshot(selected)?.high) }}</div>
              </div>
              <div class="m">
                <div class="k">今开</div>
                <div class="v">{{ fmt2(latestSnapshot(selected)?.open) }}</div>
              </div>
              <div class="m">
                <div class="k">最低</div>
                <div class="v">{{ fmt2(latestSnapshot(selected)?.low) }}</div>
              </div>
              <div class="m">
                <div class="k">昨收</div>
                <div class="v">{{ fmt2(latestSnapshot(selected)?.prevClose) }}</div>
              </div>
              <div class="m">
                <div class="k">成交额</div>
                <div class="v">{{ fmtAmount(latestSnapshot(selected)?.amount) }}</div>
              </div>
              <div class="m">
                <div class="k">换手率</div>
                <div class="v">{{ fmtPct(latestSnapshot(selected)?.turnover_rate) }}</div>
              </div>
              <div class="m">
                <div class="k">总市值</div>
                <div class="v">{{ fmtCap(latestSnapshot(selected)?.market_cap) }}</div>
              </div>
            </div>
            <div class="q-tabs">
              <el-segmented
                v-model="kMode"
                :options="[
                  { label: '日K', value: 'daily' },
                  { label: '周K', value: 'weekly' },
                  { label: '叠加', value: 'overlay' },
                ]"
              />
            </div>
          </div>
        </div>

        <div class="chart" v-if="selected">
          <KlineMultiPanel :daily="selected.daily" :weekly="selected.weekly" :mode="kMode" :initial-candles="60" />
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
  background: var(--hq-bg);
  color: var(--hq-text);
}
.topbar {
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  border-bottom: 1px solid var(--hq-border);
  backdrop-filter: blur(10px);
  background: rgba(11, 15, 20, 0.65);
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
  border: 1px solid var(--hq-border);
  border-radius: 8px;
  overflow: hidden;
  background: var(--hq-panel);
}
.right {
  min-height: 0;
  border: 1px solid var(--hq-border);
  border-radius: 8px;
  overflow: hidden;
  background: var(--hq-panel);
  display: flex;
  flex-direction: column;
}
.quote {
  padding: 12px 12px 8px;
  border-bottom: 1px solid var(--hq-border);
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}
.q-left {
  min-width: 240px;
}
.q-title {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.q-code {
  font-weight: 800;
  font-size: 18px;
  letter-spacing: 0.3px;
}
.q-name {
  font-weight: 700;
  font-size: 18px;
}
.q-sub {
  color: var(--hq-muted);
  font-size: 12px;
}
.q-time {
  margin-top: 4px;
  color: var(--hq-muted);
  font-size: 12px;
}
.q-price {
  margin-top: 8px;
}
.q-big {
  font-size: 44px;
  font-weight: 900;
  line-height: 1;
}
.q-delta {
  margin-top: 2px;
  display: flex;
  gap: 12px;
}
.q-small {
  font-size: 14px;
  font-weight: 600;
}
.q-right {
  flex: 1;
  min-width: 360px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.q-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(120px, 1fr));
  gap: 8px 14px;
}
.m .k {
  color: var(--hq-muted);
  font-size: 12px;
}
.m .v {
  color: var(--hq-text);
  font-size: 14px;
  font-weight: 600;
}
.q-tabs {
  display: flex;
  justify-content: flex-start;
}
.num.up,
.q-big.up,
.q-small.up {
  color: var(--hq-red);
}
.num.down,
.q-big.down,
.q-small.down {
  color: var(--hq-green);
}
.num.flat,
.q-big.flat,
.q-small.flat {
  color: var(--hq-text);
}
.chart {
  flex: 1;
  min-height: 0;
  padding: 8px;
}
.empty {
  padding: 16px;
  color: var(--hq-muted);
}
</style>
