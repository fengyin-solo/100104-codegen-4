"""养护材料业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

import threading
from datetime import date
from typing import Any

from app.store import store

MODULE = "material2"
REQUIRED_FIELDS = ["材料编号", "材料名称", "规格型号"]
STATUS_ORDER = ["充足", "不足", "待采购", "已停用"]
ACTION_RULES = {"申领材料": "不足", "采购入库": "充足", "停用材料": "已停用"}
NEGATIVE_ACTIONS = ["停用材料"]

OUTBOUND = "出库"
INBOUND = "入库"
# 质检结论里这两类材料不能入库，只能单独挑出另行处置
QUALITY_REJECTS = {"受潮", "已过期"}


def _as_int(value: Any) -> int | None:
    """把存量、数量字段宽容地转成整数；转不了就返回 None 交给校验报错。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    text = str(value or "").strip()
    if text.lstrip("-").isdigit():
        return int(text)
    return None


def _valid_date(text: str) -> bool:
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


def check_batch_date(day: str) -> str | None:
    """校验整组统一的出入库日期，返回可读的错误说明；合法时返回 None。"""
    if not day.strip():
        return "出入库日期未填写"
    if not _valid_date(day.strip()):
        return f"日期「{day}」格式不正确，应为 YYYY-MM-DD"
    return None


class Material2Service:
    def __init__(self) -> None:
        # 批量提交会连续改多行存量，加把锁避免线程池里两个批次交叉扣减
        self._lock = threading.Lock()

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("材料编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        entry["当前存量"] = _as_int(values.get("当前存量")) or 0
        entry["最低保有量"] = _as_int(values.get("最低保有量")) or 0
        entry["records"] = []
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"养护材料 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于养护材料可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"养护材料已{action}"

    # ------------------------------------------------------------------
    # 批量出入库：逐条校验、逐条落账，单条失败不影响同组其他材料
    # ------------------------------------------------------------------

    def list_records(self, entry_id: int) -> list[dict[str, Any]] | None:
        """读取某条材料名下的全部出入库记录；材料不存在时返回 None。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        return list(entry.get("records", []))

    def batch_outbound(self, items: list[dict[str, Any]], outbound_date: str) -> list[dict[str, Any]]:
        """整组出库：扣减当前存量并把出库记录挂到对应材料编号下面。

        每条材料独立校验独立落账，不做整组回滚——已扣减成功的保持有效，
        失败的行说明原因，前端可以只把失败的行重新提交。
        """
        results: list[dict[str, Any]] = []
        with self._lock:
            for item in items:
                results.append(self._outbound_one(item, outbound_date))
        return results

    def batch_inbound(self, items: list[dict[str, Any]], inbound_date: str) -> list[dict[str, Any]]:
        """整组入库：只给质检合格的材料加存量，受潮、已过期的逐条拒收。"""
        results: list[dict[str, Any]] = []
        with self._lock:
            for item in items:
                results.append(self._inbound_one(item, inbound_date))
        return results

    def _outbound_one(self, item: dict[str, Any], outbound_date: str) -> dict[str, Any]:
        code = str(item.get("材料编号") or "").strip()
        row = self._find_by_code(code)
        if row is None:
            return self._item_result(code, False, f"材料编号 {code or '（空）'} 不存在或已归档")
        if row.get("status") == "已停用":
            return self._item_result(code, False, "材料已停用，不能办理出库")
        spec = str(item.get("规格型号") or "").strip()
        if spec and spec != str(row.get("规格型号") or ""):
            return self._item_result(
                code, False,
                f"规格型号「{spec}」与台账「{row.get('规格型号')}」不一致，不同规格不能合并出库",
            )
        qty = _as_int(item.get("出库数量"))
        if qty is None or qty <= 0:
            return self._item_result(code, False, "出库数量必须是大于 0 的整数")
        team = str(item.get("领用班组") or "").strip()
        if not team:
            return self._item_result(code, False, "领用班组未填写")
        stock = _as_int(row.get("当前存量")) or 0
        if qty > stock:
            return self._item_result(code, False, f"当前存量 {stock} 不足，无法出库 {qty}")
        row["当前存量"] = stock - qty
        self._refresh_status(row)
        self._append_record(row, OUTBOUND, qty, outbound_date, 领用班组=team)
        return self._item_result(code, True, f"已出库 {qty}，结存 {row['当前存量']}", row["当前存量"])

    def _inbound_one(self, item: dict[str, Any], inbound_date: str) -> dict[str, Any]:
        code = str(item.get("材料编号") or "").strip()
        row = self._find_by_code(code)
        if row is None:
            return self._item_result(code, False, f"材料编号 {code or '（空）'} 不存在或已归档")
        if row.get("status") == "已停用":
            return self._item_result(code, False, "材料已停用，不能办理入库")
        quality = str(item.get("质检结果") or "合格").strip()
        if quality in QUALITY_REJECTS:
            return self._item_result(code, False, f"质检结论为「{quality}」，不办理入库，请单独挑出另行处置")
        qty = _as_int(item.get("入库数量"))
        if qty is None or qty <= 0:
            return self._item_result(code, False, "入库数量必须是大于 0 的整数")
        stock = _as_int(row.get("当前存量")) or 0
        row["当前存量"] = stock + qty
        self._refresh_status(row)
        self._append_record(row, INBOUND, qty, inbound_date, 质检结果=quality)
        return self._item_result(code, True, f"已入库 {qty}，结存 {row['当前存量']}", row["当前存量"])

    def _append_record(self, row: dict[str, Any], kind: str, qty: int, day: str, **extra: str) -> None:
        """出入库记录挂在材料编号下面，一条材料一条记录，绝不跨规格合并。"""
        records = row.setdefault("records", [])
        tag = "OUT" if kind == OUTBOUND else "IN"
        record: dict[str, Any] = {
            "记录号": f"{row.get('材料编号')}-{tag}-{len(records) + 1:03d}",
            "类型": kind,
            "材料编号": row.get("材料编号"),
            "材料名称": row.get("材料名称"),
            "规格型号": row.get("规格型号"),
            "数量": qty,
            "日期": day,
            "结存": _as_int(row.get("当前存量")) or 0,
        }
        record.update(extra)
        records.append(record)

    def _refresh_status(self, row: dict[str, Any]) -> None:
        """按结存与最低保有量重算材料状态；已停用的材料保持停用。"""
        if row.get("status") == "已停用":
            return
        stock = _as_int(row.get("当前存量")) or 0
        floor = _as_int(row.get("最低保有量")) or 0
        if stock <= 0:
            status = "待采购"
        elif stock < floor:
            status = "不足"
        else:
            status = "充足"
        row["status"] = status
        row["材料状态"] = status

    def _find_by_code(self, code: str) -> dict[str, Any] | None:
        for row in store.rows(MODULE):
            if str(row.get("材料编号") or "") == code:
                return row
        return None

    @staticmethod
    def _item_result(code: str, ok: bool, message: str, balance: int | None = None) -> dict[str, Any]:
        return {"材料编号": code, "ok": ok, "message": message, "结存": balance}
