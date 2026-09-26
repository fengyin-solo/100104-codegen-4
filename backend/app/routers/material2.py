"""养护材料接口：维护养护材料，覆盖批量出入库、出入库记录与料场盘点。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, BatchStockPayload, BatchStockResult, EntryPayload, PageResult
from app.services.material2 import Material2Service

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


@router.get("/stock/records", response_model=PageResult[dict])
def list_stock_records(
    keyword: str | None = Query(default=None, description="按材料编号检索"),
    record_type: str | None = Query(default=None, description="出库、入库、入库拒收"),
    yard: str | None = Query(default=None, description="按存放料场过滤"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """出入库记录查询：记录挂在材料编号下，可按编号、类型、料场过滤。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_records(keyword=keyword, record_type=record_type, yard=yard, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stock/yards")
def yard_overview() -> dict[str, Any]:
    """料场盘点：按料场汇总台账存量，数据与材料台账同源，不会对不上。"""
    return service.yard_overview()


@router.post("/stock/outbound", response_model=BatchStockResult)
def batch_outbound(payload: BatchStockPayload) -> BatchStockResult:
    """整组提交出库：逐条扣减存量；已成功的不回滚，失败项修正后可单独重试。"""
    if not payload.items:
        raise HTTPException(status_code=400, detail="请至少勾选一条材料再提交出库")
    result = service.batch_outbound(
        [item.model_dump() for item in payload.items],
        use_date=payload.领用日期,
        remark=payload.remark,
    )
    return BatchStockResult(**result)


@router.post("/stock/inbound", response_model=BatchStockResult)
def batch_inbound(payload: BatchStockPayload) -> BatchStockResult:
    """整组提交入库：受潮/过期材料自动挑出登记拒收，仅合格材料增加存量。"""
    if not payload.items:
        raise HTTPException(status_code=400, detail="请至少勾选一条材料再提交入库")
    result = service.batch_inbound(
        [item.model_dump() for item in payload.items],
        use_date=payload.入库日期,
        remark=payload.remark,
    )
    return BatchStockResult(**result)


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


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条养护材料，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing == ["duplicate"]:
        return ActionResult(ok=False, message="材料编号已存在，不能重复登记")
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="养护材料已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条养护材料执行申领材料、采购入库、停用材料；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
