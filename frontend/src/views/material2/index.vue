<template>
  <section class="page material-page" data-module="material2">
    <header class="page-head">
      <div>
        <h2>养护材料管理</h2>
        <p class="page-desc">盘点批量出入库：勾选多条整组提交，逐条填领用班组、统一领用日期；入库自动挑出受潮/过期材料。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="exportRows">导出材料清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <nav class="tabs">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        type="button"
        class="tab"
        :class="{ active: activeTab === tab.key }"
        @click="switchTab(tab.key)"
      >
        {{ tab.label }}
      </button>
    </nav>

    <!-- ============ 材料台账 ============ -->
    <div v-if="activeTab === 'ledger'" class="tab-panel">
      <form class="filter-bar" @submit.prevent="reloadLedger">
        <label class="filter-item">
          <span>材料编号</span>
          <input v-model="ledgerFilter.keyword" placeholder="按材料编号检索" />
        </label>
        <label class="filter-item">
          <span>材料状态</span>
          <select v-model="ledgerFilter.status">
            <option value="">全部</option>
            <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
          </select>
        </label>
        <button class="btn" type="submit">查询</button>
        <button class="btn ghost" type="button" @click="resetLedgerFilter">重置条件</button>
      </form>

      <div class="bulk-bar">
        <label class="check-all">
          <input type="checkbox" :checked="allChecked" :indeterminate.prop="someChecked" @change="toggleAll" />
          全选本页（已选 {{ selectedCodes.size }} 条）
        </label>
        <button class="btn primary" type="button" :disabled="!selectedCodes.size" @click="startOutbound">
          批量出库（{{ selectedCodes.size }}）
        </button>
        <button class="btn primary" type="button" :disabled="!selectedCodes.size" @click="startInbound">
          批量入库（{{ selectedCodes.size }}）
        </button>
        <button v-if="selectedCodes.size" class="btn ghost" type="button" @click="selectedCodes.clear()">清空选择</button>
        <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      </div>

      <table class="data-table">
        <thead>
          <tr>
            <th class="col-check">选择</th>
            <th v-for="column in columns" :key="column">{{ column }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="String(row.id)" :class="{ 'row-selected': selectedCodes.has(String(row['材料编号'])) }">
            <td class="col-check">
              <input
                type="checkbox"
                :checked="selectedCodes.has(String(row['材料编号']))"
                @change="toggleRow(row)"
              />
            </td>
            <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          </tr>
          <tr v-if="!rows.length">
            <td :colspan="columns.length + 1" class="empty-state">暂无养护材料数据</td>
          </tr>
        </tbody>
      </table>
      <footer class="page-foot"><span>共 {{ total }} 条材料记录</span></footer>
    </div>

    <!-- ============ 批量出库 ============ -->
    <div v-if="activeTab === 'outbound'" class="tab-panel">
      <div class="form-head">
        <h3>批量出库</h3>
        <button class="btn ghost" type="button" @click="cancelBatch">返回台账重新勾选</button>
      </div>
      <div class="shared-fields">
        <label class="filter-item">
          <span>统一领用日期 *</span>
          <input v-model="outbound.date" type="date" />
        </label>
        <label class="filter-item">
          <span>统一填写领用班组</span>
          <input v-model="outbound.teamFill" placeholder="填入后点右侧批量带入" />
        </label>
        <button class="btn" type="button" @click="fillOutboundTeams">批量带入班组</button>
        <span class="hint">每条仍可单独改班组；当前存量不足会在提交后逐条提示。</span>
      </div>

      <table class="data-table">
        <thead>
          <tr>
            <th>材料编号</th>
            <th>材料名称</th>
            <th>规格型号</th>
            <th>存放料场</th>
            <th>当前存量</th>
            <th>出库数量 *</th>
            <th>领用班组 *</th>
            <th>移除</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(line, idx) in outbound.lines" :key="idx">
            <td><input v-model="line.code" class="cell-input" placeholder="材料编号" /></td>
            <td>{{ line.name }}</td>
            <td>{{ line.spec }}</td>
            <td>{{ line.yard }}</td>
            <td :class="{ 'stock-low': line.stock <= 0 }">{{ line.stock }}</td>
            <td>
              <input v-model.number="line.qty" type="number" min="1" step="1" class="cell-input" :placeholder="`不超过 ${line.stock}`" />
            </td>
            <td><input v-model="line.team" class="cell-input" placeholder="领用班组" /></td>
            <td><button class="link" type="button" @click="removeOutbound(idx)">移除</button></td>
          </tr>
        </tbody>
      </table>

      <div class="submit-bar">
        <button class="btn primary" type="button" :disabled="submitting" @click="submitOutbound">
          {{ submitting ? '提交中…' : '整组提交出库' }}
        </button>
        <span class="hint">已扣减成功的条目不会因其他条目失败而回滚，失败条目修正后可单独重试。</span>
      </div>

      <div v-if="outbound.result" class="result-panel">
        <p class="result-summary">{{ outbound.result.message }}<span class="batch-no">批次号：{{ outbound.result.batch_no }}</span></p>
        <ul v-if="outbound.result.succeeded.length" class="result-list ok-list">
          <li v-for="s in outbound.result.succeeded" :key="s['材料编号']">
            ✅ {{ s['材料编号'] }}（{{ s.record['规格型号'] }}）出库 {{ s.record['数量'] }}，扣减后存量 {{ s.entry['当前存量'] }}
          </li>
        </ul>
        <ul v-if="outbound.result.failed.length" class="result-list fail-list">
          <li v-for="(f, idx) in outbound.result.failed" :key="f['材料编号'] + idx">
            ❌ {{ f['材料编号'] || '（编号为空）' }}：{{ f.reason }}
          </li>
        </ul>
        <div v-if="outbound.result.failed.length" class="submit-bar">
          <button class="btn primary" type="button" @click="retryOutbound">只重试失败的 {{ outbound.result.failed.length }} 条</button>
        </div>
      </div>
    </div>

    <!-- ============ 批量入库 ============ -->
    <div v-if="activeTab === 'inbound'" class="tab-panel">
      <div class="form-head">
        <h3>批量入库</h3>
        <button class="btn ghost" type="button" @click="cancelBatch">返回台账重新勾选</button>
      </div>
      <div class="shared-fields">
        <label class="filter-item">
          <span>统一入库日期 *</span>
          <input v-model="inbound.date" type="date" />
        </label>
        <label class="filter-item">
          <span>统一填写供货单位</span>
          <input v-model="inbound.supplierFill" placeholder="填入后点右侧批量带入" />
        </label>
        <button class="btn" type="button" @click="fillInboundSuppliers">批量带入单位</button>
        <span class="hint">盘点时把受潮/过期材料在「质量判定」里挑出来，整组提交只让合格材料入库。</span>
      </div>

      <h4 class="group-title good">待入库（质量判定：合格）</h4>
      <table class="data-table">
        <thead>
          <tr>
            <th>材料编号</th>
            <th>材料名称</th>
            <th>规格型号</th>
            <th>存放料场</th>
            <th>当前存量</th>
            <th>入库数量 *</th>
            <th>供货单位</th>
            <th>质量判定</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(line, idx) in inboundGoodLines" :key="idx">
            <td>{{ line.code }}</td>
            <td>{{ line.name }}</td>
            <td>{{ line.spec }}</td>
            <td>{{ line.yard }}</td>
            <td>{{ line.stock }}</td>
            <td><input v-model.number="line.qty" type="number" min="1" step="1" class="cell-input" placeholder="入库数量" /></td>
            <td><input v-model="line.supplier" class="cell-input" placeholder="供货单位" /></td>
            <td>
              <select v-model="line.grade" class="cell-input">
                <option v-for="g in grades" :key="g" :value="g">{{ g }}</option>
              </select>
            </td>
          </tr>
          <tr v-if="!inboundGoodLines.length">
            <td colspan="8" class="empty-state">合格材料都已处理完，或全部被移到下方「挑出不入库」</td>
          </tr>
        </tbody>
      </table>

      <h4 class="group-title bad">挑出不入库（受潮 / 过期，仅登记拒收）</h4>
      <table class="data-table">
        <thead>
          <tr>
            <th>材料编号</th>
            <th>材料名称</th>
            <th>规格型号</th>
            <th>质量判定</th>
            <th>情况说明</th>
            <th>恢复为合格</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(line, idx) in inboundBadLines" :key="idx" class="row-rejected">
            <td>{{ line.code }}</td>
            <td>{{ line.name }}</td>
            <td>{{ line.spec }}</td>
            <td>
              <select v-model="line.grade" class="cell-input">
                <option v-for="g in grades" :key="g" :value="g">{{ g }}</option>
              </select>
            </td>
            <td><input v-model="line.reason" class="cell-input" placeholder="如：包装破损受潮 / 已过保质期" /></td>
            <td><button class="link" type="button" @click="line.grade = '合格'">恢复合格</button></td>
          </tr>
          <tr v-if="!inboundBadLines.length">
            <td colspan="6" class="empty-state">尚未挑出受潮或过期材料</td>
          </tr>
        </tbody>
      </table>

      <div class="submit-bar">
        <button class="btn primary" type="button" :disabled="submitting" @click="submitInbound">
          {{ submitting ? '提交中…' : '整组提交（只入合格材料）' }}
        </button>
      </div>

      <div v-if="inbound.result" class="result-panel">
        <p class="result-summary">{{ inbound.result.message }}<span class="batch-no">批次号：{{ inbound.result.batch_no }}</span></p>
        <ul v-if="inbound.result.succeeded.length" class="result-list ok-list">
          <li v-for="s in inbound.result.succeeded" :key="s['材料编号']">
            ✅ {{ s['材料编号'] }}（{{ s.record['规格型号'] }}）入库 {{ s.record['数量'] }}，最新存量 {{ s.entry['当前存量'] }}
          </li>
        </ul>
        <ul v-if="inbound.result.rejected.length" class="result-list reject-list">
          <li v-for="(x, idx) in inbound.result.rejected" :key="x['材料编号'] + idx">
            ⚠️ {{ x['材料编号'] }}：{{ x.reason }}
          </li>
        </ul>
        <ul v-if="inbound.result.failed.length" class="result-list fail-list">
          <li v-for="(f, idx) in inbound.result.failed" :key="f['材料编号'] + idx">
            ❌ {{ f['材料编号'] || '（编号为空）' }}：{{ f.reason }}
          </li>
        </ul>
        <div v-if="inbound.result.failed.length" class="submit-bar">
          <button class="btn primary" type="button" @click="retryInbound">只重试失败的 {{ inbound.result.failed.length }} 条</button>
        </div>
      </div>
    </div>

    <!-- ============ 料场盘点 ============ -->
    <div v-if="activeTab === 'yards'" class="tab-panel">
      <p class="hint">{{ yardData?.consistency }}（数据来源：{{ yardData?.source }} 材料台账）</p>
      <div class="stat-row">
        <article class="stat-card"><span class="stat-label">料场数</span><strong class="stat-value">{{ yardData?.totals['料场数'] ?? '—' }}</strong></article>
        <article class="stat-card"><span class="stat-label">材料种类合计</span><strong class="stat-value">{{ yardData?.totals['材料种类'] ?? '—' }}</strong></article>
        <article class="stat-card"><span class="stat-label">当前存量合计</span><strong class="stat-value">{{ yardData?.totals['当前存量合计'] ?? '—' }}</strong></article>
      </div>
      <div v-for="yard in yardData?.yards ?? []" :key="yard['存放料场']" class="yard-card">
        <header class="yard-head" @click="toggleYard(yard['存放料场'])">
          <strong>{{ yard['存放料场'] }}</strong>
          <span>材料 {{ yard['材料种类'] }} 种 · 当前存量合计 {{ yard['当前存量合计'] }} · 不足/待采购 {{ yard['不足种类'] }} 种</span>
          <span class="link">{{ expandedYards.has(yard['存放料场']) ? '收起' : '展开明细' }}</span>
        </header>
        <table v-if="expandedYards.has(yard['存放料场'])" class="data-table yard-table">
          <thead>
            <tr>
              <th>材料编号</th><th>材料名称</th><th>规格型号</th><th>当前存量</th><th>最低保有量</th><th>材料状态</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in yard.materials" :key="m['材料编号']">
              <td>{{ m['材料编号'] }}</td>
              <td>{{ m['材料名称'] }}</td>
              <td>{{ m['规格型号'] }}</td>
              <td :class="{ 'stock-low': m['材料状态'] !== '充足' && m['材料状态'] !== '已停用' }">{{ m['当前存量'] }}</td>
              <td>{{ m['最低保有量'] }}</td>
              <td>{{ m['材料状态'] }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ============ 出入库记录 ============ -->
    <div v-if="activeTab === 'records'" class="tab-panel">
      <form class="filter-bar" @submit.prevent="reloadRecords">
        <label class="filter-item">
          <span>材料编号</span>
          <input v-model="recordFilter.keyword" placeholder="按材料编号检索" />
        </label>
        <label class="filter-item">
          <span>记录类型</span>
          <select v-model="recordFilter.record_type">
            <option value="">全部</option>
            <option v-for="t in recordTypes" :key="t" :value="t">{{ t }}</option>
          </select>
        </label>
        <label class="filter-item">
          <span>存放料场</span>
          <select v-model="recordFilter.yard">
            <option value="">全部</option>
            <option v-for="y in yardNames" :key="y" :value="y">{{ y }}</option>
          </select>
        </label>
        <button class="btn" type="submit">查询</button>
        <button class="btn ghost" type="button" @click="resetRecordFilter">重置条件</button>
      </form>
      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in recordColumns" :key="column">{{ column }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="rec in recordRows" :key="String(rec.id)" :class="{ 'row-rejected': rec['类型'] === '入库拒收' }">
            <td v-for="column in recordColumns" :key="column">{{ rec[column] ?? '—' }}</td>
          </tr>
          <tr v-if="!recordRows.length">
            <td :colspan="recordColumns.length" class="empty-state">暂无出入库记录</td>
          </tr>
        </tbody>
      </table>
      <footer class="page-foot"><span>共 {{ recordTotal }} 条记录（按材料编号挂账，不同规格各自独立）</span></footer>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
interface StockLine {
  code: string
  name: string
  spec: string
  yard: string
  stock: number
  qty: number | null
  team: string
  supplier: string
  grade: string
  reason: string
}
interface BatchFailure {
  材料编号: string
  reason: string
  item: Record<string, unknown>
}
interface BatchSuccess {
  材料编号: string
  record: Record<string, string | number>
  entry: Row
}
interface BatchReject {
  材料编号: string
  reason: string
  record?: Record<string, string | number>
}
interface BatchResult {
  ok: boolean
  message: string
  batch_no: string
  succeeded: BatchSuccess[]
  failed: BatchFailure[]
  rejected: BatchReject[]
}

const ENDPOINT = '/api/material2'
const columns = ['材料编号', '材料名称', '规格型号', '适用场景', '存放料场', '最低保有量', '当前存量', '材料状态']
const recordColumns = ['经办时间', '批次号', '类型', '材料编号', '材料名称', '规格型号', '存放料场', '数量', '日期', '领用班组', '供货单位', '质量判定', '备注']
const statuses = ['充足', '不足', '待采购', '已停用']
const recordTypes = ['出库', '入库', '入库拒收']
const grades = ['合格', '受潮', '过期']
const tabs = [
  { key: 'ledger', label: '材料台账' },
  { key: 'outbound', label: '批量出库' },
  { key: 'inbound', label: '批量入库' },
  { key: 'yards', label: '料场盘点' },
  { key: 'records', label: '出入库记录' },
] as const
type TabKey = (typeof tabs)[number]['key']

const activeTab = ref<TabKey>('ledger')
const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const ledgerFilter = ref<{ keyword: string; status: string }>({ keyword: '', status: '' })
const selectedCodes = ref<Set<string>>(new Set())
const submitting = ref(false)

const stats = computed(() => [
  { label: '材料种类', value: total.value },
  { label: '不足材料', value: rows.value.filter((r) => r['材料状态'] === '不足').length },
  { label: '待采购材料', value: rows.value.filter((r) => r['材料状态'] === '待采购').length },
  { label: '已选材料', value: selectedCodes.value.size },
])

function today(): string {
  return new Date().toISOString().slice(0, 10)
}

function resetLedgerFilter() {
  ledgerFilter.value = { keyword: '', status: '' }
  void reloadLedger()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function toggleRow(row: Row) {
  const code = String(row['材料编号'])
  if (selectedCodes.value.has(code)) {
    selectedCodes.value.delete(code)
  } else {
    selectedCodes.value.add(code)
  }
  selectedCodes.value = new Set(selectedCodes.value)
}

const allChecked = computed(() => rows.value.length > 0 && rows.value.every((r) => selectedCodes.value.has(String(r['材料编号']))))
const someChecked = computed(() => rows.value.some((r) => selectedCodes.value.has(String(r['材料编号']))) && !allChecked.value)

function toggleAll() {
  if (allChecked.value) {
    for (const row of rows.value) {
      selectedCodes.value.delete(String(row['材料编号']))
    }
  } else {
    for (const row of rows.value) {
      selectedCodes.value.add(String(row['材料编号']))
    }
  }
  selectedCodes.value = new Set(selectedCodes.value)
}

async function reloadLedger() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (ledgerFilter.value.keyword) {
    query.set('keyword', ledgerFilter.value.keyword)
  }
  if (ledgerFilter.value.status) {
    query.set('status', ledgerFilter.value.status)
  }
  query.set('size', '200')
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('材料列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '材料列表读取失败'
  }
}

// ------------------------------------------------------------------
// 批量出库
// ------------------------------------------------------------------
const outbound = ref<{ date: string; teamFill: string; lines: StockLine[]; result: BatchResult | null }>({
  date: today(),
  teamFill: '',
  lines: [],
  result: null,
})

function toLine(row: Row): StockLine {
  return {
    code: String(row['材料编号'] ?? ''),
    name: String(row['材料名称'] ?? ''),
    spec: String(row['规格型号'] ?? ''),
    yard: String(row['存放料场'] ?? ''),
    stock: Number(row['当前存量'] ?? 0),
    qty: null,
    team: '',
    supplier: '',
    grade: '合格',
    reason: '',
  }
}

function selectedRows(): Row[] {
  return rows.value.filter((r) => selectedCodes.value.has(String(r['材料编号'])))
}

function startOutbound() {
  const picked = selectedRows()
  if (!picked.length) {
    return
  }
  outbound.value = { date: today(), teamFill: '', lines: picked.map(toLine), result: null }
  activeTab.value = 'outbound'
}

function fillOutboundTeams() {
  const team = outbound.value.teamFill.trim()
  if (!team) {
    return
  }
  outbound.value.lines.forEach((line) => {
    line.team = team
  })
}

function removeOutbound(index: number) {
  outbound.value.lines.splice(index, 1)
}

async function submitOutbound() {
  outbound.value.result = null
  errorMessage.value = ''
  if (!outbound.value.lines.length) {
    errorMessage.value = '请至少保留一条材料再提交'
    return
  }
  submitting.value = true
  try {
    const response = await request(`${ENDPOINT}/stock/outbound`, {
      method: 'POST',
      body: JSON.stringify({
        领用日期: outbound.value.date,
        items: outbound.value.lines.map((line) => ({
          材料编号: line.code,
          规格型号: line.spec,
          出库数量: line.qty,
          领用班组: line.team,
        })),
      }),
    })
    const payload = await response.json()
    if (!response.ok) {
      throw new Error(payload.detail ?? '批量出库提交失败')
    }
    outbound.value.result = payload as BatchResult
    await reloadLedger()
    syncLineStocks(outbound.value.lines, payload.succeeded)
    if (!payload.failed.length) {
      selectedCodes.value.clear()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '批量出库提交失败'
  } finally {
    submitting.value = false
  }
}

function retryOutbound() {
  const result = outbound.value.result
  if (!result || !result.failed.length) {
    return
  }
  const byCode = new Map(outbound.value.lines.map((line) => [line.code, line]))
  const lines: StockLine[] = []
  for (const failure of result.failed) {
    const old = byCode.get(failure['材料编号'])
    lines.push(old ? { ...old } : {
      code: failure['材料编号'],
      name: '',
      spec: String(failure.item['规格型号'] ?? ''),
      yard: '',
      stock: 0,
      qty: failure.item['出库数量'] === undefined ? null : Number(failure.item['出库数量']),
      team: String(failure.item['领用班组'] ?? ''),
      supplier: '',
      grade: '合格',
      reason: '',
    })
  }
  outbound.value.lines = lines
  outbound.value.result = null
  void submitOutbound()
}

// ------------------------------------------------------------------
// 批量入库
// ------------------------------------------------------------------
const inbound = ref<{ date: string; supplierFill: string; lines: StockLine[]; result: BatchResult | null }>({
  date: today(),
  supplierFill: '',
  lines: [],
  result: null,
})
const inboundGoodLines = computed(() => inbound.value.lines.filter((line) => line.grade === '合格'))
const inboundBadLines = computed(() => inbound.value.lines.filter((line) => line.grade !== '合格'))

function startInbound() {
  const picked = selectedRows()
  if (!picked.length) {
    return
  }
  inbound.value = { date: today(), supplierFill: '', lines: picked.map(toLine), result: null }
  activeTab.value = 'inbound'
}

function fillInboundSuppliers() {
  const supplier = inbound.value.supplierFill.trim()
  if (!supplier) {
    return
  }
  inbound.value.lines.forEach((line) => {
    line.supplier = supplier
  })
}

async function submitInbound() {
  inbound.value.result = null
  errorMessage.value = ''
  if (!inbound.value.lines.length) {
    errorMessage.value = '请至少保留一条材料再提交'
    return
  }
  submitting.value = true
  try {
    const response = await request(`${ENDPOINT}/stock/inbound`, {
      method: 'POST',
      body: JSON.stringify({
        入库日期: inbound.value.date,
        items: inbound.value.lines.map((line) => ({
          材料编号: line.code,
          规格型号: line.spec,
          入库数量: line.qty,
          供货单位: line.supplier,
          质量判定: line.grade,
          拒收原因: line.reason,
        })),
      }),
    })
    const payload = (await response.json()) as BatchResult
    if (!response.ok) {
      throw new Error('批量入库提交失败')
    }
    inbound.value.result = payload
    await reloadLedger()
    syncLineStocks(inbound.value.lines, payload.succeeded)
    // 成功条目已入账，从表单移除；受潮/过期拒收只提示不增库存，行保留以便改判；失败行保留修正重试
    const succeededCodes = new Set(payload.succeeded.map((s) => s['材料编号']))
    inbound.value.lines = inbound.value.lines.filter((line) => !succeededCodes.has(line.code))
    if (!payload.failed.length && !inbound.value.lines.length) {
      selectedCodes.value.clear()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '批量入库提交失败'
  } finally {
    submitting.value = false
  }
}

function retryInbound() {
  const result = inbound.value.result
  if (!result || !result.failed.length) {
    return
  }
  // 失败条目已在提交后保留在 lines 里，直接带着用户修正后的内容再提一次
  inbound.value.result = null
  void submitInbound()
}

function syncLineStocks(lines: StockLine[], succeeded: BatchSuccess[]) {
  const latest = new Map(succeeded.map((s) => [s['材料编号'], s]))
  for (const line of lines) {
    const hit = latest.get(line.code)
    if (hit) {
      line.stock = Number(hit.entry['当前存量'] ?? 0)
      line.name = String(hit.entry['材料名称'] ?? line.name)
      line.spec = String(hit.entry['规格型号'] ?? line.spec)
      line.yard = String(hit.entry['存放料场'] ?? line.yard)
    }
  }
}

function cancelBatch() {
  outbound.value.result = null
  inbound.value.result = null
  activeTab.value = 'ledger'
}

// ------------------------------------------------------------------
// 料场盘点 & 出入库记录
// ------------------------------------------------------------------
interface YardMaterial {
  材料编号: string
  材料名称: string
  规格型号: string
  当前存量: number
  最低保有量: number
  材料状态: string
}
interface YardBucket {
  存放料场: string
  材料种类: number
  当前存量合计: number
  不足种类: number
  materials: YardMaterial[]
}
interface YardOverview {
  source: string
  consistency: string
  totals: Record<string, number>
  yards: YardBucket[]
}
const yardData = ref<YardOverview | null>(null)
const expandedYards = ref<Set<string>>(new Set())

async function reloadYards() {
  try {
    const response = await request(`${ENDPOINT}/stock/yards`)
    if (!response.ok) {
      throw new Error()
    }
    yardData.value = await response.json()
  } catch {
    errorMessage.value = '料场盘点数据读取失败'
  }
}

function toggleYard(name: string) {
  if (expandedYards.value.has(name)) {
    expandedYards.value.delete(name)
  } else {
    expandedYards.value.add(name)
  }
  expandedYards.value = new Set(expandedYards.value)
}

const yardNames = computed(() => (yardData.value?.yards ?? []).map((y) => String(y['存放料场'])))

const recordRows = ref<Row[]>([])
const recordTotal = ref(0)
const recordFilter = ref<{ keyword: string; record_type: string; yard: string }>({ keyword: '', record_type: '', yard: '' })

function resetRecordFilter() {
  recordFilter.value = { keyword: '', record_type: '', yard: '' }
  void reloadRecords()
}

async function reloadRecords() {
  const query = new URLSearchParams({ size: '200' })
  if (recordFilter.value.keyword) {
    query.set('keyword', recordFilter.value.keyword)
  }
  if (recordFilter.value.record_type) {
    query.set('record_type', recordFilter.value.record_type)
  }
  if (recordFilter.value.yard) {
    query.set('yard', recordFilter.value.yard)
  }
  try {
    const response = await request(`${ENDPOINT}/stock/records?${query.toString()}`)
    if (!response.ok) {
      throw new Error()
    }
    const payload = await response.json()
    recordRows.value = payload.items ?? []
    recordTotal.value = payload.total ?? recordRows.value.length
  } catch {
    errorMessage.value = '出入库记录读取失败'
  }
}

async function switchTab(key: TabKey) {
  activeTab.value = key
  errorMessage.value = ''
  if (key === 'yards') {
    await reloadYards()
  } else if (key === 'records') {
    if (!yardData.value) {
      await reloadYards()
    }
    await reloadRecords()
  } else if (key === 'ledger') {
    await reloadLedger()
  }
}

onMounted(reloadLedger)
</script>

<style scoped>
.tabs {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 12px;
}
.tab {
  border: 1px solid transparent;
  border-bottom: none;
  background: transparent;
  padding: 8px 16px;
  cursor: pointer;
  font-size: 13px;
  color: var(--muted);
  border-radius: 6px 6px 0 0;
}
.tab.active {
  background: #fff;
  border-color: var(--border);
  color: var(--brand);
  font-weight: 600;
  position: relative;
  top: 1px;
}
.bulk-bar {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 8px;
}
.check-all {
  font-size: 13px;
}
.col-check {
  width: 44px;
  text-align: center;
}
.row-selected {
  background: #eef5ff;
}
.form-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.shared-fields {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: flex-end;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 12px;
}
.hint {
  color: var(--muted);
  font-size: 12px;
}
.cell-input {
  width: 100%;
  min-width: 90px;
  padding: 4px 6px;
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 13px;
}
.stock-low {
  color: #b42318;
  font-weight: 600;
}
.submit-bar {
  display: flex;
  gap: 10px;
  align-items: center;
  margin: 12px 0;
}
.result-panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 14px;
}
.result-summary {
  font-weight: 600;
  margin: 4px 0 8px;
}
.batch-no {
  float: right;
  font-weight: 400;
  color: var(--muted);
  font-size: 12px;
}
.result-list {
  list-style: none;
  margin: 0 0 8px;
  padding: 0;
  font-size: 13px;
  line-height: 1.9;
}
.ok-list li { color: #067647; }
.fail-list li { color: #b42318; }
.reject-list li { color: #b54708; }
.group-title {
  margin: 14px 0 6px;
  font-size: 13px;
}
.group-title.good { color: #067647; }
.group-title.bad { color: #b54708; }
.row-rejected {
  background: #fdf6ec;
}
.yard-card {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 10px;
  overflow: hidden;
}
.yard-head {
  display: flex;
  gap: 14px;
  align-items: center;
  padding: 10px 14px;
  cursor: pointer;
  font-size: 13px;
}
.yard-head span {
  color: var(--muted);
}
.yard-head .link {
  margin-left: auto;
}
.yard-table {
  border-left: none;
  border-right: none;
  border-bottom: none;
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
