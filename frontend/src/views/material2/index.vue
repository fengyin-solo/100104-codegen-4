<template>
  <section class="page" data-module="material2">
    <header class="page-head">
      <div>
        <h2>养护材料管理</h2>
        <p class="page-desc">维护养护材料，支持勾选多条后整组出库、整组入库；出入库记录挂在材料编号下，盘点页与台账同源。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记养护材料</button>
        <button class="btn" type="button" :disabled="!selectedCount" @click="openOutbound">
          批量出库{{ selectedCount ? `（${selectedCount}）` : '' }}
        </button>
        <button class="btn" type="button" :disabled="!selectedCount" @click="openInbound">
          批量入库{{ selectedCount ? `（${selectedCount}）` : '' }}
        </button>
        <button class="btn" type="button" @click="exportRows">导出养护材料清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th class="check-col">
            <input type="checkbox" :checked="allSelected" title="全选本页" @change="toggleAll" />
          </th>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td class="check-col">
            <input
              type="checkbox"
              :checked="selected.has(row.id)"
              :title="`选择 ${row['材料编号']}`"
              @change="toggleRow(row.id)"
            />
          </td>
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openRecords(row)">出入库记录</button>
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无养护材料数据，可先登记养护材料</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条养护材料记录</span>
      <span v-if="noticeMessage" class="ok-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 批量出库：逐条填领用班组，领用日期全组统一 -->
    <div v-if="outboundVisible" class="modal-mask" @click.self="closeOutbound">
      <div class="modal-card">
        <div class="modal-head">
          <h3>批量出库</h3>
          <button class="link" type="button" @click="closeOutbound">关闭</button>
        </div>
        <p class="modal-tip">
          已选 {{ outboundLines.length }} 条材料，逐条填写出库数量与领用班组；不同规格型号的材料各自成单，不会合并。
        </p>
        <label class="filter-item modal-date">
          <span>领用日期（全组统一）</span>
          <input v-model="outboundDate" type="date" />
        </label>
        <table class="data-table">
          <thead>
            <tr>
              <th>材料编号</th>
              <th>材料名称</th>
              <th>规格型号</th>
              <th>当前存量</th>
              <th>出库数量</th>
              <th>领用班组</th>
              <th>处理结果</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="line in outboundLines" :key="line.材料编号">
              <td>{{ line.材料编号 }}</td>
              <td>{{ line.材料名称 }}</td>
              <td>{{ line.规格型号 }}</td>
              <td>{{ line.当前存量 }}</td>
              <td>
                <input
                  v-model.number="line.出库数量"
                  class="field-input num-input"
                  type="number"
                  min="1"
                  :disabled="line.state === 'ok'"
                />
              </td>
              <td>
                <input
                  v-model="line.领用班组"
                  class="field-input"
                  placeholder="如：桥梁一班"
                  :disabled="line.state === 'ok'"
                />
              </td>
              <td>
                <span v-if="line.state === 'ok'" class="tag-ok">✓ {{ line.message }}</span>
                <span v-else-if="line.state === 'fail'" class="tag-fail">✗ {{ line.message }}</span>
                <span v-else class="tag-muted">待提交</span>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="outboundError" class="error-text">{{ outboundError }}</p>
        <div class="modal-foot">
          <button class="btn ghost" type="button" @click="closeOutbound">关闭</button>
          <button
            v-if="hasOutboundFailed"
            class="btn"
            type="button"
            :disabled="submitting"
            @click="submitOutbound(true)"
          >
            仅重试失败项（{{ outboundFailedCount }}）
          </button>
          <button
            class="btn primary"
            type="button"
            :disabled="submitting || !outboundPendingCount"
            @click="submitOutbound(false)"
          >
            {{ submitting ? '提交中…' : `整组提交出库（${outboundPendingCount}）` }}
          </button>
        </div>
      </div>
    </div>

    <!-- 批量入库：受潮、已过期的材料单独挑出，不纳入本次入库 -->
    <div v-if="inboundVisible" class="modal-mask" @click.self="closeInbound">
      <div class="modal-card">
        <div class="modal-head">
          <h3>批量入库</h3>
          <button class="link" type="button" @click="closeInbound">关闭</button>
        </div>
        <p class="modal-tip">
          已选 {{ inboundLines.length }} 条材料，逐条填写入库数量并判定质检结果；受潮、已过期的材料会被单独挑出，不纳入本次入库。
        </p>
        <label class="filter-item modal-date">
          <span>入库日期（全组统一）</span>
          <input v-model="inboundDate" type="date" />
        </label>
        <table class="data-table">
          <thead>
            <tr>
              <th>材料编号</th>
              <th>材料名称</th>
              <th>规格型号</th>
              <th>当前存量</th>
              <th>入库数量</th>
              <th>质检结果</th>
              <th>处理结果</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="line in inboundAccepted" :key="line.材料编号">
              <td>{{ line.材料编号 }}</td>
              <td>{{ line.材料名称 }}</td>
              <td>{{ line.规格型号 }}</td>
              <td>{{ line.当前存量 }}</td>
              <td>
                <input
                  v-model.number="line.入库数量"
                  class="field-input num-input"
                  type="number"
                  min="1"
                  :disabled="line.state === 'ok'"
                />
              </td>
              <td>
                <select v-model="line.质检结果" class="field-input" :disabled="line.state === 'ok'">
                  <option v-for="option in qualityOptions" :key="option" :value="option">{{ option }}</option>
                </select>
              </td>
              <td>
                <span v-if="line.state === 'ok'" class="tag-ok">✓ {{ line.message }}</span>
                <span v-else-if="line.state === 'fail'" class="tag-fail">✗ {{ line.message }}</span>
                <span v-else class="tag-muted">待提交</span>
              </td>
            </tr>
            <tr v-if="!inboundAccepted.length">
              <td colspan="7" class="empty-state">本次没有质检合格、可以入库的材料</td>
            </tr>
          </tbody>
        </table>
        <template v-if="inboundRejected.length">
          <p class="modal-tip reject-tip">
            以下 {{ inboundRejected.length }} 条受潮或已过期，不纳入本次入库，请单独挑出另行处置：
          </p>
          <table class="data-table">
            <thead>
              <tr>
                <th>材料编号</th>
                <th>材料名称</th>
                <th>规格型号</th>
                <th>质检结果</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="line in inboundRejected" :key="line.材料编号">
                <td>{{ line.材料编号 }}</td>
                <td>{{ line.材料名称 }}</td>
                <td>{{ line.规格型号 }}</td>
                <td>
                  <select v-model="line.质检结果" class="field-input">
                    <option v-for="option in qualityOptions" :key="option" :value="option">{{ option }}</option>
                  </select>
                </td>
              </tr>
            </tbody>
          </table>
        </template>
        <p v-if="inboundError" class="error-text">{{ inboundError }}</p>
        <div class="modal-foot">
          <button class="btn ghost" type="button" @click="closeInbound">关闭</button>
          <button
            v-if="hasInboundFailed"
            class="btn"
            type="button"
            :disabled="submitting"
            @click="submitInbound(true)"
          >
            仅重试失败项（{{ inboundFailedCount }}）
          </button>
          <button
            class="btn primary"
            type="button"
            :disabled="submitting || !inboundPendingCount"
            @click="submitInbound(false)"
          >
            {{ submitting ? '提交中…' : `整组提交入库（${inboundPendingCount}）` }}
          </button>
        </div>
      </div>
    </div>

    <!-- 挂在材料编号下的出入库记录 -->
    <div v-if="recordsVisible" class="modal-mask" @click.self="recordsVisible = false">
      <div class="modal-card">
        <div class="modal-head">
          <h3>出入库记录 · {{ recordsFor?.['材料编号'] }}（{{ recordsFor?.['规格型号'] }}）</h3>
          <button class="link" type="button" @click="recordsVisible = false">关闭</button>
        </div>
        <table class="data-table">
          <thead>
            <tr>
              <th>记录号</th>
              <th>类型</th>
              <th>规格型号</th>
              <th>数量</th>
              <th>领用班组 / 质检结果</th>
              <th>日期</th>
              <th>结存</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="record in recordsRows" :key="String(record['记录号'])">
              <td>{{ record['记录号'] }}</td>
              <td>{{ record['类型'] }}</td>
              <td>{{ record['规格型号'] }}</td>
              <td>{{ record['数量'] }}</td>
              <td>{{ record['领用班组'] ?? record['质检结果'] ?? '—' }}</td>
              <td>{{ record['日期'] }}</td>
              <td>{{ record['结存'] }}</td>
            </tr>
            <tr v-if="!recordsRows.length">
              <td colspan="7" class="empty-state">该材料暂无出入库记录</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null> & { id: number }
