"""值班交接接口：按班次登记值班班组，接班人批量回执交接事项的确认或退回。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.duty import DutyService

router = APIRouter(prefix="/api/duty", tags=["值班交接"])

service = DutyService()

LIST_FIELDS = ["班次", "值班班组", "交班人", "接班人", "交接进度", "待办事项", "交接状态"]
STATUSES = ["待交班", "待确认", "已交接", "部分退回"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按班次或值班班组检索"),
    status: str | None = Query(default=None, description="待交班、待确认、已交接、部分退回"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按班次/班组与状态过滤值班交接列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出值班交接清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "duty", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条值班交接明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"值班记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一次交班：班次、值班班组、交班人、接班人缺一不可，缺哪个说哪个。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="交班已登记，等待接班人回执", entry=entry)


@router.post("/{entry_id}/receipt", response_model=ActionResult)
def submit_receipt(entry_id: int, payload: EntryPayload) -> ActionResult:
    """接班人一次提交多条确认/退回结论；单条不合格不拖累整批，已处理的条目保留。"""
    raw_items = payload.values.get("items")
    if not isinstance(raw_items, list):
        return ActionResult(ok=False, message="回执格式不对：items 应该是交接事项结论数组")
    entry, message = service.submit_receipt(entry_id, raw_items)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
