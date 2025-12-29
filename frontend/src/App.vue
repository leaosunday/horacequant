<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import type { PickBundleItem } from './lib/api'
import { fetchPicksBundleStream } from './lib/api'
import StockChartCard from './components/StockChartCard.vue'

const ruleName = ref('b1')
const tradeDate = ref(dayjs().format('YYYY-MM-DD'))
const mode = ref<'daily' | 'weekly' | 'overlay'>('daily')

const loading = ref(false)
const items = ref<PickBundleItem[]>([])
const cursor = ref<string>('')
const done = ref(false)
const requestId = ref<string | null>(null)

const scrollerRef = ref<HTMLElement | null>(null)
const sentinelRef = ref<HTMLElement | null>(null)
let io: IntersectionObserver | null = null

async function resetAndLoad() {
  items.value = []
  cursor.value = ''
  done.value = false
  requestId.value = null
  await loadMore()
}

async function loadMore() {
  if (loading.value || done.value) return
  loading.value = true
  try {
    let gotAny = false
    let nextCursor = ''
    await fetchPicksBundleStream({
      ruleName: ruleName.value,
      tradeDate: tradeDate.value,
      windowDays: 365,
      limit: 50,
      cursor: cursor.value,
      onMeta: (m) => {
        nextCursor = m.next_cursor
        requestId.value = (m.request_id ?? null) as any
      },
      onItem: (it) => {
        gotAny = true
        items.value.push(it)
      },
    })
    const next = nextCursor
    if (!next || !gotAny) {
      done.value = true
    } else {
      cursor.value = next
    }
  } catch (e: any) {
    console.error(e)
    ElMessage.error(`加载失败：${String(e?.message ?? e)}`)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void resetAndLoad()
  io = new IntersectionObserver(
    (entries) => {
      const hit = entries.some((e) => e.isIntersecting)
      if (hit) void loadMore()
    },
    { root: scrollerRef.value, rootMargin: '800px 0px', threshold: 0.01 },
  )
  if (sentinelRef.value) io.observe(sentinelRef.value)
})

onUnmounted(() => {
  io?.disconnect()
  io = null
})
</script>

<template>
  <div class="app">
    <div class="topbar">
      <div class="brand">
        <div class="title">HoraceQuant</div>
        <div class="sub">picks · {{ ruleName }} · {{ tradeDate }} <span v-if="requestId" class="rid">rid={{ requestId }}</span></div>
      </div>
      <div class="controls">
        <el-input v-model="ruleName" style="width: 120px" placeholder="策略(b1)" />
        <el-date-picker v-model="tradeDate" type="date" value-format="YYYY-MM-DD" format="YYYY-MM-DD" />
        <el-segmented
          v-model="mode"
          :options="[
            { label: '日K', value: 'daily' },
            { label: '周K', value: 'weekly' },
            { label: '叠加', value: 'overlay' },
          ]"
        />
        <el-button type="primary" :loading="loading" @click="resetAndLoad">刷新</el-button>
      </div>
    </div>

    <div class="scroller" ref="scrollerRef">
      <div class="grid">
        <StockChartCard v-for="it in items" :key="`${it.code}-${it.trade_date}`" :item="it" :mode="mode" @update:mode="(v)=>mode=v" />
      </div>

      <div class="footer">
        <div v-if="loading" class="hint">加载中（流式）…</div>
        <div v-else-if="done" class="hint">没有更多了</div>
        <div v-else class="hint">下拉继续加载</div>
        <div ref="sentinelRef" class="sentinel" />
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
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  border-bottom: 1px solid var(--hq-border);
  backdrop-filter: blur(10px);
  background: rgba(11, 15, 20, 0.65);
}
.brand {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.title {
  font-weight: 800;
  letter-spacing: 0.2px;
}
.sub {
  font-size: 12px;
  color: var(--hq-muted);
}
.rid {
  margin-left: 8px;
  color: rgba(96, 165, 250, 0.85);
}
.controls {
  display: flex;
  gap: 10px;
  align-items: center;
}
.scroller {
  flex: 1;
  overflow: auto;
  padding: 10px;
}
.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-auto-rows: calc((100vh - 56px - 20px - 10px) / 2);
  gap: 10px;
}
.footer {
  padding: 10px 0 20px;
  text-align: center;
}
.hint {
  color: var(--hq-muted);
  font-size: 12px;
}
.sentinel {
  height: 1px;
}

@media (max-width: 768px) {
  .controls {
    gap: 8px;
  }
  .grid {
    grid-template-columns: 1fr;
    grid-auto-rows: calc(100vh - 56px - 20px);
  }
}
</style>
