<template>
  <section class="page" data-module="duty">
    <header class="page-head">
      <div>
        <h2>值班交接班</h2>
        <p class="page-desc">按班次登记交班班组、交班人与接班人，把未办结事项挂成交接事项；同一班次重复交班以最后一次回执为准。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="reload">刷新值班信息</button>
      </div>
    </header>

    <div class="stat-row">
      <article class="stat-card">
        <span class="stat-label">当前班次</span>
        <strong class="stat-value">{{ board.shift || '暂无交接记录' }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">交接进度</span>
        <strong class="stat-value">{{ board.handover_progress || '—' }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">班组待办（未办结）</span>
        <strong class="stat-value">{{ board.todo_count }}</strong>
      </article>
    </div>

    <div class="duty-grid">
      <section class="panel">
        <h3 class="panel-title">交班登记</h3>
        <form class="handover-form" @submit.prevent="submitHandover">
          <div class="form-grid">
            <label class="form-item">
              <span>班次 *</span>
              <input v-model="form.shift" placeholder="如 白班 2026-09-27" />
            </label>
            <label class="form-item">
              <span>交班班组 *</span>
              <input v-model="form.team" list="team-options" placeholder="如 甲组" />
            </label>
            <label class="form-item">
              <span>交班人 *</span>
              <input v-model="form.handover_person" placeholder="交班值班员" />
            </label>
            <label class="form-item">
              <span>接班人 *</span>
              <input v-model="form.receiver_person" placeholder="接班值班员" />
            </label>
            <label class="form-item">
              <span>接班班组（留空同交班班组）</span>
              <input v-model="form.receiver_team" list="team-options" placeholder="默认转入交班班组" />
            </label>
          </div>
          <datalist id="team-options">
            <option value="甲组" />
            <option value="乙组" />
          </datalist>

          <div class="pick-head">
            <span>挂起未办结事项（勾选后进入交接，班组待办中暂时置为“交接中”）</span>
            <button class="link" type="button" @click="toggleAll">{{ allPicked ? '全部取消' : '全选当前班组' }}</button>
          </div>
          <ul class="pick-list">
            <li v-for="todo in visibleTodos" :key="String(todo.id)">
              <label class="pick-line">
                <input v-model="pickedIds" type="checkbox" :value="Number(todo.id)" />
                <span class="pick-tag">{{ todo.所属班组 }}</span>
                <span>{{ todo.事项内容 }}</span>
                <span class="pick-no">{{ todo.事项编号 }}</span>
              </label>
            </li>
            <li v-if="!visibleTodos.length" class="empty-inline">该班组当前没有未办结事项，可在下方现场补充</li>
          </ul>

          <div class="pick-head">
            <span>现场补充交接事项</span>
            <button class="link" type="button" @click="extraItems.push('')">再加一条</button>
          </div>
          <ul class="extra-list">
            <li v-for="(_, index) in extraItems" :key="index" class="extra-line">
              <input v-model="extraItems[index]" placeholder="写清未办结事项与当前进展" />
              <button class="link danger" type="button" @click="extraItems.splice(index, 1)">移除</button>
            </li>
            <li v-if="!extraItems.length" class="empty-inline">暂无补充事项</li>
          </ul>

          <div class="form-foot">
            <button class="btn primary" type="submit" :disabled="submitting">{{ submitting ? '提交中…' : '提交交班回执' }}</button>
            <span v-if="formMessage" :class="formOk ? 'ok-text' : 'error-text'">{{ formMessage }}</span>
          </div>
        </form>
      </section>

      <section class="panel">
        <h3 class="panel-title">交接回执</h3>
        <table class="data-table">
          <thead>
            <tr><th>班次</th><th>交班→接班</th><th>进度</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="shift in shifts" :key="String(shift.id)">
              <td>{{ shift.班次 }}</td>
              <td>{{ shift.交班班组 }}·{{ shift.交班人 }} → {{ shift.接班班组 || shift.交班班组 }}·{{ shift.接班人 }}</td>
              <td>
                <span :class="['status-tag', statusClass(shift.status)]">{{ shift.status }}</span>
                {{ shift.processed }}/{{ shift.total }}
              </td>
              <td class="row-actions">
                <RouterLink class="link" :to="`/duty/review/${shift.id}`">
                  {{ shift.processed < shift.total ? '去确认' : '查看回执' }}
                </RouterLink>
              </td>
            </tr>
            <tr v-if="!shifts.length">
              <td colspan="4" class="empty-state">还没有交接回执，先在左侧登记一次交班</td>
            </tr>
          </tbody>
        </table>
      </section>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Todo = {
  id: number
  事项编号: string
  事项内容: string
  所属班组: string
}
type Shift = {
  id: number
  班次: string
  交班班组: string
  接班班组: string
  交班人: string
  接班人: string
  status: string
  processed: number
  total: number
}
type Board = {
  shift: string
  handover_progress: string
  todo_count: number
}

const store = useSessionStore()

const board = ref<Board>({ shift: '', handover_progress: '', todo_count: 0 })
const todos = ref<Todo[]>([])
const shifts = ref<Shift[]>([])
const pickedIds = ref<number[]>([])
const extraItems = ref<string[]>([])
const submitting = ref(false)
const formMessage = ref('')
const formOk = ref(false)

const form = reactive({
  shift: '',
  team: '',
  handover_person: '',
  receiver_person: '',
  receiver_team: '',
})

const visibleTodos = computed(() =>
  form.team.trim() ? todos.value.filter((todo) => todo.所属班组 === form.team.trim()) : todos.value,
)
const allPicked = computed(
  () => visibleTodos.value.length > 0 && visibleTodos.value.every((todo) => pickedIds.value.includes(todo.id)),
)

function toggleAll() {
  if (allPicked.value) {
    const ids = new Set(visibleTodos.value.map((todo) => todo.id))
    pickedIds.value = pickedIds.value.filter((id) => !ids.has(id))
  } else {
    pickedIds.value = Array.from(new Set([...pickedIds.value, ...visibleTodos.value.map((todo) => todo.id)]))
  }
}

function statusClass(status: string) {
  if (status === '交接完成') return 'done'
  if (status === '部分确认') return 'partial'
  return 'pending'
}

async function reload() {
  formMessage.value = ''
  try {
    const [boardResp, todoResp, shiftResp] = await Promise.all([
      request('/api/duty/board'),
      request('/api/duty/todos'),
      request('/api/duty/shifts'),
    ])
    if (!boardResp.ok || !todoResp.ok || !shiftResp.ok) {
      throw new Error('值班数据读取失败')
    }
    board.value = await boardResp.json()
    todos.value = (await todoResp.json()).items ?? []
    shifts.value = (await shiftResp.json()).items ?? []
    await store.syncDuty()
  } catch (error) {
    formOk.value = false
    formMessage.value = error instanceof Error ? error.message : '值班数据读取失败'
  }
}

async function submitHandover() {
  submitting.value = true
  formMessage.value = ''
  try {
    const payload = {
      shift: form.shift.trim(),
      team: form.team.trim(),
      handover_person: form.handover_person.trim(),
      receiver_person: form.receiver_person.trim(),
      receiver_team: form.receiver_team.trim(),
      item_ids: pickedIds.value,
      extra_items: extraItems.value.map((item) => item.trim()).filter(Boolean),
    }
    const response = await request('/api/duty/shifts', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    const data = await response.json()
    formOk.value = Boolean(data.ok)
    formMessage.value = data.message || '交班登记失败'
    if (data.ok) {
      Object.assign(form, { shift: '', team: '', handover_person: '', receiver_person: '', receiver_team: '' })
      pickedIds.value = []
      extraItems.value = []
      await reload()
    }
  } catch (error) {
    formOk.value = false
    formMessage.value = error instanceof Error ? error.message : '交班登记请求失败'
  } finally {
    submitting.value = false
  }
}

onMounted(reload)
</script>
