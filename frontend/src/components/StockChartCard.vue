<template>
  <div class="card">
    <div class="quote">
      <div class="left">
        <div class="title">
          <span class="code">{{ item.code }}</span>
          <span class="name">{{ item.name }}</span>
          <span class="sub">{{ item.exchange }}</span>
        </div>
        <div class="price">
          <div :class="['big', upDown(snap.change)]">{{ fmt2(snap.close) }}</div>
          <div class="delta">
            <span :class="['small', upDown(snap.change)]">{{ fmtSigned2(snap.change) }}</span>
            <span :class="['small', upDown(snap.pct)]">{{ fmtSignedPct(snap.pct) }}</span>
          </div>
        </div>
      </div>

      <div class="right">
        <div class="metrics">
          <div class="m">
            <div class="k">最高</div>
            <div class="v">{{ fmt2(snap.high) }}</div>
          </div>
          <div class="m">
            <div class="k">今开</div>
            <div class="v">{{ fmt2(snap.open) }}</div>
          </div>
          <div class="m">
            <div class="k">最低</div>
            <div class="v">{{ fmt2(snap.low) }}</div>
          </div>
          <div class="m">
            <div class="k">昨收</div>
            <div class="v">{{ fmt2(snap.prevClose) }}</div>
          </div>
          <div class="m">
            <div class="k">成交额</div>
            <div class="v">{{ fmtAmount(snap.amount) }}</div>
          </div>
          <div class="m">
            <div class="k">换手率</div>
            <div class="v">{{ fmtPct(snap.turnover_rate) }}</div>
          </div>
          <div class="m">
            <div class="k">总市值</div>
            <div class="v">{{ fmtCap(item.market_cap) }}</div>
          </div>
        </div>
        <div class="tabs" v-if="showModeToggle">
          <el-segmented
            v-model="modeProxy"
            :options="[
              { label: '日K', value: 'daily' },
              { label: '周K', value: 'weekly' },
              { label: '叠加', value: 'overlay' },
            ]"
          />
        </div>
      </div>
    </div>

    <div class="chart">
      <KlineMultiPanel :daily="item.daily" :weekly="item.weekly" :mode="modeProxy" :initial-candles="initialCandles" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { PickBundleItem } from '../lib/api'
import KlineMultiPanel from './KlineMultiPanel.vue'

defineOptions({ name: 'StockChartCard' })

const props = defineProps<{
  item: PickBundleItem
  mode: 'daily' | 'weekly' | 'overlay'
  initialCandles?: number
  showModeToggle?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:mode', v: 'daily' | 'weekly' | 'overlay'): void
}>()

function n(v: unknown): number {
  const x = Number(v)
  return Number.isFinite(x) ? x : NaN
}

const snap = computed(() => {
  const d = props.item.daily ?? []
  const last = d.length > 0 ? d[d.length - 1] : undefined
  const prev = d.length > 1 ? d[d.length - 2] : undefined
  const close = n(last?.close)
  const prevClose = n(prev?.close)
  const change = Number.isFinite(close) && Number.isFinite(prevClose) ? close - prevClose : n(last?.change_amount)
  const pct = Number.isFinite(close) && Number.isFinite(prevClose) && prevClose !== 0 ? (change / prevClose) * 100 : n(last?.pct_change)
  return {
    ts: String(last?.trade_date ?? props.item.trade_date ?? ''),
    close,
    prevClose,
    change,
    pct,
    high: n(last?.high),
    low: n(last?.low),
    open: n(last?.open),
    amount: n(last?.amount),
    turnover_rate: n(last?.turnover_rate),
  }
})

const modeProxy = computed({
  get: () => props.mode,
  set: (v) => emit('update:mode', v),
})

function upDown(v: unknown): string {
  const x = Number(v)
  if (!Number.isFinite(x) || x === 0) return 'flat'
  return x > 0 ? 'up' : 'down'
}

function fmt2(v: unknown): string {
  const x = Number(v)
  if (!Number.isFinite(x)) return '--'
  return x.toFixed(2)
}
function fmtSigned2(v: unknown): string {
  const x = Number(v)
  if (!Number.isFinite(x)) return '--'
  const s = x > 0 ? '+' : ''
  return `${s}${x.toFixed(2)}`
}
function fmtSignedPct(v: unknown): string {
  const x = Number(v)
  if (!Number.isFinite(x)) return '--'
  const s = x > 0 ? '+' : ''
  return `${s}${x.toFixed(2)}%`
}
function fmtPct(v: unknown): string {
  const x = Number(v)
  if (!Number.isFinite(x)) return '--'
  return `${x.toFixed(2)}%`
}
function fmtCap(v: unknown): string {
  const x = Number(v)
  if (!Number.isFinite(x)) return '--'
  return `${(x / 1e8).toFixed(2)}亿`
}
function fmtAmount(v: unknown): string {
  const x = Number(v)
  if (!Number.isFinite(x)) return '--'
  return `${(x / 1e8).toFixed(2)}亿`
}
</script>

<style scoped>
.card {
  border: 1px solid var(--hq-border);
  border-radius: 12px;
  overflow: hidden;
  background: var(--hq-panel);
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.quote {
  padding: 10px 12px 6px;
  border-bottom: 1px solid var(--hq-border);
  display: flex;
  gap: 12px;
  align-items: flex-start;
  justify-content: space-between;
}
.left {
  min-width: 240px;
}
.title {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.code {
  font-weight: 900;
  font-size: 18px;
  letter-spacing: 0.3px;
}
.name {
  font-weight: 800;
  font-size: 18px;
}
.sub {
  color: var(--hq-muted);
  font-size: 12px;
}
.price {
  margin-top: 8px;
}
.big {
  font-size: 38px;
  font-weight: 950;
  line-height: 1;
}
.delta {
  margin-top: 2px;
  display: flex;
  gap: 12px;
}
.small {
  font-size: 13px;
  font-weight: 700;
}
.right {
  flex: 1;
  min-width: 360px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(120px, 1fr));
  gap: 6px 12px;
}
.m .k {
  color: var(--hq-muted);
  font-size: 12px;
}
.m .v {
  color: var(--hq-text);
  font-size: 14px;
  font-weight: 650;
}
.tabs {
  display: flex;
  justify-content: flex-start;
}
.chart {
  flex: 1;
  min-height: 0;
  padding: 8px;
}
.up {
  color: var(--hq-red);
}
.down {
  color: var(--hq-green);
}
.flat {
  color: var(--hq-text);
}

@media (max-width: 768px) {
  .quote {
    flex-direction: column;
  }
  .right {
    min-width: 0;
  }
  .metrics {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .big {
    font-size: 42px;
  }
}
</style>