type LineState = 'idle' | 'ok' | 'fail'

interface OutboundLine {
  材料编号: string
  材料名称: string
  规格型号: string
  当前存量: number
  出库数量: number
  领用班组: string
  state: LineState
  message: string
}

interface InboundLine {
  材料编号: string
  材料名称: string
  规格型号: string
  当前存量: number
  入库数量: number
  质检结果: string
  state: LineState
  message: string
}

interface BatchItemResult {
  材料编号: string
  ok: boolean
  message: string
  结存: number | null
}

interface BatchResult {
  ok: boolean
  message: string
  results: BatchItemResult[]
}

const ENDPOINT = '/api/material2'
const columns = ["材料编号", "材料名称", "规格型号", "适用场景", "存放料场", "最低保有量", "当前存量", "材料状态"]
const actions = ["申领材料", "采购入库", "停用材料"]
const qualityOptions = ["合格", "受潮", "已过期"]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const selected = ref<Set<number>>(new Set())
const submitting = ref(false)

const outboundVisible = ref(false)
const outboundDate = ref(today())
const outboundLines = ref<OutboundLine[]>([])
const outboundError = ref('')

const inboundVisible = ref(false)
const inboundDate = ref(today())
const inboundLines = ref<InboundLine[]>([])
const inboundError = ref('')

