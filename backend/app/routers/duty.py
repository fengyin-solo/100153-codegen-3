"""值班交接班接口：值班栏看板、班组待办、交班登记与接班批量评审。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas import ActionResult, HandoverCreatePayload, HandoverReviewPayload
from app.services.duty import DutyService

router = APIRouter(prefix="/api/duty", tags=["值班交接班"])

service = DutyService()


@router.get("/board")
def board() -> dict[str, object]:
    """值班栏：当前班次、交接进度与班组待办总数，供顶栏和值班页同步。"""
    return service.board()


@router.get("/todos")
def list_todos(team: str | None = None) -> dict[str, object]:
    """班组待办事项清单；可按班组过滤，交班登记时据此勾选挂起。"""
    items = service.list_todos(team=team)
    return {"items": items, "total": len(items)}


@router.get("/shifts")
def list_shifts() -> dict[str, object]:
    """交接回执列表：同一班次重复交班只保留最后一次回执。"""
    items = service.list_shifts()
    return {"items": items, "total": len(items)}


@router.get("/shifts/{shift_id}")
def get_shift(shift_id: int) -> dict[str, object]:
    """回执明细：班次信息加逐条交接事项及处理结果。"""
    shift = service.get_shift(shift_id)
    if shift is None:
        raise HTTPException(status_code=404, detail=f"班次交接回执 {shift_id} 不存在")
    return shift


@router.post("/shifts", response_model=ActionResult)
def create_shift(payload: HandoverCreatePayload) -> ActionResult:
    """按班次登记交班；班次、交班班组、交班人、接班人缺失时逐一说明。"""
    shift, missing, warnings = service.create_handover(payload.model_dump())
    if missing:
        return ActionResult(ok=False, message=f"缺少必填项：{'、'.join(missing)}")
    message = "交接回执已登记，等待接班人确认"
    if warnings:
        message += f"；另有 {len(warnings)} 条挂起事项未生效：{'；'.join(warnings)}"
    return ActionResult(ok=True, message=message, entry=shift)


@router.post("/shifts/{shift_id}/review")
def review_shift(shift_id: int, payload: HandoverReviewPayload) -> dict[str, object]:
    """接班人一次提交多条确认或退回结果；逐条返回成败，部分失败不回滚已成功条目。"""
    summary, results, error = service.review(shift_id, [item.model_dump() for item in payload.decisions])
    if error:
        raise HTTPException(status_code=400, detail=error)
    return {"ok": True, "results": results, **summary}
