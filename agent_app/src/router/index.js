import { createRouter, createWebHistory } from 'vue-router'
import Agent from '../views/Agent.vue'

const routes = [
  { path: '/', name: 'Agent', component: Agent },
  { path: '/agent', redirect: '/' },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
