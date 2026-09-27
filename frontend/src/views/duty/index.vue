<template>
  <section class="page" data-module="duty">
    <header class="page-head">
      <div>
        <h2>值班班组交接班</h2>
        <p class="page-desc">按班次登记值班班组、交班人与接班人，未办结事项挂为交接事项，接班人一次提交多条确认或退回结论。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="showCreate = !showCreate">登记交班</button>
        <button class="btn" type="button" @click="reload">刷新值班栏</button>
        <button class="btn" type="button" @click="exportRows">导出交接清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article class="stat-card">
        <span class="stat-label">当前班次</span>
        <strong class="stat-value">{{ currentShift }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">交接进度</span>
        <strong class="stat-value">{{ currentProgress }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">待确认事项</span>
        <strong class="stat-value">{{ waitingCount }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">退回待办</span>
        <strong class="stat-value">{{ rejectedCount }}</strong>
      </article>
    </div>

    <form v-if="showCreate" class="panel" @submit.prevent="submitCreate">
      <h3 class="panel-title">登记交班</h3>
      <div class="panel-grid">
        <label v-for="field in createFields" :key="field" class="filter-item">
          <span>{{ field }}（必填）</span>
          <input v-model="createForm[field]" :placeholder="`填写${field}`" />
        </label>
      </div>
      <label class="filter-item block">
        <span>未办结事项（每行一条，挂为交接事项）</span>
        <textarea v-model="createItems" rows="3" placeholder="例如：3号站传输中断待跟进"></textarea>
      </label>
      <div class="panel-actions">
        <button class="btn primary" type="submit">提交登记</button>
        <button class="btn ghost" type="button" @click="showCreate = false">取消</button>
      </div>
    </form>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>班次/班组</span>
        <input v-model="keyword" placeholder="按班次或值班班组检索" />
      </label>
      <label class="filter-item">
        <span>交接状态</span>
        <select v-model="statusFilter">
          <option value="">全部</option>
          <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td>{{ row['班次'] }}</td>
          <td>{{ row['值班班组'] }}</td>
          <td>{{ row['交班人'] }}</td>
          <td>{{ row['接班人'] }}</td>
          <td>{{ row['交接进度'] }}</td>
          <td>{{ todoText(row) }}</td>
          <td>{{ row.status }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openReceipt(row)">交接回执</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无值班交接记录，可先登记交班</td>
        </tr>
      </tbody>
    </table>

    <section v-if="receiptEntry" class="panel">
      <h3 class="panel-title">
        交接回执：{{ receiptEntry['班次'] }} · {{ receiptEntry['值班班组'] }}（接班人 {{ receiptEntry['接班人'] }}）
      </h3>
      <table class="data-table">
        <thead>
          <tr><th>交接事项</th><th>当前状态</th><th>结论</th><th>逐条原因（必填）</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in receiptEntry['交接事项']" :key="item['事项id']">
            <td>{{ item['内容'] }}</td>
            <td>{{ item['状态'] }}</td>
            <template v-if="item['状态'] === '待确认'">
              <td>
                <select v-model="lineOf(item['事项id']).结论">
                  <option value="确认">确认</option>
                  <option value="退回">退回</option>
                </select>
              </td>
              <td><input v-model="lineOf(item['事项id']).原因" placeholder="写清确认或退回的原因" /></td>
            </template>
            <template v-else>
              <td>—</td>
              <td>{{ item['原因'] || '—' }}</td>
            </template>
          </tr>
        </tbody>
      </table>
      <div class="panel-actions">
        <button class="btn primary" type="button" :disabled="!receiptLines.length" @click="submitReceipt">
          提交回执（{{ receiptLines.length }} 条待确认）
        </button>
        <button class="btn ghost" type="button" @click="receiptEntry = null">关闭</button>
      </div>
      <p v-if="!receiptLines.length" class="page-desc">该班次的交接事项已全部办结，没有可回执的条目。</p>
    </section>

    <footer class="page-foot">
      <span>共 {{ total }} 条值班交接记录</span>
      <span v-if="message" :class="messageOk ? '' : 'error-text'">{{ message }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type HandoverItem = { 事项id: number; 内容: string; 状态: string; 原因: string; 批次: number }
type DutyRow = {
  id: number
  status: string
  班次: string
  值班班组: string
  交班人: string
  接班人: string
  交接进度: string
  待办事项: string[]
  交接事项: HandoverItem[]
}
type ReceiptLine = { 事项id: number; 结论: string; 原因: string }

const ENDPOINT = '/api/duty'
const columns = ['班次', '值班班组', '交班人', '接班人', '交接进度', '待办事项', '交接状态']
const statuses = ['待交班', '待确认', '已交接', '部分退回']
const createFields = ['班次', '值班班组', '交班人', '接班人']

const session = useSessionStore()
const rows = ref<DutyRow[]>([])
const total = ref(0)
const keyword = ref('')
const statusFilter = ref('')
const message = ref('')
const messageOk = ref(false)

const showCreate = ref(false)
const createForm = ref<Record<string, string>>({})
const createItems = ref('')

const receiptEntry = ref<DutyRow | null>(null)
const receiptLines = ref<ReceiptLine[]>([])

const latestRow = computed(() => [...rows.value].sort((a, b) => b.id - a.id)[0])
const currentShift = computed(() => latestRow.value?.['班次'] ?? '—')
const currentProgress = computed(() => latestRow.value?.['交接进度'] ?? '0/0')
const waitingCount = computed(() =>
  rows.value.reduce((sum, row) => sum + (row['交接事项'] ?? []).filter((item) => item['状态'] === '待确认').length, 0),
)
const rejectedCount = computed(() =>
  rows.value.reduce((sum, row) => sum + (row['待办事项'] ?? []).length, 0),
)

function todoText(row: DutyRow) {
  const todos = row['待办事项'] ?? []
  return todos.length ? todos.join('；') : '—'
}

function lineOf(itemId: number): ReceiptLine {
  let line = receiptLines.value.find((item) => item['事项id'] === itemId)
  if (!line) {
    line = { 事项id: itemId, 结论: '确认', 原因: '' }
    receiptLines.value.push(line)
  }
  return line
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function openReceipt(row: DutyRow) {
  receiptEntry.value = row
  receiptLines.value = (row['交接事项'] ?? [])
    .filter((item) => item['状态'] === '待确认')
    .map((item) => ({ 事项id: item['事项id'], 结论: '确认', 原因: '' }))
  message.value = ''
}

async function submitCreate() {
  message.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({
        values: {
          ...createForm.value,
          交接事项: createItems.value.split('\n').map((text) => text.trim()).filter(Boolean),
        },
      }),
    })
    const payload = await response.json()
    message.value = payload.message ?? '登记结果未知'
    messageOk.value = Boolean(payload.ok)
    if (payload.ok) {
      showCreate.value = false
      createForm.value = {}
      createItems.value = ''
      await reload()
    }
  } catch (error) {
    messageOk.value = false
    message.value = error instanceof Error ? error.message : '交班登记失败'
  }
}

async function submitReceipt() {
  const entry = receiptEntry.value
  if (!entry) return
  message.value = ''
  try {
    const response = await request(`${ENDPOINT}/${entry.id}/receipt`, {
      method: 'POST',
      body: JSON.stringify({ values: { items: receiptLines.value } }),
    })
    const payload = await response.json()
    message.value = payload.message ?? '回执结果未知'
    messageOk.value = Boolean(payload.ok)
    if (payload.ok) {
      receiptEntry.value = null
      await reload()
    }
  } catch (error) {
    messageOk.value = false
    message.value = error instanceof Error ? error.message : '回执提交失败'
  }
}

async function reload() {
  message.value = ''
  const query = new URLSearchParams()
  if (keyword.value) query.set('keyword', keyword.value)
  if (statusFilter.value) query.set('status', statusFilter.value)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('值班交接列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    // 值班栏同步：班次与交接进度跟着最新一条交接记录走
    session.setDuty(currentShift.value, currentProgress.value)
  } catch (error) {
    messageOk.value = false
    message.value = error instanceof Error ? error.message : '值班交接列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.panel { background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 12px; margin-bottom: 12px; }
.panel-title { margin: 0 0 10px; font-size: 14px; }
.panel-grid { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 10px; }
.panel-actions { display: flex; gap: 8px; margin-top: 10px; }
.filter-item.block { display: block; }
.filter-item.block textarea { width: 100%; }
</style>
