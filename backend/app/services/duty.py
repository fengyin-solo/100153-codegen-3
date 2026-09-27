"""值班交接班业务规则：交班登记、同班次回执覆盖、接班批量评审与待办回流。

数据落在三张内存表里：
- duty_todo：班组待办事项（种子数据里已有示例）；退回的交接事项回到这里，状态仍为待办；
- handover_shift：交接回执（一个班次最后一次交班只保留一条）；
- handover_item：回执下的交接事项，逐条记录接班人的处理结果。
"""
from __future__ import annotations

from typing import Any

from app.store import store

TODO_MODULE = "duty_todo"
SHIFT_MODULE = "handover_shift"
ITEM_MODULE = "handover_item"

REQUIRED_FIELDS = ["班次", "交班班组", "交班人", "接班人"]
STATUS_PENDING = "待接班"
STATUS_PARTIAL = "部分确认"
STATUS_DONE = "交接完成"


def _now() -> str:
    """演示用时间戳：内存仓库不引入额外依赖，直接用可读字符串。"""
    from datetime import datetime

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _next_id(rows: list[dict[str, Any]]) -> int:
    return max((int(row.get("id", 0)) for row in rows), default=0) + 1


def _next_todo_no() -> str:
    rows = store.rows(TODO_MODULE)
    max_no = 0
    for row in rows:
        no = str(row.get("事项编号", ""))
        if no.startswith("TODO-"):
            try:
                max_no = max(max_no, int(no.removeprefix("TODO-")))
            except ValueError:
                continue
    return f"TODO-{max_no + 1:04d}"


def _shift_progress(shift_id: int) -> tuple[int, int, str]:
    """汇总一条回执下的交接进度，返回 (已处理数, 总数, 班次状态)。"""
    items = [row for row in store.rows(ITEM_MODULE) if row.get("shift_id") == shift_id]
    total = len(items)
    done = sum(1 for row in items if row.get("result") != "待确认")
    if done == 0:
        status = STATUS_PENDING
    elif done < total:
        status = STATUS_PARTIAL
    else:
        status = STATUS_DONE
    return done, total, status


def _serialize_shift(shift: dict[str, Any]) -> dict[str, Any]:
    done, total, _ = _shift_progress(int(shift["id"]))
    data = dict(shift)
    data["processed"] = done
    data["total"] = total
    return data


