<template>
  <section class="page" data-module="duty-review">
    <header class="page-head">
      <div>
        <h2>接班确认</h2>
        <p class="page-desc">
          班次「{{ shift?.班次 ?? '…' }}」：{{ shift?.交班班组 }}（{{ shift?.交班人 }}）向
          {{ shift?.接班班组 || shift?.交班班组 }}（{{ shift?.接班人 }}）交接。逐条填写确认说明或退回原因后一次提交，
          一条不合格不会拖累整批。
        </p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" to="/duty">返回值班页</RouterLink>
      </div>
    </header>

    <div v-if="loadError" class="error-banner">{{ loadError }}</div>

    <template v-else-if="shift">
      <div class="stat-row">
        <article class="stat-card">
          <span class="stat-label">交接进度</span>
          <strong class="stat-value">{{ shift.processed }}/{{ shift.total }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">回执状态</span>
          <strong class="stat-value">{{ shift.status }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">交班时刻</span>
          <strong class="stat-value time">{{ shift.交班时刻 }}</strong>
        </article>
      </div>

      <div v-if="batchMessage" :class="['error-banner', batchOk ? 'ok' : '']">
        {{ batchMessage }}
        <span v-if="allDone">正在返回值班页刷新…</span>
      </div>

      <table class="data-table review-table">
        <thead>
          <tr>
            <th style="width: 36%">交接事项（未办结）</th>
            <th style="width: 14%">来源班组</th>
            <th style="width: 16%">处理结果</th>
            <th style="width: 26%">原因（逐条必填）</th>
            <th style="width: 8%">提交回执</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in shift.items" :key="String(item.id)" :class="{ 'is-done': !isPending(item) }">
            <td>{{ item.事项内容 }}</td>
            <td>{{ item.来源班组 }}</td>
            <td>
              <template v-if="isPending(item)">
                <label class="radio-line">
                  <input v-model="decisions[item.id].action" type="radio" value="confirm" />确认接收
                </label>
                <label class="radio-line">
                  <input v-model="decisions[item.id].action" type="radio" value="return" />退回
                </label>
              </template>
              <span v-else :class="['status-tag', item.result === '已确认' ? 'done' : 'rejected']">{{ item.result }}</span>
            </td>
            <td>
              <textarea
                v-if="isPending(item)"
                v-model="decisions[item.id].reason"
                rows="2"
                :placeholder="decisions[item.id].action === 'return' ? '写清退回原因，事项将回到来源班组待办' : '写清确认说明，事项将转入接班班组待办'"
              />
              <span v-else class="reason-text">{{ item.处理原因 }}<br /><small>{{ item.处理时刻 }}</small></span>
            </td>
            <td>
              <span v-if="rowMessages[item.id]" :class="rowMessages[item.id].ok ? 'ok-text' : 'error-text'">
                {{ rowMessages[item.id].message }}
              </span>
              <span v-else-if="!isPending(item)" class="ok-text">已保留</span>
            </td>
          </tr>
        </tbody>
      </table>

      <footer class="review-foot">
        <RouterLink class="btn ghost" to="/duty">稍后处理</RouterLink>
        <button class="btn primary" type="button" :disabled="submitting || pendingCount === 0" @click="submitReview">
          {{ submitting ? '提交中…' : `一次提交确认/退回（待处理 ${pendingCount} 条）` }}
        </button>
      </footer>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Item = {
  id: number
  事项内容: string
  来源班组: string
  result: string
  处理原因: string
  处理时刻: string | null
}
type ShiftDetail = {
  id: number
  班次: string
  交班班组: string
  接班班组: string
  交班人: string
  接班人: string
  交班时刻: string
  status: string
  processed: number
  total: number
  items: Item[]
}
type Decision = { action: 'confirm' | 'return'; reason: string }
type RowMessage = { ok: boolean; message: string }

const route = useRoute()
const router = useRouter()
const store = useSessionStore()

const shift = ref<ShiftDetail | null>(null)
const decisions = reactive<Record<number, Decision>>({})
const rowMessages = reactive<Record<number, RowMessage>>({})
const submitting = ref(false)
const loadError = ref('')
const batchMessage = ref('')
const batchOk = ref(false)
const allDone = ref(false)

const pendingItems = computed(() => (shift.value?.items ?? []).filter((item) => item.result === '待确认'))
const pendingCount = computed(() => pendingItems.value.length)

function isPending(item: Item) {
  return item.result === '待确认'
}

function seedDecisions(items: Item[]) {
  for (const item of items) {
    if (item.result === '待确认' && !decisions[item.id]) {
      decisions[item.id] = { action: 'confirm', reason: '' }
    }
  }
}

async function load() {
  loadError.value = ''
  const id = Number(route.params.id)
  try {
    const response = await request(`/api/duty/shifts/${id}`)
    if (response.status === 404) {
      throw new Error('该交接回执不存在或已被同班次新的交班回执替换')
    }
    if (!response.ok) {
      throw new Error('交接回执读取失败')
    }
    const detail = (await response.json()) as ShiftDetail
    shift.value = detail
    seedDecisions(detail.items)
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : '交接回执读取失败'
  }
}

async function submitReview() {
  if (!shift.value) return
  const shiftId = shift.value.id
  submitting.value = true
  batchMessage.value = ''
  const payload = {
    decisions: pendingItems.value.map((item) => ({
      item_id: item.id,
      action: decisions[item.id].action,
      reason: decisions[item.id].reason.trim(),
    })),
  }
  try {
    const response = await request(`/api/duty/shifts/${shiftId}/review`, {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    const data = await response.json()
    if (!response.ok) {
      throw new Error(data.detail || '批量提交未被受理')
    }
    batchOk.value = data.failed === 0
    batchMessage.value = data.message
    allDone.value = Boolean(data.all_done)
    for (const result of data.results as Array<{ item_id: number; ok: boolean; message: string }>) {
      rowMessages[result.item_id] = { ok: result.ok, message: result.message }
    }
    // 服务端逐条落库：无论是否整批完成，都重新拉取，已处理条目原样保留
    await load()
    await store.syncDuty()
    if (allDone.value) {
      // 确认完成：回到值班页刷新，班次与交接进度同步
      setTimeout(() => {
        void router.push('/duty')
      }, 1200)
    }
  } catch (error) {
    batchOk.value = false
    batchMessage.value = error instanceof Error ? error.message : '批量提交失败'
  } finally {
    submitting.value = false
  }
}

onMounted(load)
</script>
