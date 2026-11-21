<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { dateText, materialKind, regionName, study } from '../api/study.js'

const region = useRoute().params.region
const packs = ref([]), variants = ref([]), runs = ref([]), essays = ref([]), variant = ref('')
const run = ref(null), essay = ref(null), review = ref(null), minutes = ref(30), slow = ref(90), remaining = ref(0)
const chosen = ref(''), guessed = ref(false), busy = ref(false), error = ref(''), message = ref('')
const importText = ref(''), target = ref('packs'), essayText = ref('')
const first = computed(() => run.value?.questions.find(q => !run.value.attempts[q.number]))
const canAnswer = computed(() => Boolean(first.value && run.value && !run.value.closed && remaining.value > 0))
const timer = window.setInterval(() => {
  remaining.value = run.value && !run.value.closed ? Math.max(0, Math.ceil((Date.parse(run.value.deadline) - Date.now()) / 1000)) : 0
}, 250)
onUnmounted(() => window.clearInterval(timer))
async function action(fn) {
  if (busy.value) return
  busy.value = true; error.value = ''; message.value = ''
  try { await fn() } catch (e) { error.value = e.message } finally { busy.value = false }
}
async function load() {
  const query = new URLSearchParams({ region })
  if (variant.value) query.set('variant', variant.value)
  const [p, h, a] = await Promise.all([study(`/packs?${query}`), study(`/runs?region=${region}`), study(`/essays?region=${region}`)])
  packs.value = p.items; variants.value = p.variants; runs.value = h.items; essays.value = a.items
}
function assign(data) { run.value = data; remaining.value = data.remaining; chosen.value = ''; guessed.value = false }
async function focus() {
  if (canAnswer.value) await study(`/runs/${run.value.id}/focus/${first.value.number}`, 'PUT')
}
async function begin(packId) {
  await action(async () => {
    essay.value = null; review.value = null
    assign(await study('/runs', 'POST', { pack_id: packId, minutes: minutes.value, slow_seconds: slow.value }))
    await focus(); await load(); scroll('practice')
  })
}
async function reopen(id) {
  await action(async () => {
    essay.value = null; review.value = null; assign(await study(`/runs/${id}`)); await focus(); scroll('practice')
  })
}
async function answer() {
  await action(async () => {
    const number = first.value.number
    assign(await study(`/runs/${run.value.id}/answers`, 'POST', { number, chosen: chosen.value, guessed: guessed.value }))
    review.value = null; await focus()
  })
}
async function finish() {
  await action(async () => { assign(await study(`/runs/${run.value.id}/finish`, 'PUT')); await load() })
}
function scroll(id) { window.requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView({ block: 'start' })) }
async function readFile(event) {
  const file = event.target.files[0]
  if (!file) return
  if (file.size > 3 * 1024 * 1024) { error.value = '练习资料文件最多 3 MiB'; return }
  importText.value = await file.text()
}
async function add() {
  await action(async () => {
    const data = JSON.parse(importText.value.replace(/^\uFEFF/, ''))
    if (data.region !== region) throw new Error('资料地区与当前入口不一致，请到对应地区导入')
    const result = await study(`/${target.value}`, 'POST', data)
    variant.value = ''; await load(); message.value = result.created === false ? '该卷已存在，未重复导入' : '已导入本地资料'
    importText.value = ''
  })
}
async function openEssay(id) {
  await action(async () => {
    run.value = null; review.value = null; essay.value = await study(`/essays/${id}`); essayText.value = essay.value.answer; scroll('essay')
  })
}
async function saveEssay() {
  await action(async () => {
    essay.value = await study(`/essays/${essay.value.id}/answer`, 'PUT', { answer: essayText.value })
    review.value = null; message.value = '申论作答已保存'
  })
}
async function makeReview(path) { await action(async () => { review.value = await study(path); scroll('review') }) }
async function copyReview() {
  await action(async () => {
    if (!navigator.clipboard) throw new Error('此浏览器不能自动复制，可手动选中下方文本')
    await navigator.clipboard.writeText(review.value.text); message.value = '复盘材料已复制，未发送'
  })
}
onMounted(() => action(load))
</script>

