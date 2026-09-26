"""养护材料业务规则：批量出入库、库存扣减、出入库记录与料场盘点口径都收在这里。

设计要点：
- 批量提交逐条处理：每条独立判定、独立落账，一条卡住不影响其他条；
- 库存（当前存量）只有一处事实来源，出入库记录、料场盘点都由它派生，
  因此料场盘点页与材料台账看到的当前存量必然一致；
- 出库记录按"材料编号 + 规格型号"落账，规格型号与台账不符直接拦下，
  不同规格永远不会合并成同一条出库记录；
- 入库时受潮/过期材料只登记拒收记录，不增加库存，也不占批量提交名额。
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from app.store import store

MODULE = "material2"
RECORD_MODULE = "material2_record"
REQUIRED_FIELDS = ["材料编号", "材料名称", "规格型号"]
STATUS_ORDER = ["充足", "不足", "待采购", "已停用"]
ACTION_RULES = {"申领材料": "不足", "采购入库": "充足", "停用材料": "已停用"}
NEGATIVE_ACTIONS = ["停用材料"]

OUTBOUND_TYPE = "出库"
INBOUND_TYPE = "入库"
REJECT_TYPE = "入库拒收"
QUALITY_GRADES = ("合格", "受潮", "过期")
DEFAULT_GRADE = "合格"


def _to_int(value: Any) -> int | None:
    """把台账里的存量解析成非负整数；解析不了返回 None。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    text = str(value or "").strip()
    if not text:
        return None
    match = re.fullmatch(r"\d+", text)
    return int(match.group()) if match else None


def _next_id(module: str) -> int:
    return max((int(row.get("id", 0)) for row in store.rows(module)), default=0) + 1


