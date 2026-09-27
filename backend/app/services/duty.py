"""值班交接业务规则：班次登记、批量回执、退回待办与进度口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "duty"
REQUIRED_FIELDS = ["班次", "值班班组", "交班人", "接班人"]
STATUS_ORDER = ["待交班", "待确认", "已交接", "部分退回"]
ITEM_RESULTS = ["确认", "退回"]


class DutyService:
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
            rows = [
                row for row in rows
                if keyword in str(row.get("班次", "")) or keyword in str(row.get("值班班组", ""))
            ]
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
        # 同一班次重复交班：作废旧登记与其回执，只保留最后一次
        shift = str(values["班次"]).strip()
        for old in [row for row in rows if row.get("班次") == shift]:
            rows.remove(old)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: str(values.get(field)).strip() for field in REQUIRED_FIELDS})
        entry["交接事项"] = [
            {"事项id": index + 1, "内容": text, "状态": "待确认", "原因": "", "批次": 0}
            for index, text in enumerate(self._parse_items(values.get("交接事项")))
        ]
        entry["待办事项"] = []
        entry["最近回执"] = []
        entry["回执批次"] = 0
        self._refresh(entry)
        rows.append(entry)
        return entry, []

    def submit_receipt(
        self, entry_id: int, items: list[dict[str, Any]]
    ) -> tuple[dict[str, Any] | None, str]:
        """接班人批量回执：逐条校验，单条不合格只影响自己，已处理的条目保留。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"值班记录 {entry_id} 不存在或已归档"
        if not items:
            return None, "回执里至少要有一条交接事项结论"
        entry["回执批次"] = int(entry.get("回执批次", 0)) + 1
        batch = entry["回执批次"]
        receipt: list[dict[str, Any]] = []
        failures: list[str] = []
        done = 0
        for raw in items:
            item_id = self._item_id(raw.get("事项id"))
            target = next(
                (item for item in entry["交接事项"] if item["事项id"] == item_id), None
            )
            result = str(raw.get("结论") or "").strip()
            reason = str(raw.get("原因") or "").strip()
            problem = self._validate(target, result, reason)
            if problem:
                failures.append(f"事项{item_id if item_id is not None else '?'}{problem}")
                receipt.append({"事项id": item_id, "结论": result, "通过": False, "说明": problem})
                continue
            assert target is not None
            target["状态"] = "已确认" if result == "确认" else "已退回"
            target["原因"] = reason
            target["批次"] = batch
            if result == "退回":
                # 退回的事项回到原班组待办，而不是消失
                entry.setdefault("待办事项", []).append(target["内容"])
            done += 1
            receipt.append({"事项id": item_id, "结论": result, "通过": True, "说明": reason})
        # 同一班次只保留最后一次回执
        entry["最近回执"] = receipt
        self._refresh(entry)
        message = f"第 {batch} 次回执已登记：处理 {done} 条"
        if failures:
            message += f"，未通过 {len(failures)} 条（{'；'.join(failures)}）"
        return entry, message

    def _validate(self, target: dict[str, Any] | None, result: str, reason: str) -> str | None:
        if target is None:
            return "不存在于本班次的交接事项里"
        if result not in ITEM_RESULTS:
            return "的结论只能是确认或退回"
        if not reason:
            return "缺少逐条原因说明"
        if target["状态"] != "待确认":
            return f"已是{target['状态']}状态，不能重复回执"
        return None

    def _refresh(self, entry: dict[str, Any]) -> None:
        items = entry.get("交接事项", [])
        total = len(items)
        confirmed = sum(1 for item in items if item["状态"] == "已确认")
        rejected = sum(1 for item in items if item["状态"] == "已退回")
        waiting = total - confirmed - rejected
        entry["交接进度"] = f"{confirmed}/{total}"
        if total == 0:
            entry["status"] = "待交班"
        elif waiting > 0:
            entry["status"] = "待确认"
        elif rejected > 0:
            entry["status"] = "部分退回"
        else:
            entry["status"] = "已交接"
        entry["pending"] = entry["status"] != "已交接"
        entry["abnormal"] = rejected > 0

    @staticmethod
    def _item_id(raw: Any) -> int | None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_items(raw: Any) -> list[str]:
        if isinstance(raw, str):
            candidates = raw.replace("；", "\n").replace(";", "\n").splitlines()
        elif isinstance(raw, list):
            candidates = [
                str(item.get("内容", "")) if isinstance(item, dict) else str(item)
                for item in raw
            ]
        else:
            candidates = []
        return [text.strip() for text in candidates if text and text.strip()]