const recordsVisible = ref(false)
const recordsRows = ref<Record<string, string | number | null>[]>([])
const recordsFor = ref<Row | null>(null)

const stats = computed(() => [
  { label: '材料种类', value: total.value },
  { label: '不足材料', value: rows.value.filter((row) => row['材料状态'] === '不足').length },
  { label: '待采购材料', value: rows.value.filter((row) => row['材料状态'] === '待采购').length },
])

const selectedCount = computed(() => selected.value.size)
const allSelected = computed(() => rows.value.length > 0 && rows.value.every((row) => selected.value.has(row.id)))

const outboundPending = computed(() => outboundLines.value.filter((line) => line.state !== 'ok'))
const outboundPendingCount = computed(() => outboundPending.value.length)
const outboundFailedCount = computed(() => outboundLines.value.filter((line) => line.state === 'fail').length)
const hasOutboundFailed = computed(() => outboundFailedCount.value > 0)

const inboundAccepted = computed(() => inboundLines.value.filter((line) => line.质检结果 === '合格'))
const inboundRejected = computed(() => inboundLines.value.filter((line) => line.质检结果 !== '合格'))
const inboundPendingCount = computed(() => inboundAccepted.value.filter((line) => line.state !== 'ok').length)
const inboundFailedCount = computed(() => inboundAccepted.value.filter((line) => line.state === 'fail').length)
const hasInboundFailed = computed(() => inboundFailedCount.value > 0)