def _refresh_status(entry: dict[str, Any]) -> None:
    """按最新存量重算材料状态，保证「材料状态」与「当前存量」口径一致。"""
    stock = _to_int(entry.get("当前存量"))
    minimum = _to_int(entry.get("最低保有量"))
    if stock is None:
        return
    if stock == 0:
        entry["status"] = "待采购"
    elif minimum is not None and stock < minimum:
        entry["status"] = "不足"
    else:
        entry["status"] = "充足"
    entry["材料状态"] = entry["status"]
    entry["pending"] = entry["status"] != "已停用"
    entry["abnormal"] = entry["status"] in ("不足", "待采购", "已停用")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _valid_date(value: Any) -> bool:
    text = str(value or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return False
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _resolve_entry(code: Any = None, entry_id: Any = None) -> tuple[dict[str, Any] | None, str]:
    """按材料编号（优先）或记录 id 定位台账条目。"""
    rows = store.rows(MODULE)
    code_text = str(code or "").strip()
    if code_text:
        for row in rows:
            if str(row.get("材料编号", "")).strip() == code_text:
                return row, ""
        return None, f"材料编号 {code_text} 在台账中不存在"
    try:
        target_id = int(entry_id)
    except (TypeError, ValueError):
        return None, "材料编号缺失，且行内编号无法识别"
    for row in rows:
        if int(row.get("id", 0)) == target_id:
            return row, ""
    return None, f"材料编号 {target_id} 在台账中不存在"


class Material2Service:
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
        code = str(values.get("材料编号")).strip()
        if any(str(row.get("材料编号", "")).strip() == code for row in rows):
            return None, ["duplicate"]
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        for optional in ("适用场景", "存放料场", "最低保有量", "当前存量"):
            if values.get(optional) not in (None, ""):
                entry[optional] = values.get(optional)
        if _to_int(entry.get("当前存量")) is None:
            entry["当前存量"] = 0
        if _to_int(entry.get("最低保有量")) is None:
            entry["最低保有量"] = 0
        entry["status"] = "充足"
        entry["材料状态"] = "充足"
        entry["pending"] = True
        entry["abnormal"] = False
        _refresh_status(entry)
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
        entry["材料状态"] = target
        return entry, f"养护材料已{action}"

    # ------------------------------------------------------------------
    # 批量出入库
    # ------------------------------------------------------------------
    def batch_outbound(
        self,
        items: list[dict[str, Any]],
        *,
        use_date: str | None = None,
        remark: str | None = None,
    ) -> dict[str, Any]:
        """整组提交出库：逐条判定并扣减，成功的不回滚，失败的逐条说明原因。"""
        date_text = str(use_date or "").strip() or _today()
        batch_no = f"OUT-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        if not _valid_date(date_text):
            bad_date = date_text or "未填写"
            return {
                "ok": False,
                "message": f"领用日期「{bad_date}」不是合法日期，应为 YYYY-MM-DD",
                "batch_no": batch_no,
                "succeeded": [],
                "failed": [
                    {
                        "材料编号": str(item.get("材料编号") or "").strip(),
                        "reason": f"领用日期「{bad_date}」不是合法日期，应为 YYYY-MM-DD",
                        "item": item,
                    }
                    for item in items
                ],
                "rejected": [],
            }

        # 同一次提交里重复的材料编号：无法明确每行各自的扣减口径，整组中这些行先拦下。
        seen: set[str] = set()
        duplicate: set[str] = set()
        for item in items:
            code = str(item.get("材料编号") or "").strip()
            if code and code in seen:
                duplicate.add(code)
            if code:
                seen.add(code)

        succeeded: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        for item in items:
            code = str(item.get("材料编号") or "").strip()
            if code in duplicate:
                failed.append({"材料编号": code, "reason": "同一批出库里材料编号重复，无法分别扣减", "item": item})
                continue

            entry, resolve_msg = _resolve_entry(code=code, entry_id=item.get("id"))
            if entry is None:
                failed.append({"材料编号": code, "reason": resolve_msg, "item": item})
                continue
            entry_code = str(entry.get("材料编号", "")).strip()

            quantity = _to_int(item.get("出库数量"))
            if quantity is None or quantity <= 0:
                failed.append({"材料编号": entry_code, "reason": "出库数量必须是大于 0 的整数", "item": item})
                continue
            team = str(item.get("领用班组") or "").strip()
            if not team:
                failed.append({"材料编号": entry_code, "reason": "领用班组未填写", "item": item})
                continue
            if str(entry.get("status") or "") == "已停用":
                failed.append({"材料编号": entry_code, "reason": "材料已停用，不允许出库", "item": item})
                continue

            submitted_spec = str(item.get("规格型号") or "").strip()
            ledger_spec = str(entry.get("规格型号") or "").strip()
            if submitted_spec and submitted_spec != ledger_spec:
                failed.append({
                    "材料编号": entry_code,
                    "reason": f"规格型号不匹配：提交为「{submitted_spec}」，台账为「{ledger_spec}」，禁止跨规格合并出库",
                    "item": item,
                })
                continue

            stock = _to_int(entry.get("当前存量"))
            if stock is None:
                failed.append({"材料编号": entry_code, "reason": "台账当前存量不是有效数字，无法扣减", "item": item})
                continue
            if quantity > stock:
                failed.append({
                    "材料编号": entry_code,
                    "reason": f"当前存量仅 {stock}，不足出库 {quantity}",
                    "item": item,
                })
                continue

            # 校验全部通过后才扣减；本行之后的任何异常都不会回滚这里。
            entry["当前存量"] = stock - quantity
            _refresh_status(entry)
            record = self._append_record(
                entry,
                OUTBOUND_TYPE,
                quantity,
                batch_no=batch_no,
                date_text=date_text,
                extra={"领用班组": team, "领用日期": date_text},
                remark=remark,
            )
            succeeded.append({"材料编号": entry_code, "record": record, "entry": dict(entry)})

        message = self._build_batch_message(len(succeeded), len(failed), "出库")
        return {
            "ok": not failed,
            "message": message,
            "batch_no": batch_no,
            "succeeded": succeeded,
            "failed": failed,
            "rejected": [],
        }

    def batch_inbound(
        self,
        items: list[dict[str, Any]],
        *,
        use_date: str | None = None,
        remark: str | None = None,
    ) -> dict[str, Any]:
        """整组提交入库：受潮/过期材料只登记拒收记录，合格材料才增加库存。"""
        date_text = str(use_date or "").strip() or _today()
        batch_no = f"IN-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        if not _valid_date(date_text):
            bad_date = date_text or "未填写"
            reason = f"入库日期「{bad_date}」不是合法日期，应为 YYYY-MM-DD"
            return {
                "ok": False,
                "message": reason,
                "batch_no": batch_no,
                "succeeded": [],
                "failed": [
                    {"材料编号": str(item.get("材料编号") or "").strip(), "reason": reason, "item": item}
                    for item in items
                    if str(item.get("质量判定") or DEFAULT_GRADE).strip() == DEFAULT_GRADE
                ],
                "rejected": [],
            }

        seen: set[str] = set()
        duplicate: set[str] = set()
        for item in items:
            code = str(item.get("材料编号") or "").strip()
            if code and code in seen:
                duplicate.add(code)
            if code:
                seen.add(code)

        succeeded: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        for item in items:
            code = str(item.get("材料编号") or "").strip()
            grade = str(item.get("质量判定") or DEFAULT_GRADE).strip()
            if grade not in QUALITY_GRADES:
                grade = DEFAULT_GRADE

            entry, resolve_msg = _resolve_entry(code=code, entry_id=item.get("id"))
            if entry is None:
                # 编号对不上台账就谈不上"挑出"，无论质量判定如何都按失败处理，要求用户修正
                failed.append({"材料编号": code, "reason": resolve_msg, "item": item})
                continue
            entry_code = str(entry.get("材料编号", "")).strip()

            if code in duplicate:
                # 重复编号无法逐行落账，受潮/过期行也一并拦下，让用户拆清后再提交
                target = rejected if grade in ("受潮", "过期") else failed
                target.append({"材料编号": entry_code, "reason": "同一批入库里材料编号重复，无法分别登记", "item": item})
                continue

            submitted_spec = str(item.get("规格型号") or "").strip()
            ledger_spec = str(entry.get("规格型号") or "").strip()
            if submitted_spec and submitted_spec != ledger_spec:
                reason = f"规格型号不匹配：提交为「{submitted_spec}」，台账为「{ledger_spec}」，禁止跨规格合并入库"
                target = rejected if grade in ("受潮", "过期") else failed
                target.append({"材料编号": entry_code, "reason": reason, "item": item})
                continue

            # 受潮/过期：单独登记拒收记录，不碰库存，不计入失败，也不需要重试。
            if grade in ("受潮", "过期"):
                record = self._append_record(
                    entry,
                    REJECT_TYPE,
                    0,
                    batch_no=batch_no,
                    date_text=date_text,
                    extra={"质量判定": grade, "供货单位": str(item.get("供货单位") or "").strip(), "入库日期": date_text},
                    remark=str(item.get("拒收原因") or "") or f"材料{grade}，不可入库",
                )
                rejected.append({"材料编号": entry_code, "reason": f"{grade}材料已挑出，登记拒收，未计入库存", "record": record})
                continue

            quantity = _to_int(item.get("入库数量"))
            if quantity is None or quantity <= 0:
                failed.append({"材料编号": entry_code, "reason": "入库数量必须是大于 0 的整数", "item": item})
                continue

            stock = _to_int(entry.get("当前存量"))
            if stock is None:
                failed.append({"材料编号": entry_code, "reason": "台账当前存量不是有效数字，无法增加", "item": item})
                continue

            entry["当前存量"] = stock + quantity
            _refresh_status(entry)
            record = self._append_record(
                entry,
                INBOUND_TYPE,
                quantity,
                batch_no=batch_no,
                date_text=date_text,
                extra={"供货单位": str(item.get("供货单位") or "").strip(), "入库日期": date_text, "质量判定": DEFAULT_GRADE},
                remark=remark,
            )
            succeeded.append({"材料编号": entry_code, "record": record, "entry": dict(entry)})

        message_parts = []
        if succeeded or not failed:
            message_parts.append(self._build_batch_message(len(succeeded), len(failed), "入库"))
        if rejected:
            message_parts.append(f"另有 {len(rejected)} 条受潮/过期材料已挑出登记拒收，未计入库存")
        message = "；".join(message_parts)
        return {
            "ok": not failed,
            "message": message,
            "batch_no": batch_no,
            "succeeded": succeeded,
            "failed": failed,
            "rejected": rejected,
        }

    def _append_record(
        self,
        entry: dict[str, Any],
        record_type: str,
        quantity: int,
        *,
        batch_no: str,
        date_text: str,
        extra: dict[str, Any] | None = None,
        remark: str | None = None,
    ) -> dict[str, Any]:
        """出入库记录挂在材料编号下面；材料编号 + 规格型号一并落账，不做合并。"""
        record: dict[str, Any] = {
            "id": _next_id(RECORD_MODULE),
            "批次号": batch_no,
            "类型": record_type,
            "材料编号": str(entry.get("材料编号", "")).strip(),
            "材料名称": entry.get("材料名称"),
            "规格型号": entry.get("规格型号"),
            "存放料场": entry.get("存放料场"),
            "数量": quantity,
            "日期": date_text,
            "经办时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        if extra:
            record.update({key: value for key, value in extra.items() if value not in (None, "")})
        if remark:
            record["备注"] = remark
        store.rows(RECORD_MODULE).append(record)
        return record

    @staticmethod
    def _build_batch_message(succeeded: int, failed: int, verb: str) -> str:
        if succeeded and not failed:
            return f"{verb}完成：{succeeded} 条成功"
        if succeeded and failed:
            return f"{verb}部分完成：{succeeded} 条已生效，{failed} 条被卡住，可仅重试失败项"
        if failed:
            return f"{verb}未生效：{failed} 条全部被卡住，按提示修正后重试即可"
        return "没有需要处理的材料"

    # ------------------------------------------------------------------
    # 记录与料场盘点：全部从同一份台账/记录派生
    # ------------------------------------------------------------------
    def list_records(
        self,
        *,
        keyword: str | None = None,
        record_type: str | None = None,
        yard: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = list(reversed(store.rows(RECORD_MODULE)))
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("材料编号", ""))]
        if record_type:
            rows = [row for row in rows if row.get("类型") == record_type]
        if yard:
            rows = [row for row in rows if str(row.get("存放料场") or "") == yard]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def yard_overview(self) -> dict[str, Any]:
        """料场盘点：按存放料场汇总台账存量，并回挂材料编号下的出入库流水。

        汇总数据由 material2 台账直接派生，不另存一份存量，
        所以料场盘点与材料台账的当前存量不可能对不上。
        """
        yards: dict[str, dict[str, Any]] = {}
        for entry in store.rows(MODULE):
            yard_name = str(entry.get("存放料场") or "未分配料场")
            bucket = yards.setdefault(
                yard_name,
                {"存放料场": yard_name, "材料种类": 0, "当前存量合计": 0, "不足种类": 0, "materials": []},
            )
            stock = _to_int(entry.get("当前存量")) or 0
            bucket["材料种类"] += 1
            bucket["当前存量合计"] += stock
            if entry.get("status") in ("不足", "待采购"):
                bucket["不足种类"] += 1
            bucket["materials"].append({
                "材料编号": entry.get("材料编号"),
                "材料名称": entry.get("材料名称"),
                "规格型号": entry.get("规格型号"),
                "当前存量": stock,
                "最低保有量": _to_int(entry.get("最低保有量")) or 0,
                "材料状态": entry.get("status"),
            })
        yard_list = sorted(yards.values(), key=lambda item: item["存放料场"])
        totals = {
            "料场数": len(yard_list),
            "材料种类": sum(item["材料种类"] for item in yard_list),
            "当前存量合计": sum(item["当前存量合计"] for item in yard_list),
        }
        records = store.rows(RECORD_MODULE)
        return {
            "source": "material2",
            "consistency": "盘点存量按材料台账实时汇总，台账调整后此处同步变化",
            "totals": totals,
            "yards": yard_list,
            "record_count": len(records),
        }
