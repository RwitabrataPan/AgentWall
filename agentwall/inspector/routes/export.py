from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import joinedload

from agentwall.inspector.deps import get_db
from agentwall.storage.models import ToolEvent

router = APIRouter(prefix="/api/export", tags=["export"])

_FIELDS = [
    "event_id", "session_id", "tool_name", "tool_type", "action",
    "target", "resource_category", "timestamp",
    "decision", "risk_score", "reason", "alignment_score",
    "detector_hits", "policy_matched", "llm_used", "arguments",
]


@router.get("")
def export_data(
    format: str = Query("json", pattern="^(json|csv)$"),
    session_id: str | None = Query(None),
    db=Depends(get_db),
):
    with db.session() as s:
        q = s.query(ToolEvent).options(joinedload(ToolEvent.evaluation))
        if session_id:
            q = q.filter(ToolEvent.session_id == session_id)
        rows = q.order_by(ToolEvent.timestamp).all()

        data = []
        for r in rows:
            ev = r.evaluation
            data.append({
                "event_id": r.id,
                "session_id": r.session_id,
                "tool_name": r.tool_name,
                "tool_type": r.tool_type,
                "action": r.action,
                "target": r.target,
                "resource_category": r.resource_category,
                "timestamp": r.timestamp,
                "decision": ev.decision if ev else None,
                "risk_score": ev.risk_score if ev else None,
                "reason": ev.reason if ev else None,
                "alignment_score": ev.alignment_score if ev else None,
                "detector_hits": ev.detector_hits if ev else None,
                "policy_matched": ev.policy_matched if ev else None,
                "llm_used": ev.llm_used if ev else None,
                "arguments": r.arguments,
            })

    filename_base = f"agentwall_{session_id or 'all'}"

    if format == "json":
        return Response(
            content=json.dumps(data, indent=2, default=str),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={filename_base}.json"},
        )

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_FIELDS)
    writer.writeheader()
    for row in data:
        row["arguments"] = json.dumps(row.get("arguments") or {})
        row["detector_hits"] = json.dumps(row.get("detector_hits") or [])
        writer.writerow(row)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename_base}.csv"},
    )
