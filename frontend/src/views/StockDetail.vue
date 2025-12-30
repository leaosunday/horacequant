<template>
  <div class="stock-detail-container">
    <!-- 返回按钮 -->
    <div class="header">
      <button class="back-btn" @click="goBack">
        <span class="back-icon">←</span>
        返回列表
      </button>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="loading-container">
      <div class="loading-spinner"></div>
      <p>加载股票数据中...</p>
    </div>

    <!-- 图表 -->
    <div v-else-if="stockData" class="chart-wrapper">
      <KlineChart
        :stock-code="stockData.code"
        :stock-name="stockData.name"
        :daily-data="stockData.daily"
        :weekly-data="stockData.weekly"
        :market-cap="stockData.market_cap"
      />
    </div>

    <!-- 错误状态 -->
    <div v-else class="error-state">
      <p>数据加载失败</p>
      <button @click="goBack" class="error-back-btn">返回列表</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { fetchPicks } from '@/api'
import type { PickBundleItem } from '@/types/api'
import KlineChart from '@/components/KlineChart.vue'

const route = useRoute()
const router = useRouter()

const stockCode = ref(route.params.code as string)
const stockData = ref<PickBundleItem | null>(null)
const loading = ref(false)

const goBack = () => {
  const ruleName = route.query.ruleName as string
  const tradeDate = route.query.tradeDate as string
  if (ruleName && tradeDate) {
    router.push({
      name: 'StockList',
      params: { ruleName, tradeDate }
    })
  } else {
    router.back()
  }
}

const loadData = async () => {
  loading.value = true
  try {
    const ruleName = (route.query.ruleName as string) || 'b1'
    const tradeDate = (route.query.tradeDate as string) || '20251229'
    
    const response = await fetchPicks({
      ruleName,
      tradeDate,
      limit: 50
    })

    // 查找对应的股票
    const found = response.data.items.find(item => item.code === stockCode.value)
    if (found) {
      stockData.value = found
    }
  } catch (error) {
    console.error('Failed to load stock data:', error)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.stock-detail-container {
  width: 100%;
  min-height: 100vh;
  background-color: #0a0a0a;
  color: #ffffff;
}

.header {
  padding: 16px;
  border-bottom: 1px solid #1a1a1a;
}

.back-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background-color: #1a1a1a;
  border: 1px solid #3a3a3a;
  color: #ffffff;
  font-size: 14px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.back-btn:hover {
  background-color: #2a2a2a;
  border-color: #4a4a4a;
}

.back-icon {
  font-size: 18px;
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

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.chart-wrapper {
  height: calc(100vh - 65px);
  padding: 16px;
}

.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  gap: 16px;
  color: #8a8a8a;
}

.error-back-btn {
  padding: 12px 32px;
  background-color: #1a1a1a;
  border: 1px solid #3a3a3a;
  color: #ffffff;
  font-size: 14px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.error-back-btn:hover {
  background-color: #2a2a2a;
  border-color: #4a4a4a;
}

/* 移动端适配 */
@media (max-width: 768px) {
  .header {
    padding: 12px;
  }

  .chart-wrapper {
    height: calc(100vh - 53px);
    padding: 12px;
  }
}
</style>

