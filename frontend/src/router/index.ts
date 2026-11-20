import { createRouter, createWebHistory, type RouterHistory, type RouteRecordRaw } from 'vue-router'

import PredictView from '../views/PredictView.vue'

export const APP_NAME = '顧客流失預測'

export const routes: RouteRecordRaw[] = [
  { path: '/', name: 'predict', component: PredictView, meta: { title: '單筆預測' } },
  {
    path: '/performance',
    name: 'performance',
    component: () => import('../views/PerformanceView.vue'),
    meta: { title: '模型成效' },
  },
  {
    path: '/batch',
    name: 'batch',
    component: () => import('../views/BatchView.vue'),
    meta: { title: '批次預測' },
  },
]

/** 導覽列項目：由 routes 推導（path 與 meta.title） */
export const NAV_ITEMS = routes.map((r) => ({
  to: r.path,
  label: String(r.meta?.title ?? r.path),
}))

export function createAppRouter(history: RouterHistory = createWebHistory()) {
  const router = createRouter({
    history,
    routes,
    scrollBehavior: () => ({ top: 0 }),
  })
  router.afterEach((to) => {
    const title = typeof to.meta.title === 'string' ? to.meta.title : ''
    document.title = title ? `${title}｜${APP_NAME}` : APP_NAME
  })
  return router
}

export default createAppRouter
