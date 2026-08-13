import json
from pathlib import Path
from datetime import datetime
from typing import Any, Dict

LOG_PATH = Path("data/metrics.log.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

def log_event(event: str, payload: Dict[str, Any]) -> None:
    try:
        record = {
            "event": event,
            "ts": datetime.utcnow().isoformat() + "Z",
            **payload,
        }
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        # Nunca romper el flujo por logging
        pass
