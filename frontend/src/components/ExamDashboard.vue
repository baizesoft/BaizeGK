<script setup>
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { dateText, study } from '../api/study.js'
const board = ref(null), error = ref(''), message = ref(''), editing = ref(null), saving = ref(false)
const phases = { registration: '报名', payment: '缴费', ticket: '准考证', written: '公共笔试 · 第一场', written_pm: '公共笔试 · 第二场' }
const labels = { pending: '本轮未查到新公告／待公布', unverified: '本轮暂无法核验', confirmed: '本轮公告已核对' }
const collisionLabels = { unknown: '两地本轮笔试时段未确认，暂不判断撞期。', none: '按已确认的公共科目时段，两地没有重叠。', overlap: '两地公共科目笔试有时段重叠，请按目标职位取舍。' }
async function load() {
  error.value = ''
  try { board.value = await study('/exams') } catch (e) { error.value = e.message }
}
function edit(item) {
  const c = item.current
  message.value = ''; error.value = ''
  editing.value = { id: item.id, year: c.year, status: c.status, source: c.source, source_title: c.source_title,
    timeline: Object.fromEntries(Object.keys(phases).map(k => [k, { start: c.timeline[k]?.start?.slice(0, 16) || '', end: c.timeline[k]?.end?.slice(0, 16) || '' }])) }
}
async function save() {
  const { id, timeline, ...body } = editing.value
  error.value = ''; message.value = ''; saving.value = true
  try {
    body.timeline = body.status === 'confirmed' ? Object.fromEntries(Object.entries(timeline).filter(([, t]) => t.start || t.end)
      .map(([k, t]) => [k, { start: t.start || null, end: t.end || null }])) : {}
    board.value = await study(`/exams/${id}`, 'PUT', body)
    editing.value = null; message.value = '本地核验记录已保存'
  } catch (e) { error.value = e.message } finally { saving.value = false }
}
function range(t) {
  if (!t?.start && !t?.end) return '待公布'
  if (t.start && t.end) return `${dateText(t.start)} — ${dateText(t.end)}`
  return t.start ? `${dateText(t.start)} 起` : `截止 ${dateText(t.end)}`
}
onMounted(load)
</script>

<template>
  <div class="study-page">
    <header class="study-heading"><span class="eyebrow">白泽公考 / 个人备考</span><h1>我的两场考试</h1><p>铜仁看贵州省考，重庆看重庆市考。公告与往年参考分开；时间均为北京时间。</p></header>
    <p v-if="error && !editing" role="alert" class="study-error">{{ error }} <button v-if="!board" @click="load">重试</button></p>
    <p v-if="message" role="status" class="study-message">{{ message }}</p>
    <p v-if="!board && !error">正在读取本地记录…</p>
    <template v-if="board">
      <p class="study-banner" data-testid="collision" :data-collision="board.collision">{{ collisionLabels[board.collision] }}</p>
      <div class="study-grid">
        <article v-for="item in board.items" :key="item.id" :data-testid="`exam-${item.id}`" class="study-card">
          <div class="study-between"><h2>{{ item.name }}</h2><span class="study-chip">{{ item.current.year }} 年度</span></div>
          <p class="study-stage">{{ labels[item.current.status] }}</p><p v-if="item.current.note" class="study-subtle">{{ item.current.note }}</p>
          <dl class="study-timeline"><div v-for="(name, key) in phases" :key="key"><dt>{{ name }}</dt><dd>{{ range(item.current.timeline[key]) }} <span v-if="item.stages[key]" class="study-chip">{{ item.stages[key] }}</span></dd></div></dl>
          <p class="study-subtle"><a :href="item.current.source" target="_blank" rel="noopener noreferrer">核验来源</a> · {{ dateText(item.current.checked_at) }}</p>
          <details><summary>{{ item.history.year }} 年历史参考（不是本轮）</summary><dl class="study-timeline"><div v-for="(name, key) in phases" :key="key"><dt>{{ name }}</dt><dd>{{ range(item.history.timeline[key]) }}</dd></div></dl><a :href="item.history.source" target="_blank" rel="noopener noreferrer">往年公告原文</a></details>
          <div class="study-actions"><RouterLink :to="`/study/${item.id}`" class="study-button primary">练对应试卷</RouterLink><RouterLink :to="`/jobs/${item.id}`" class="study-button">看职位表</RouterLink><button @click="edit(item)">更新核验</button></div>
          <form v-if="editing?.id === item.id" class="study-form" @submit.prevent="save">
            <h3>手工更新 · {{ editing.year }} 年度</h3>
            <label>核验状态<select v-model="editing.status" name="status"><option value="pending">未查到新公告／待公布</option><option value="unverified">暂无法核验</option><option value="confirmed">已核对本轮公告</option></select></label>
            <label>官方来源<input v-model.trim="editing.source" required type="url" name="source"></label>
            <label>来源标题<input v-model.trim="editing.source_title" name="source_title" :required="editing.status === 'confirmed'"></label>
            <template v-if="editing.status === 'confirmed'">
              <p class="study-subtle">按公告正文录入；没公布的日期留空。第二场可留空。</p>
              <fieldset v-for="(name, key) in phases" :key="key" class="study-date-edit"><legend>{{ name }}</legend><label>开始<input v-model="editing.timeline[key].start" type="datetime-local" :name="`${key}-start`"></label><label>截止<input v-model="editing.timeline[key].end" type="datetime-local" :name="`${key}-end`"></label></fieldset>
            </template>
            <div class="study-actions"><button class="primary" :disabled="saving">保存核验记录</button><button type="button" @click="editing = null">取消</button></div><p v-if="error" role="alert" class="study-error">{{ error }}</p>
          </form>
        </article>
      </div>
    </template>
  </div>
</template>
