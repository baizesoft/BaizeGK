<script setup>
import { onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { regionName, study, unpack } from '../api/study.js'
const region = useRoute().params.region
const tables = ref([]), selected = ref(''), results = ref(null), busy = ref(false), error = ref(''), notice = ref('')
const file = ref(null), year = ref(2027), announcement = ref(''), attachment = ref(''), kind = ref('official')
const area = ref(region === 'gz-tr' ? '铜仁' : ''), degree = ref(''), major = ref(''), age = ref('')
const areaOnly = ref(region === 'gz-tr')
const condition = ref(''), strictMajor = ref(false)
async function act(fn) { if (busy.value) return; busy.value = true; error.value = ''; notice.value = ''; try { await fn() } catch (e) { error.value = e.message } finally { busy.value = false } }
async function load() { tables.value = (await study(`/jobs?region=${region}`)).items }
async function search(page = 1) {
  if (!selected.value) { results.value = null; return }
  const q = new URLSearchParams({ area: area.value.trim(), major: major.value.trim(), page })
  if (areaOnly.value) q.set('area_only', 'true')
  if (condition.value.trim()) q.set('condition', condition.value.trim())
  if (strictMajor.value) q.set('strict_major', 'true')
  if (degree.value) q.set('degree', degree.value)
  if (age.value !== '') q.set('age', age.value)
  results.value = await study(`/jobs/${selected.value}?${q}`)
}
async function add() {
  await act(async () => {
    const current = file.value
    const content = await unpack(current)
    const out = await study('/jobs/import', 'POST', { content, filename: current.name, region, year: year.value,
      announcement: announcement.value, file_url: attachment.value, kind: kind.value })
    await load(); selected.value = out.id; await search(); notice.value = `职位表已保存 · ${out.count} 行`
  })
}
onMounted(() => act(load))
</script>

<template>
  <div class="study-page">
    <header class="study-heading"><RouterLink to="/">← 我的两场考试</RouterLink><h1>{{ regionName(region) }} · 职位表</h1><p>按表中明确条件初筛，不代表报考资格。条件含糊时保留原文，标作「需核实」。</p></header>
    <p v-if="error" class="study-error" role="alert">{{ error }}</p><p v-if="notice" role="status" class="study-message">{{ notice }}</p>
    <section class="study-card"><h2>筛选已导入表格</h2>
      <form class="study-form" @submit.prevent="act(() => search())">
        <label>职位表<select v-model="selected" name="job-table" @change="results = null"><option value="">选择一份本地表</option><option v-for="t in tables" :key="t.id" :value="t.id">{{ t.year }} · {{ t.filename }} · {{ t.reference_only ? '历史／测试参考' : '本轮资料（不代表开放报名）' }}</option></select></label>
        <div class="study-controls"><label>{{ areaOnly ? '考区或地区包含' : '地区或单位包含' }}<input v-model="area" name="job-area"></label><label>学历<select v-model="degree" name="job-degree"><option value="">不填</option><option>专科</option><option>本科</option><option>硕士</option><option>博士</option></select></label><label>专业全称<input v-model="major" name="job-major"></label><label>年龄（初筛）<input v-model.number="age" name="job-age" type="number" min="16" max="75"></label></div>
        <label class="study-check"><input v-model="areaOnly" name="job-area-only" type="checkbox"> 只按职位表的考区／地区筛选，不匹配单位名称</label>
        <label>其他条件原文关键词<input v-model.trim="condition" name="job-condition" placeholder="例如：基层工作经历"></label>
        <label class="study-check"><input v-model="strictMajor" type="checkbox" :disabled="!major.trim()"> 仅保留专业明确匹配或不限的职位（可能漏掉专业类岗位）</label>
        <button class="primary" :disabled="busy || !selected">筛选职位</button>
      </form>
    </section>
    <section v-if="results" class="study-card" data-testid="job-results"><h2>筛选结果 · {{ results.total }} 行</h2>
      <p v-if="results.table.reference_only" class="study-banner">历史／测试参考，不是本轮可报岗位。</p>
      <p class="study-subtle">{{ results.notice }}</p>
      <p><a :href="results.table.announcement" target="_blank" rel="noopener noreferrer">公告原文</a><template v-if="results.table.file_url"> · <a :href="results.table.file_url" target="_blank" rel="noopener noreferrer">表格原件</a></template> · {{ results.table.filename }}</p>
      <p v-if="!results.items.length">没有符合已填写条件的记录。</p>
      <details v-for="r in results.items" :key="r.sheet + ':' + r.row" class="study-job" :data-row="r.row">
        <summary><strong>{{ r.title }}</strong> · {{ r.area || r.unit || '地区未知' }} · {{ r.status }} · {{ r.sheet }}第 {{ r.row }} 行</summary>
        <p>单位：{{ r.unit || '未知' }} · 职位代码：{{ r.code || '表内未识别' }} · 表列类别：{{ r.variant || '未知' }}</p><p>学历：{{ r.degree || '表内未识别' }}｜专业：{{ r.major || '表内未识别' }}｜年龄：{{ r.age || '见公告' }}</p>
        <p v-if="r.reasons.length">待核实：{{ r.reasons.join('；') }}</p><p v-for="(v, k) in r.conditions" :key="k" class="study-pre">{{ k }}：{{ v }}</p>
      </details>
      <div class="study-actions"><button :disabled="busy || results.page === 1" @click="act(() => search(results.page - 1))">上一页</button><span>第 {{ results.page }} 页</span><button :disabled="busy || results.page * results.page_size >= results.total" @click="act(() => search(results.page + 1))">下一页</button></div>
    </section>
    <section class="study-card"><h2>导入职位表（XLS、XLSX 或 CSV）</h2><p class="study-subtle">先从公告下载官方附件。仅导入本地；不需要提供身份证号或证件。</p>
      <form class="study-form" @submit.prevent="add"><div class="study-controls"><label>招录年度<input v-model.number="year" name="job-year" type="number" min="2000" max="2100" required></label><label>资料类别<select v-model="kind" name="job-kind"><option value="official">官方职位表</option><option value="fixture">测试材料</option></select></label></div>
        <label>官方公告地址<input v-model.trim="announcement" name="job-announcement" type="url" required></label><label>官方附件地址<input v-model.trim="attachment" name="job-attachment" type="url" :required="kind === 'official'"></label>
        <label>本地表格<input type="file" name="job-file" accept=".xls,.xlsx,.csv" required @change="file = $event.target.files[0]"></label><button class="primary" :disabled="busy || !file">导入并查看职位表</button>
      </form>
    </section>
  </div>
</template>
