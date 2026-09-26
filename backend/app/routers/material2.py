"""养护材料接口：维护养护材料，覆盖申领材料、采购入库、停用材料等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import (
    ActionResult,
    BatchInboundPayload,
    BatchOutboundPayload,
    BatchResult,
    EntryPayload,
    PageResult,
)
from app.services.material2 import Material2Service, check_batch_date

router = APIRouter(prefix="/api/material2", tags=["养护材料"])

service = Material2Service()

LIST_FIELDS = ["材料编号", "材料名称", "规格型号", "适用场景", "存放料场", "最低保有量", "当前存量", "材料状态"]
STATUSES = ["充足", "不足", "待采购", "已停用"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按材料编号检索"),
    status: str | None = Query(default=None, description="充足、不足、待采购、已停用"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按材料编号与状态过滤养护材料列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条养护材料，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="养护材料已登记", entry=entry)


# 批量接口与导出必须写在 /{entry_id} 之前，否则会被当成材料 id 匹配掉


@router.post("/batch-outbound", response_model=BatchResult)
def batch_outbound(payload: BatchOutboundPayload) -> BatchResult:
    """整组出库：逐条校验逐条扣减，失败的行给出材料编号和原因，成功的行不回滚。"""
    if not payload.items:
        raise HTTPException(status_code=400, detail="出库清单为空，请先勾选要出库的材料")
    date_error = check_batch_date(payload.领用日期)
    if date_error:
        raise HTTPException(status_code=400, detail=date_error)
    items = [item.model_dump() for item in payload.items]
    results = service.batch_outbound(items, payload.领用日期.strip())
    return _batch_result(results, "出库")


@router.post("/batch-inbound", response_model=BatchResult)
def batch_inbound(payload: BatchInboundPayload) -> BatchResult:
    """整组入库：只给质检合格的材料加存量，受潮、已过期的逐条说明并拒收。"""
    if not payload.items:
        raise HTTPException(status_code=400, detail="入库清单为空，请先勾选要入库的材料")
    date_error = check_batch_date(payload.入库日期)
    if date_error:
        raise HTTPException(status_code=400, detail=date_error)
    items = [item.model_dump() for item in payload.items]
    results = service.batch_inbound(items, payload.入库日期.strip())
    return _batch_result(results, "入库")


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出养护材料清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "material2", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条养护材料明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"养护材料 {entry_id} 不存在或已归档")
    return entry


@router.get("/{entry_id}/records", response_model=dict)
def list_records(entry_id: int) -> dict[str, Any]:
    """读取挂在该材料编号下的全部出入库记录，盘点时用来对账。"""
    records = service.list_records(entry_id)
    if records is None:
        raise HTTPException(status_code=404, detail=f"养护材料 {entry_id} 不存在或已归档")
    return {"items": records, "total": len(records)}


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条养护材料执行申领材料、采购入库、停用材料；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


def _batch_result(results: list[dict[str, Any]], kind: str) -> BatchResult:
    """把逐条结果汇总成一句话：哪几条卡住、为什么卡住，看 results 明细。"""
    failed = [item for item in results if not item["ok"]]
    succeeded = len(results) - len(failed)
    if failed:
        codes = "、".join(item["材料编号"] or "（空编号）" for item in failed)
        message = f"共提交 {len(results)} 条，{succeeded} 条{kind}成功，{len(failed)} 条被卡住：{codes}；已成功的不会回滚，可修正后只重试失败项"
    else:
        message = f"共提交 {len(results)} 条，全部{kind}成功"
    return BatchResult(ok=not failed, message=message, results=results)