class DutyService:
    # ---------- 值班页 ----------

    def board(self) -> dict[str, Any]:
        """值班栏数据：最近一条回执决定当前班次与交接进度。"""
        shifts = store.rows(SHIFT_MODULE)
        todo_count = sum(1 for row in store.rows(TODO_MODULE) if row.get("pending"))
        latest = shifts[-1] if shifts else None
        if latest is None:
            return {"current_shift": None, "shift": "", "handover_progress": "暂无交接记录", "todo_count": todo_count}
        done, total, status = _shift_progress(int(latest["id"]))
        return {
            "current_shift": _serialize_shift(latest),
            "shift": latest["班次"],
            "handover_progress": f"{status}（{done}/{total}）" if total else f"{status}（0 项）",
            "todo_count": todo_count,
        }

    def list_todos(self, team: str | None = None) -> list[dict[str, Any]]:
        """班组待办清单，默认只看待办；用于交班时勾选挂起。"""
        rows = [row for row in store.rows(TODO_MODULE) if row.get("pending")]
        if team:
            rows = [row for row in rows if row.get("所属班组") == team]
        return rows

    # ---------- 交班登记 ----------

    def create_handover(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str], list[str]]:
        """登记一次交班。

        返回 (回执, 缺失必填项, 被忽略的挂起事项说明)；同一班次重复交班时，
        旧回执及其事项整条作废，旧回执里未处理的事项还原回班组待办。
        """
        def clean(key: str) -> str:
            return str(values.get(key) or "").strip()

        shift_name, team = clean("shift"), clean("team")
        handover_person, receiver_person = clean("handover_person"), clean("receiver_person")
        receiver_team = clean("receiver_team") or team

        form = {
            "班次": shift_name,
            "交班班组": team,
            "交班人": handover_person,
            "接班人": receiver_person,
        }
        missing = [label for label in REQUIRED_FIELDS if not form[label]]
        if missing:
            return None, missing, []

        shifts = store.rows(SHIFT_MODULE)
        items_table = store.rows(ITEM_MODULE)
        todos = store.rows(TODO_MODULE)

        # 同一班次重复交班：旧回执作废，其下未处理事项从“交接中”还原回待办
        old = next((row for row in shifts if row.get("班次") == shift_name), None)
        if old is not None:
            old_id = int(old["id"])
            for item in items_table:
                if item.get("shift_id") != old_id:
                    continue
                if item.get("result") != "待确认":
                    continue
                todo_id = item.get("todo_id")
                if isinstance(todo_id, int):
                    source = next((row for row in todos if int(row.get("id", 0)) == todo_id), None)
                    if source is not None:
                        source["status"] = "待办"
                        source["pending"] = True
            shifts.remove(old)
            items_table[:] = [row for row in items_table if row.get("shift_id") != old_id]

        shift_id = _next_id(shifts)
        shift = {
            "id": shift_id,
            "班次": shift_name,
            "交班班组": team,
            "交班人": handover_person,
            "接班人": receiver_person,
            "接班班组": receiver_team,
            "交班时刻": _now(),
            "status": STATUS_PENDING,
            "pending": True,
            "abnormal": False,
        }
        shifts.append(shift)

        warnings: list[str] = []
        raw_ids = values.get("item_ids") or []
        try:
            item_ids = [int(value) for value in raw_ids]
        except (TypeError, ValueError):
            item_ids = []
            warnings.append("挂起事项编号存在非法值，已整体忽略勾选内容")

        picked: set[int] = set()
        for todo_id in item_ids:
            todo = next((row for row in todos if int(row.get("id", 0)) == todo_id), None)
            if todo is None:
                warnings.append(f"待办事项 {todo_id} 不存在或已办结，未挂入本次交接")
                continue
            if not todo.get("pending"):
                warnings.append(f"待办事项「{todo.get('事项内容', '')}」已办结，未挂入本次交接")
                continue
            if todo_id in picked:
                continue
            picked.add(todo_id)
            items_table.append({
                "id": _next_id(items_table),
                "shift_id": shift_id,
                "todo_id": todo_id,
                "事项内容": todo.get("事项内容", ""),
                "来源班组": todo.get("所属班组", team),
                "result": "待确认",
                "处理原因": "",
                "处理时刻": None,
            })
            todo["status"] = "交接中"
            todo["pending"] = False

        for raw in values.get("extra_items") or []:
            content = str(raw or "").strip()
            if not content:
                continue
            items_table.append({
                "id": _next_id(items_table),
                "shift_id": shift_id,
                "todo_id": None,
                "事项内容": content,
                "来源班组": team,
                "result": "待确认",
                "处理原因": "",
                "处理时刻": None,
            })

        return _serialize_shift(shift), [], warnings

    def list_shifts(self) -> list[dict[str, Any]]:
        return [_serialize_shift(row) for row in reversed(store.rows(SHIFT_MODULE))]

    def get_shift(self, shift_id: int) -> dict[str, Any] | None:
        shift = store.find(SHIFT_MODULE, shift_id)
        if shift is None:
            return None
        data = _serialize_shift(shift)
        data["items"] = [
            dict(row) for row in store.rows(ITEM_MODULE) if row.get("shift_id") == shift_id
        ]
        return data

    # ---------- 接班批量评审 ----------

    def review(self, shift_id: int, decisions: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str]:
        """批量处理交接事项。

        逐条独立落库：一条不合格只影响该条，已经处理好的条目原样保留。
        返回 (回执汇总, 逐条结果, 整单级错误说明)。
        """
        shift = store.find(SHIFT_MODULE, shift_id)
        if shift is None:
            return None, [], f"班次交接回执 {shift_id} 不存在"
        if not decisions:
            return None, [], "没有提交任何交接事项的处理结果，请逐条选择确认或退回"

        results: list[dict[str, Any]] = []
        processed = 0
        failed = 0
        items_table = store.rows(ITEM_MODULE)

        for decision in decisions:
            try:
                item_id = int(decision.get("item_id"))
            except (TypeError, ValueError):
                item_id = -1
            action = str(decision.get("action") or "").strip()
            reason = str(decision.get("reason") or "").strip()

            item = next(
                (row for row in items_table if int(row.get("id", 0)) == item_id and row.get("shift_id") == shift_id),
                None,
            )
            if item is None:
                failed += 1
                results.append({"item_id": item_id, "ok": False, "message": f"交接事项 {item_id} 不属于本次回执或不存在，已跳过"})
                continue
            if item["result"] != "待确认":
                failed += 1
                results.append({"item_id": item_id, "ok": False, "message": f"该事项已{item['result']}，不能重复处理，已保留原结果"})
                continue
            if action not in ("confirm", "return"):
                failed += 1
                results.append({"item_id": item_id, "ok": False, "message": "处理动作只能是确认或退回，该条未生效"})
                continue
            if not reason:
                failed += 1
                label = "确认说明" if action == "confirm" else "退回原因"
                results.append({"item_id": item_id, "ok": False, "message": f"请填写{label}，该条未生效"})
                continue

            if action == "confirm":
                item["result"] = "已确认"
                self._sync_todo(item, target_team=shift.get("接班班组"), return_back=False)
            else:
                item["result"] = "已退回"
                self._sync_todo(item, target_team=item.get("来源班组"), return_back=True)
            item["处理原因"] = reason
            item["处理时刻"] = _now()
            processed += 1
            results.append({"item_id": item_id, "ok": True, "message": f"事项已{item['result']}"})

        done, total, status = _shift_progress(shift_id)
        shift["status"] = status
        shift["pending"] = done < total
        shift["abnormal"] = any(
            row.get("result") == "已退回"
            for row in items_table
            if row.get("shift_id") == shift_id
        )

        summary = {
            "shift": _serialize_shift(shift),
            "processed": processed,
            "failed": failed,
            "total": total,
            "all_done": done >= total,
            "message": (
                f"提交完成：{processed} 条已生效，{failed} 条未生效"
                if failed
                else f"提交完成：{processed} 条已全部生效"
            ),
        }
        return summary, results, ""

    def _sync_todo(self, item: dict[str, Any], target_team: str | None, *, return_back: bool) -> None:
        """处理结果落到班组待办：确认后转入接班班组，退回则回到原班组待办。"""
        todos = store.rows(TODO_MODULE)
        todo_id = item.get("todo_id")
        source: dict[str, Any] | None = None
        if isinstance(todo_id, int):
            source = next((row for row in todos if int(row.get("id", 0)) == todo_id), None)

        if source is not None:
            source["所属班组"] = target_team or source.get("所属班组")
            source["status"] = "待办"
            source["pending"] = True
            source["来源"] = "交接退回" if return_back else "交接接收"
            return

        todos.append({
            "id": _next_id(todos),
            "status": "待办",
            "pending": True,
            "abnormal": False,
            "事项编号": _next_todo_no(),
            "事项内容": item.get("事项内容", ""),
            "所属班组": target_team or item.get("来源班组", ""),
            "登记时刻": _now(),
            "来源": "交接退回" if return_back else "交接接收",
        })
