import { createRouter, createWebHistory } from 'vue-router'
import ExamDashboard from '../components/ExamDashboard.vue'
import StudyWorkspace from '../components/StudyWorkspace.vue'
import StudyJobs from '../components/StudyJobs.vue'
import Quiz from '../components/Quiz.vue'
import Papers from '../components/Papers.vue'
import Materials from '../components/Materials.vue'

/**
 * 前端路由表。
 * 路径与任务说明保持一致：/（首页）、/quiz（在线刷题）、
 * /papers（历年真题）、/materials（学习资料）。
 */
const routes = [
  { path: '/', name: 'home', component: ExamDashboard, meta: { title: '白泽公考' } },
  { path: '/study/:region(gz-tr|cq)', name: 'study', component: StudyWorkspace },
  { path: '/jobs/:region(gz-tr|cq)', name: 'jobs', component: StudyJobs },
  { path: '/quiz', name: 'quiz', component: Quiz, meta: { title: '在线刷题' } },
  { path: '/papers', name: 'papers', component: Papers, meta: { title: '历年真题' } },
  { path: '/materials', name: 'materials', component: Materials, meta: { title: '学习资料' } },
  // 兜底：未知路径回到首页
  { path: '/:pathMatch(.*)*', redirect: '/' }
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 }
  }
})

export default router