<template>
  <div class="study-page">
    <header class="study-heading"><RouterLink to="/">← 我的两场考试</RouterLink><h1>{{ regionName(region) }} · 练习</h1><p>限时做题，记录错题、蒙对和超时；申论作答只保存在本机。</p></header>
    <div class="study-status"><p v-if="error" class="study-error" role="alert">{{ error }}</p><p v-if="message" class="study-message" role="status">{{ message }}</p></div>
    <section class="study-card">
      <div class="study-between"><h2>行测试卷</h2><span class="study-chip">无可靠答案不计入正确率</span></div>
      <div class="study-controls">
        <label>卷别<select v-model="variant" @change="action(load)"><option value="">全部卷别</option><option v-for="v in variants" :key="v" :value="v">{{ v }}</option></select></label>
        <label>练习时长（分钟）<input v-model.number="minutes" type="number" min="1" max="180"></label>
        <label>单题超时（秒）<input v-model.number="slow" type="number" min="1" max="3600"></label>
      </div>
      <p v-if="!packs.length" class="study-subtle">这里还没有符合条件的试卷。可在下方导入有权使用的资料。</p>
      <article v-for="p in packs" :key="p.id" class="study-row" :data-testid="`pack-${p.id}`">
        <div><strong>{{ p.title }}</strong><p class="study-subtle">{{ p.year ?? '年度未知' }} · 行测 · {{ p.variant || '卷别未知' }} · {{ materialKind(p.kind) }} · 已核对 {{ p.verified }}/{{ p.count }} 题<br>{{ p.source }}</p></div>
        <button class="primary" :disabled="busy || !Number.isInteger(minutes) || minutes < 1 || minutes > 180 || !Number.isInteger(slow) || slow < 1 || slow > 3600" @click="begin(p.id)">开始限时练习</button>
      </article>
    </section>
    <section v-if="run" id="practice" class="study-card">
      <div class="study-between"><h2>{{ run.title }}</h2><span class="study-chip" data-testid="timer">{{ run.closed ? '已结束' : `剩余 ${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, '0')}` }}</span></div>
      <p>{{ materialKind(run.kind) }} · 已答 {{ Object.keys(run.attempts).length }}/{{ run.questions.length }} · <strong data-testid="score">答对 {{ run.correct }} / 已判 {{ run.graded }}</strong></p>
      <form v-if="canAnswer" class="study-form" @submit.prevent="answer">
        <h3 data-testid="question">第 {{ first.number }} 题 · {{ first.prompt }}</h3><p class="study-subtle">{{ first.source }}</p>
        <fieldset class="study-options"><legend>选择答案</legend><label v-for="(value, letter) in first.options" :key="letter"><input v-model="chosen" type="radio" name="choice" :value="letter"> {{ letter }}. {{ value }}</label></fieldset>
        <label class="study-check"><input v-model="guessed" type="checkbox" name="guessed"> 这道题我是蒙的</label>
        <div class="study-actions"><button class="primary" :disabled="busy || !chosen">提交答案</button><button type="button" :disabled="busy" @click="finish">结束练习</button></div>
      </form>
      <button v-else-if="!run.closed" :disabled="busy" @click="finish">结束并保存练习</button>
      <h3>已保存作答</h3>
      <details v-for="a in run.attempts" :key="a.number" :data-testid="`attempt-${a.number}`">
        <summary>第 {{ a.number }} 题 · {{ a.correct === null ? '答案待核对' : a.correct ? '答对' : '答错' }} · {{ a.seconds }} 秒 <span v-for="tag in a.tags.filter(t => t !== '答案待核对')" :key="tag" class="study-chip">{{ tag }}</span></summary>
        <p>{{ a.prompt }}</p><p>所选：{{ a.chosen }}；参考答案：{{ a.reference || '待核对' }}</p><p v-if="a.explanation">{{ a.explanation }}</p><p class="study-subtle">出处：{{ a.source }}</p>
      </details>
      <button :disabled="busy || !Object.values(run.attempts).some(a => a.tags.length)" @click="makeReview(`/runs/${run.id}/review`)">整理行测复盘材料</button>
    </section>
    <section class="study-card"><h2>练习记录</h2><p v-if="!runs.length" class="study-subtle">暂无练习记录。</p><div class="study-row" v-for="r in runs" :key="r.id"><span>{{ r.title }} · {{ dateText(r.started) }} · {{ materialKind(r.kind) }}</span><button :disabled="busy" @click="reopen(r.id)">打开练习记录</button></div></section>
    <section class="study-card"><h2>申论练习</h2><p v-if="!essays.length" class="study-subtle">暂无材料，可使用下方的申论 JSON 导入。</p><div class="study-row" v-for="e in essays" :key="e.id"><span>{{ e.title }} · {{ materialKind(e.kind) }}</span><button :disabled="busy" @click="openEssay(e.id)">阅读材料并作答</button></div></section>
    <section v-if="essay" id="essay" class="study-card">
      <h2>{{ essay.title }}</h2><p class="study-subtle">{{ materialKind(essay.kind) }} · 出处：{{ essay.source }}</p>
      <details open v-for="(text, i) in essay.materials" :key="i"><summary>材料 {{ i + 1 }}</summary><p class="study-pre">{{ text }}</p></details>
      <p class="study-pre"><strong>题目：</strong>{{ essay.question }}</p>
      <form class="study-form" @submit.prevent="saveEssay"><label>我的申论作答<textarea v-model="essayText" name="essay-answer" rows="7" maxlength="12000"></textarea></label><div class="study-actions"><button class="primary" :disabled="busy">保存申论作答</button><button type="button" :disabled="busy || !essay.answer?.trim() || essayText !== essay.answer" @click="makeReview(`/essays/${essay.id}/review`)">整理材料对照点评提示词</button></div></form>
    </section>
    <section v-if="review" id="review" class="study-card"><h2>复盘材料</h2><p>{{ review.notice }}</p><label class="study-form">可复制到如意（请自行确认材料允许分享）<textarea :value="review.text" readonly rows="10" name="review-text"></textarea></label><button :disabled="busy" @click="copyReview">复制复盘材料</button></section>
    <section class="study-card"><h2>导入个人资料</h2>
      <form class="study-form" @submit.prevent="add"><label>资料类型<select v-model="target" name="import-type"><option value="packs">行测试卷 JSON</option><option value="essays">申论材料 JSON</option></select></label>
        <p class="study-subtle"><a :href="`/examples/${region}-${target === 'packs' ? 'practice' : 'essay'}.json`" download>下载该地区的格式示例（测试材料，非真题）</a></p>
        <label>选择本地文件<input type="file" accept=".json,application/json" @change="readFile"></label><label>或粘贴 JSON<textarea v-model="importText" name="import-json" rows="5" required></textarea></label><button class="primary" :disabled="busy || !importText.trim()">导入所选资料</button>
      </form>
    </section>
  </div>
</template>
