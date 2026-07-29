"""
Knowledge base loader for MUPO packages, compliance, and sequences.

v1: structured files on disk.
Optional: Chroma vector memory when ENABLE_VECTOR_MEMORY=true.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from mupo_sales.config import get_settings

logger = logging.getLogger(__name__)


class KnowledgeBase:
    def __init__(self, root: Path | None = None) -> None:
        s = get_settings()
        self.root = root or s.knowledge_dir

    @property
    def packages_path(self) -> Path:
        return self.root / "packages.json"

    def load_packages(self) -> dict[str, Any]:
        with open(self.packages_path, encoding="utf-8") as f:
            return json.load(f)

    def load_company_md(self) -> str:
        path = self.root / "company.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def load_compliance_md(self) -> str:
        path = self.root / "compliance.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def get_package(self, product_id: str) -> dict[str, Any] | None:
        for p in self.load_packages().get("packages", []):
            if p.get("id") == product_id:
                return p
        return None

    def list_package_summaries(self) -> str:
        lines = []
        for p in self.load_packages().get("packages", []):
            lines.append(
                f"- {p['id']}: {p['name']} "
                f"(${p['price_min']:,}–${p['price_max']:,}) "
                f"human_close={p.get('requires_human_close')}"
            )
        note = self.load_packages().get("disclaimer", "")
        return "MUPO Packages:\n" + "\n".join(lines) + f"\n\nDisclaimer: {note}"

    def load_sequence(self, product_id: str) -> dict[str, Any] | None:
        seq_dir = self.root / "outreach_sequences"
        # Map product to sequence file
        mapping = {
            "tv_sponsorship": "sponsorship.yaml",
            "commercial_30s": "commercial.yaml",
            "tv_membership": "membership.yaml",
            "magazine_ad": "magazine.yaml",
            "artist_dev": "artist_dev.yaml",
        }
        fname = mapping.get(product_id)
        if not fname:
            return None
        path = seq_dir / fname
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def verified_metrics_block(self) -> str:
        vm = self.load_packages().get("verified_metrics", {})
        return (
            "VERIFIED METRICS POLICY:\n"
            f"{json.dumps(vm, indent=2)}\n"
            "If public_claim_allowed is false, use only safe_language in outreach."
        )

    def agent_context_bundle(self) -> str:
        """Compact context string injected into agent backstories/tasks."""
        return (
            f"{self.load_company_md()}\n\n"
            f"{self.list_package_summaries()}\n\n"
            f"{self.verified_metrics_block()}\n\n"
            f"COMPLIANCE:\n{self.load_compliance_md()}"
        )


@lru_cache
def get_kb() -> KnowledgeBase:
    return KnowledgeBase()


class SharedMemory:
    """
    Simple structured run memory shared across agents in a session.

    Keys are free-form; values are JSON-serializable.
    Persists to data/memory/session.json for continuity.
    """

    def __init__(self, path: Path | None = None) -> None:
        s = get_settings()
        self.path = path or (s.data_dir / "memory" / "session.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, Any] = {}
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self._data = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self.save()

    def update(self, mapping: dict[str, Any]) -> None:
        self._data.update(mapping)
        self.save()

    def save(self) -> None:
        self.path.write_text(json.dumps(self._data, indent=2, default=str), encoding="utf-8")

    def as_context(self) -> str:
        if not self._data:
            return "(no shared memory yet)"
        return json.dumps(self._data, indent=2, default=str)[:8000]


def try_init_vector_store() -> Any | None:
    """Optional Chroma vector store for long-term knowledge retrieval."""
    s = get_settings()
    if not s.enable_vector_memory:
        return None
    try:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        client = chromadb.PersistentClient(
            path=str(s.data_dir / "memory" / "chroma"),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        collection = client.get_or_create_collection("mupo_knowledge")
        # Seed once if empty
        if collection.count() == 0:
            kb = get_kb()
            docs = [
                kb.load_company_md(),
                kb.load_compliance_md(),
                json.dumps(kb.load_packages()),
            ]
            ids = ["company", "compliance", "packages"]
            collection.add(documents=docs, ids=ids)
            logger.info("Seeded Chroma knowledge collection with %d docs", len(ids))
        return collection
    except Exception as e:
        logger.warning("Vector memory unavailable: %s", e)
        return None
