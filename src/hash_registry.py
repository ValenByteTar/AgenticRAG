import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

class HashRegistry:
    def __init__(self, store_path: str = "data/ingest_registry.json"):
        self.store_path = Path(store_path)
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._data = {"entries": []}
        self._index = {}
        self._load()

    def _load(self) -> None:
        if self.store_path.exists():
            try:
                self._data = json.loads(self.store_path.read_text(encoding="utf-8"))
                for e in self._data.get("entries", []):
                    self._index[e["hash"]] = e
            except Exception:
                self._data = {"entries": []}
                self._index = {}

    def _save(self) -> None:
        self.store_path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def compute_hash(text: str) -> str:
        h = hashlib.sha256()
        h.update(text.encode("utf-8"))
        return h.hexdigest()

    def exists(self, content_hash: str) -> bool:
        return content_hash in self._index

    def add(self, *, content_hash: str, filename: str, filepath: str, extra: Optional[Dict] = None) -> None:
        entry = {
            "hash": content_hash,
            "filename": filename,
            "filepath": filepath,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        if extra:
            entry.update(extra)
        self._data["entries"].append(entry)
        self._index[content_hash] = entry
        self._save()
