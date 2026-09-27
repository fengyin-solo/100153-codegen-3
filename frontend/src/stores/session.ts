import { defineStore } from 'pinia'

import { fetchJson } from '@/api/client'

type DutyBoard = {
  current_shift: Record<string, unknown> | null
  shift: string
  handover_progress: string
  todo_count: number
}

export const useSessionStore = defineStore('session', {
  state: () => ({
    operator: '值班管理员',
    shiftLabel: '暂无交接记录',
    scope: '气象观测站网运维平台',
    handoverProgress: '',
  }),
  getters: {
    canOperate: (state) => state.operator.length > 0,
  },
  actions: {
    setShift(label: string) {
      this.shiftLabel = label
    },
    /** 从值班栏看板同步当前班次与交接进度，确认完成后回到值班页会再次拉取。 */
    async syncDuty() {
      try {
        const board = await fetchJson<DutyBoard>('/api/duty/board')
        this.shiftLabel = board.shift || '暂无交接记录'
        this.handoverProgress = board.handover_progress || ''
      } catch {
        this.shiftLabel = '值班信息读取失败'
        this.handoverProgress = ''
      }
    },
  },
})
