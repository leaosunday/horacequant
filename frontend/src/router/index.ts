import { createRouter, createWebHistory, RouteRecordRaw } from 'vue-router'
import StockList from '../views/StockList.vue'
import StockDetail from '../views/StockDetail.vue'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: '/stocks/b1/20251229'
  },
  {
    path: '/stocks/:ruleName/:tradeDate',
    name: 'StockList',
    component: StockList
  },
  {
    path: '/stock/:code',
    name: 'StockDetail',
    component: StockDetail,
    props: true
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router

