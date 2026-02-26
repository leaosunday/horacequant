<template>
  <div class="stock-list-container">
    <!-- 顶部导航 -->
    <div class="header">
      <div class="header-content">
        <h1 class="title">HoraceQuant</h1>
        <div class="controls">
          <div v-if="items.length > 0" class="total-count">
            共 {{ totalCount }} 只
          </div>
          <div class="control-group">
            <label>选股规则</label>
            <input 
              v-model="ruleName" 
              type="text" 
              class="rule-input"
              placeholder="如: b1"
              @keyup.enter="reloadData"
            />
          </div>
          <div class="control-group">
            <label>交易日期</label>
            <input 
              v-model="tradeDate" 
              type="date" 
              class="date-input"
              @change="reloadData"
            />
          </div>
          <button @click="reloadData" class="search-btn">查询</button>
        </div>
      </div>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading && items.length === 0" class="loading-container">
      <div class="loading-spinner"></div>
      <p>加载选股结果中...</p>
    </div>

    <!-- 股票列表 -->
    <div v-else class="stocks-grid">
      <div
        v-for="item in items"
        :key="item.code"
        class="stock-card"
      >
        <KlineChart
          :stock-code="item.code"
          :stock-name="item.name"
          :exchange="item.exchange"
          :daily-data="item.daily"
          :weekly-data="item.weekly"
          :market-cap="item.market_cap"
        />
      </div>
    </div>

    <!-- 加载更多 -->
    <div v-if="hasMore" class="load-more">
      <button v-if="!loading" @click="loadMore" class="load-more-btn">
        加载更多
      </button>
      <div v-else class="loading-spinner small"></div>
    </div>

    <!-- 空状态 -->
    <div v-if="!loading && items.length === 0" class="empty-state">
      <p>暂无选股结果</p>
      <p class="empty-hint">请检查日期或等待定时任务完成</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { fetchPicksStream } from '@/api'
import type { PickBundleItem } from '@/types/api'
import KlineChart from '@/components/KlineChart.vue'
import dayjs from 'dayjs'

// 默认值
const ruleName = ref('b1')
const tradeDate = ref(dayjs().format('YYYY-MM-DD'))

const items = ref<PickBundleItem[]>([])
const nextCursor = ref('')
const totalCount = ref(0)
const loading = ref(false)
const hasMore = ref(true)

// 加载数据
const loadData = async (cursor = '') => {
  if (loading.value) return

  loading.value = true
  try {
    // 格式化日期为 YYYYMMDD
    const formattedDate = tradeDate.value.replace(/-/g, '')
    
    const stream = fetchPicksStream({
      ruleName: ruleName.value,
      tradeDate: formattedDate,
      limit: 20,
      cursor
    })

    for await (const message of stream) {
      if (message.type === 'meta') {
        nextCursor.value = message.data.next_cursor
        totalCount.value = message.data.total
        hasMore.value = !!message.data.next_cursor
      } else if (message.type === 'item') {
        items.value.push(message.data)
      }
    }
  } catch (error) {
    console.error('Failed to load picks:', error)
  } finally {
    loading.value = false
  }
}

// 重新加载数据（清空列表）
const reloadData = () => {
  items.value = []
  nextCursor.value = ''
  hasMore.value = true
  loadData()
}

// 加载更多
const loadMore = () => {
  if (nextCursor.value) {
    loadData(nextCursor.value)
  }
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.stock-list-container {
  width: 100%;
  min-height: 100vh;
  background-color: #0a0a0a;
  color: #ffffff;
}

.header {
  position: sticky;
  top: 0;
  z-index: 100;
  background-color: #0a0a0a;
  border-bottom: 1px solid #1a1a1a;
  padding: 16px;
}

.header-content {
  max-width: 1400px;
  margin: 0 auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
}

.title {
  font-size: 24px;
  font-weight: 600;
  margin: 0;
  white-space: nowrap;
}

.controls {
  display: flex;
  gap: 12px;
  align-items: flex-end;
  flex-wrap: wrap;
}

.control-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.control-group label {
  font-size: 12px;
  color: #8a8a8a;
}

.rule-input,
.date-input {
  padding: 6px 12px;
  background-color: #1a1a1a;
  border: 1px solid #3a3a3a;
  border-radius: 4px;
  color: #ffffff;
  font-size: 14px;
  outline: none;
  transition: all 0.2s;
  color-scheme: dark;
}

.rule-input {
  width: 100px;
}

.date-input {
  width: 150px;
}

.rule-input:focus,
.date-input:focus {
  border-color: #5a5a5a;
  background-color: #2a2a2a;
}

.rule-input::placeholder {
  color: #5a5a5a;
}

.search-btn {
  padding: 6px 20px;
  background-color: #3a3a3a;
  border: 1px solid #5a5a5a;
  border-radius: 4px;
  color: #ffffff;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.search-btn:hover {
  background-color: #4a4a4a;
  border-color: #6a6a6a;
}

.search-btn:active {
  transform: scale(0.98);
}

.total-count {
  font-size: 14px;
  color: #8a8a8a;
  padding-bottom: 6px;
  margin-left: 8px;
}

.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  gap: 16px;
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid #1a1a1a;
  border-top-color: #ffffff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.loading-spinner.small {
  width: 24px;
  height: 24px;
  border-width: 2px;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.stocks-grid {
  max-width: 1400px;
  margin: 0 auto;
  padding: 16px;
  display: grid;
  gap: 16px;
}

/* PC端：1x2布局 */
@media (min-width: 1024px) {
  .stocks-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

/* 移动端：1x1布局 */
@media (max-width: 1023px) {
  .stocks-grid {
    grid-template-columns: 1fr;
  }
}

.stock-card {
  background-color: #0f0f0f;
  border: 1px solid #1a1a1a;
  border-radius: 8px;
  overflow: hidden;
  transition: all 0.2s;
  min-height: 600px;
}

.load-more {
  display: flex;
  justify-content: center;
  padding: 24px;
}

.load-more-btn {
  padding: 12px 32px;
  background-color: #1a1a1a;
  border: 1px solid #3a3a3a;
  color: #ffffff;
  font-size: 14px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.load-more-btn:hover {
  background-color: #2a2a2a;
  border-color: #4a4a4a;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  gap: 8px;
  color: #8a8a8a;
}

.empty-hint {
  font-size: 14px;
  color: #5a5a5a;
}

/* 移动端适配 */
@media (max-width: 768px) {
  .header {
    padding: 12px;
  }

  .header-content {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }

  .title {
    font-size: 20px;
  }

  .controls {
    width: 100%;
  }

  .control-group {
    flex: 1;
  }

  .rule-input,
  .date-input {
    width: 100%;
  }

  .stocks-grid {
    padding: 12px;
    gap: 12px;
  }

  .stock-card {
    min-height: 500px;
  }
}
</style>

