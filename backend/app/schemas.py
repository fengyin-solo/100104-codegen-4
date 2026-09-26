"""接口出入参模型：列表分页、动作结果与各模块的明细结构。"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    size: int = 20


class ActionResult(BaseModel):
    ok: bool
    message: str
    entry: dict[str, Any] | None = None


class EntryPayload(BaseModel):
    """登记或修改一条业务记录时提交的字段集合。"""

    values: dict[str, Any] = Field(default_factory=dict)
    remark: str | None = None


class BatchOutboundItem(BaseModel):
    """批量出库中的一行：按材料编号定位，规格型号用于防止不同规格被合并出库。"""

    材料编号: str
    出库数量: int | None = None
    领用班组: str | None = None
    规格型号: str | None = None


class BatchOutboundPayload(BaseModel):
    """整组出库提交：领用日期全组统一，领用班组逐条填写。"""

    领用日期: str
    items: list[BatchOutboundItem] = Field(default_factory=list)


class BatchInboundItem(BaseModel):
    """批量入库中的一行：质检结果为受潮、已过期的行会被拒收入库。"""

    材料编号: str
    入库数量: int | None = None
    质检结果: str = "合格"


class BatchInboundPayload(BaseModel):
    """整组入库提交：入库日期全组统一，质检结果逐条判定。"""

    入库日期: str
    items: list[BatchInboundItem] = Field(default_factory=list)


class BatchItemResult(BaseModel):
    """批量提交里单条材料的处理结果：成功带结存，失败带卡住原因。"""

    材料编号: str
    ok: bool
    message: str
    结存: int | None = None


class BatchResult(BaseModel):
    """整组提交的汇总：逐条成功失败互不牵连，失败的可单独重试。"""

    ok: bool
    message: str
    results: list[BatchItemResult] = Field(default_factory=list)



class FacilityEntry(BaseModel):
    """设施明细结构。"""

    field_0: str | None = None  # 设施编号
    field_1: str | None = None  # 设施名称
    field_2: str | None = None  # 设施类型
    field_3: str | None = None  # 所在路段
    field_4: str | None = None  # 管养单位
    field_5: str | None = None  # 建设年代
    field_6: str | None = None  # 设计等级
    field_7: str | None = None  # 设施状态

class BridgeEntry(BaseModel):
    """桥梁明细结构。"""

    field_0: str | None = None  # 桥梁编号
    field_1: str | None = None  # 桥梁名称
    field_2: str | None = None  # 桥型结构
    field_3: str | None = None  # 跨越对象
    field_4: str | None = None  # 桥面宽度
    field_5: str | None = None  # 桥长跨度
    field_6: str | None = None  # 设计荷载
    field_7: str | None = None  # 技术状况

class TunnelEntry(BaseModel):
    """隧道明细结构。"""

    field_0: str | None = None  # 隧道编号
    field_1: str | None = None  # 隧道名称
    field_2: str | None = None  # 隧道长度
    field_3: str | None = None  # 断面形式
    field_4: str | None = None  # 通风方式
    field_5: str | None = None  # 照明方式
    field_6: str | None = None  # 消防等级
    field_7: str | None = None  # 技术状况

class PavementEntry(BaseModel):
    """路面评价明细结构。"""

    field_0: str | None = None  # 评价编号
    field_1: str | None = None  # 道路名称
    field_2: str | None = None  # 评价路段
    field_3: str | None = None  # 路面损坏指数
    field_4: str | None = None  # 平整度指数
    field_5: str | None = None  # 车辙深度
    field_6: str | None = None  # 抗滑系数
    field_7: str | None = None  # 评价日期

class PatrolEntry(BaseModel):
    """巡查记录明细结构。"""

    field_0: str | None = None  # 巡查编号
    field_1: str | None = None  # 巡查路段
    field_2: str | None = None  # 巡查人员
    field_3: str | None = None  # 巡查日期
    field_4: str | None = None  # 巡查路线
    field_5: str | None = None  # 发现问题
    field_6: str | None = None  # 处置措施
    field_7: str | None = None  # 巡查状态

class DiseaseEntry(BaseModel):
    """病害明细结构。"""

    field_0: str | None = None  # 病害编号
    field_1: str | None = None  # 所属设施
    field_2: str | None = None  # 病害类型
    field_3: str | None = None  # 严重等级
    field_4: str | None = None  # 发现时间
    field_5: str | None = None  # 所在位置
    field_6: str | None = None  # 处置方案
    field_7: str | None = None  # 病害状态

class RepairEntry(BaseModel):
    """维修任务明细结构。"""

    field_0: str | None = None  # 任务编号
    field_1: str | None = None  # 任务类型
    field_2: str | None = None  # 维修对象
    field_3: str | None = None  # 维修内容
    field_4: str | None = None  # 施工队伍
    field_5: str | None = None  # 计划工期
    field_6: str | None = None  # 造价预估
    field_7: str | None = None  # 任务状态

class Material2Entry(BaseModel):
    """养护材料明细结构。"""

    field_0: str | None = None  # 材料编号
    field_1: str | None = None  # 材料名称
    field_2: str | None = None  # 规格型号
    field_3: str | None = None  # 适用场景
    field_4: str | None = None  # 存放料场
    field_5: str | None = None  # 最低保有量
    field_6: str | None = None  # 当前存量
    field_7: str | None = None  # 材料状态

class MachineEntry(BaseModel):
    """养护机械明细结构。"""

    field_0: str | None = None  # 机械编号
    field_1: str | None = None  # 机械名称
    field_2: str | None = None  # 规格型号
    field_3: str | None = None  # 所属班组
    field_4: str | None = None  # 购置日期
    field_5: str | None = None  # 年检日期
    field_6: str | None = None  # 操作人员
    field_7: str | None = None  # 机械状态

class EmergencyEntry(BaseModel):
    """应急事件明细结构。"""

    field_0: str | None = None  # 事件编号
    field_1: str | None = None  # 事件类型
    field_2: str | None = None  # 发生地点
    field_3: str | None = None  # 影响范围
    field_4: str | None = None  # 响应等级
    field_5: str | None = None  # 出动班组
    field_6: str | None = None  # 处置结果
    field_7: str | None = None  # 事件状态

class DeicingEntry(BaseModel):
    """除雪防汛明细结构。"""

    field_0: str | None = None  # 作业编号
    field_1: str | None = None  # 作业类型
    field_2: str | None = None  # 作业路段
    field_3: str | None = None  # 物资消耗
    field_4: str | None = None  # 出动人员
    field_5: str | None = None  # 作业起止
    field_6: str | None = None  # 作业效果
    field_7: str | None = None  # 作业状态

class OccupyEntry(BaseModel):
    """占道施工明细结构。"""

    field_0: str | None = None  # 施工编号
    field_1: str | None = None  # 施工位置
    field_2: str | None = None  # 占用范围
    field_3: str | None = None  # 施工内容
    field_4: str | None = None  # 申请人
    field_5: str | None = None  # 审批人
    field_6: str | None = None  # 占用期限
    field_7: str | None = None  # 施工状态

class GreeningEntry(BaseModel):
    """绿化管护明细结构。"""

    field_0: str | None = None  # 管护编号
    field_1: str | None = None  # 管护区域
    field_2: str | None = None  # 植被类型
    field_3: str | None = None  # 修剪频次
    field_4: str | None = None  # 浇水周期
    field_5: str | None = None  # 病虫害防治
    field_6: str | None = None  # 管护人员
    field_7: str | None = None  # 管护状态

class Safety2Entry(BaseModel):
    """交安设施明细结构。"""

    field_0: str | None = None  # 设施编号
    field_1: str | None = None  # 设施类型
    field_2: str | None = None  # 所在路段
    field_3: str | None = None  # 桩号位置
    field_4: str | None = None  # 设施规格
    field_5: str | None = None  # 设置日期
    field_6: str | None = None  # 养护记录
    field_7: str | None = None  # 设施状态

class GeomEntry(BaseModel):
    """边坡挡墙明细结构。"""

    field_0: str | None = None  # 边坡编号
    field_1: str | None = None  # 所属路段
    field_2: str | None = None  # 边坡类型
    field_3: str | None = None  # 支护形式
    field_4: str | None = None  # 监测点位
    field_5: str | None = None  # 变形速率
    field_6: str | None = None  # 巡查日期
    field_7: str | None = None  # 边坡状态

class LightEntry(BaseModel):
    """路灯设施明细结构。"""

    field_0: str | None = None  # 灯杆编号
    field_1: str | None = None  # 所在路段
    field_2: str | None = None  # 灯型类别
    field_3: str | None = None  # 功率瓦数
    field_4: str | None = None  # 亮灯时段
    field_5: str | None = None  # 故障类型
    field_6: str | None = None  # 报修日期
    field_7: str | None = None  # 亮灯状态

class DrainEntry(BaseModel):
    """排水设施明细结构。"""

    field_0: str | None = None  # 设施编号
    field_1: str | None = None  # 设施类型
    field_2: str | None = None  # 所在路段
    field_3: str | None = None  # 管径规格
    field_4: str | None = None  # 淤积深度
    field_5: str | None = None  # 疏通日期
    field_6: str | None = None  # 养护人员
    field_7: str | None = None  # 排水状态

class PlanEntry(BaseModel):
    """养护计划明细结构。"""

    field_0: str | None = None  # 计划编号
    field_1: str | None = None  # 计划周期
    field_2: str | None = None  # 计划类型
    field_3: str | None = None  # 覆盖设施
    field_4: str | None = None  # 计划内容
    field_5: str | None = None  # 预算金额
    field_6: str | None = None  # 编制人
    field_7: str | None = None  # 计划状态

class ComplaintEntry(BaseModel):
    """热线记录明细结构。"""

    field_0: str | None = None  # 记录编号
    field_1: str | None = None  # 来电人
    field_2: str | None = None  # 来电内容
    field_3: str | None = None  # 问题位置
    field_4: str | None = None  # 问题类型
    field_5: str | None = None  # 转办部门
    field_6: str | None = None  # 处理结果
    field_7: str | None = None  # 记录状态

class LoadEntry(BaseModel):
    """超限记录明细结构。"""

    field_0: str | None = None  # 记录编号
    field_1: str | None = None  # 抓拍路段
    field_2: str | None = None  # 车辆类型
    field_3: str | None = None  # 轴重数据
    field_4: str | None = None  # 总重数据
    field_5: str | None = None  # 超限比率
    field_6: str | None = None  # 执法单位
    field_7: str | None = None  # 处置状态