function today(): string {
  const now = new Date()
  const month = `${now.getMonth() + 1}`.padStart(2, '0')
  const day = `${now.getDate()}`.padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

function toggleRow(id: number) {
  if (selected.value.has(id)) {
    selected.value.delete(id)
  } else {
    selected.value.add(id)
  }
}

function toggleAll() {
  if (allSelected.value) {
    selected.value = new Set()
  } else {
    selected.value = new Set(rows.value.map((row) => row.id))
  }
}

function selectedRows(): Row[] {
  return rows.value.filter((row) => selected.value.has(row.id))
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '养护材料登记入口尚未接入审批流'
}

function openOutbound() {
  outboundLines.value = selectedRows().map((row) => ({
    材料编号: String(row['材料编号'] ?? ''),
    材料名称: String(row['材料名称'] ?? ''),
    规格型号: String(row['规格型号'] ?? ''),
    当前存量: Number(row['当前存量'] ?? 0),
    出库数量: 1,
    领用班组: '',
    state: 'idle',
    message: '',
  }))
  outboundDate.value = today()
  outboundError.value = ''
  outboundVisible.value = true
}

function closeOutbound() {
  outboundVisible.value = false
}

function openInbound() {
  inboundLines.value = selectedRows().map((row) => ({
    材料编号: String(row['材料编号'] ?? ''),
    材料名称: String(row['材料名称'] ?? ''),
    规格型号: String(row['规格型号'] ?? ''),
    当前存量: Number(row['当前存量'] ?? 0),
    入库数量: 1,
    质检结果: '合格',
    state: 'idle',
    message: '',
  }))
  inboundDate.value = today()
  inboundError.value = ''
  inboundVisible.value = true
}

function closeInbound() {
  inboundVisible.value = false
}

async function submitOutbound(onlyFailed: boolean) {
  outboundError.value = ''
  const targets = outboundLines.value.filter((line) => line.state !== 'ok' && (!onlyFailed || line.state === 'fail'))
  if (!targets.length) {
    outboundError.value = '没有待提交的出库行'
    return
  }
  submitting.value = true
  try {
    const payload = {
      领用日期: outboundDate.value,
      items: targets.map((line) => ({
        材料编号: line.材料编号,
        规格型号: line.规格型号,
        出库数量: line.出库数量,
        领用班组: line.领用班组,
      })),
    }
    const result = await postBatch<BatchResult>(`${ENDPOINT}/batch-outbound`, payload)
    for (const item of result.results) {
      const line = outboundLines.value.find((entry) => entry.材料编号 === item.材料编号 && entry.state !== 'ok')
      if (!line) continue
      line.state = item.ok ? 'ok' : 'fail'
      line.message = item.message
      if (item.ok && item.结存 !== null) {
        line.当前存量 = item.结存
      }
    }
    if (result.results.some((item) => item.ok)) {
      await reload()
    }
    if (result.ok) {
      outboundVisible.value = false
      noticeMessage.value = result.message
    } else {
      outboundError.value = result.message
    }
  } catch (error) {
    outboundError.value = error instanceof Error ? error.message : '批量出库提交失败'
  } finally {
    submitting.value = false
  }
}

async function submitInbound(onlyFailed: boolean) {
  inboundError.value = ''
  const targets = inboundAccepted.value.filter((line) => line.state !== 'ok' && (!onlyFailed || line.state === 'fail'))
  if (!targets.length) {
    inboundError.value = '没有质检合格、待提交的入库行'
    return
  }
  submitting.value = true
  try {
    const payload = {
      入库日期: inboundDate.value,
      items: targets.map((line) => ({
        材料编号: line.材料编号,
        入库数量: line.入库数量,
        质检结果: line.质检结果,
      })),
    }
    const result = await postBatch<BatchResult>(`${ENDPOINT}/batch-inbound`, payload)
    for (const item of result.results) {
      const line = inboundLines.value.find((entry) => entry.材料编号 === item.材料编号 && entry.state !== 'ok')
      if (!line) continue
      line.state = item.ok ? 'ok' : 'fail'
      line.message = item.message
      if (item.ok && item.结存 !== null) {
        line.当前存量 = item.结存
      }
    }
    if (result.results.some((item) => item.ok)) {
      await reload()
    }
    if (result.ok) {
      inboundVisible.value = false
      noticeMessage.value = result.message
    } else {
      inboundError.value = result.message
    }
  } catch (error) {
    inboundError.value = error instanceof Error ? error.message : '批量入库提交失败'
  } finally {
    submitting.value = false
  }
}

async function postBatch<T>(url: string, payload: unknown): Promise<T> {
  const response = await request(url, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    let detail = `接口返回 ${response.status}`
    try {
      const body = (await response.json()) as { detail?: string }
      if (body.detail) {
        detail = body.detail
      }
    } catch {
      // 保留默认错误说明
    }
    throw new Error(detail)
  }
  return (await response.json()) as T
}

async function openRecords(row: Row) {
  recordsFor.value = row
  recordsRows.value = []
  recordsVisible.value = true
  try {
    const response = await request(`${ENDPOINT}/${row.id}/records`)
    if (!response.ok) {
      throw new Error('出入库记录读取失败')
    }
    const payload = (await response.json()) as { items?: Record<string, string | number | null>[] }
    recordsRows.value = payload.items ?? []
  } catch (error) {
    recordsVisible.value = false
    errorMessage.value = error instanceof Error ? error.message : '出入库记录读取失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('养护材料动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '养护材料操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  noticeMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('养护材料列表读取失败')
    }
    const payload = (await response.json()) as { items?: Row[]; total?: number }
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    selected.value = new Set([...selected.value].filter((id) => rows.value.some((row) => row.id === id)))
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '养护材料列表读取失败'
  }
}

onMounted(reload)
</script>
