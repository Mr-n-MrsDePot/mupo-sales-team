"""Structured action logging for transparency and commission attribution."""

from __future__ import annotations

import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mupo_sales.config import get_settings


def setup_logging() -> None:
    s = get_settings()
    level = getattr(logging, s.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )


class ActionLogger:
    """
    Append-only JSONL log of every agent action.

    Used for:
      - Audit trail
      - Commission attribution (who touched the deal)
      - Dashboard activity feed
    """

    def __init__(self, path: Path | None = None) -> None:
        s = get_settings()
        self.path = path or (s.data_dir / "logs" / "actions.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        *,
        agent: str,
        action: str,
        deal_id: str | None = None,
        lead_id: str | None = None,
        details: dict[str, Any] | None = None,
        attribution: str | None = None,
    ) -> dict[str, Any]:
        record = {
            "id": str(uuid.uuid4()),
            "ts": datetime.now(timezone.utc).isoformat(),
            "agent": agent,
            "action": action,
            "deal_id": deal_id,
            "lead_id": lead_id,
            "attribution": attribution or agent,
            "details": details or {},
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
        logging.getLogger("mupo.actions").info(
            "%s | %s | deal=%s lead=%s", agent, action, deal_id, lead_id
        )
        return record

    def read_all(self, limit: int = 200) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows[-limit:]


# Module-level singleton
action_logger = ActionLogger()
