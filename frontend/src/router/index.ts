import { createRouter, createWebHistory, RouteRecordRaw } from 'vue-router'
import StockList from '../views/StockList.vue'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'StockList',
    component: StockList
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router

