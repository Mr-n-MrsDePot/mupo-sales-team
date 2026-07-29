"""Tools for reading MUPO knowledge base content."""

from __future__ import annotations

import json
from typing import Any, Type

from pydantic import BaseModel, Field

from mupo_sales.memory.knowledge import get_kb


def lookup_package(product_id: str) -> str:
    kb = get_kb()
    pkg = kb.get_package(product_id)
    if not pkg:
        return json.dumps({"error": "not_found", "product_id": product_id, "available": [p["id"] for p in kb.load_packages().get("packages", [])]})
    return json.dumps(pkg, indent=2)


def list_packages() -> str:
    return get_kb().list_package_summaries()


def get_sequence(product_id: str) -> str:
    seq = get_kb().load_sequence(product_id)
    if not seq:
        return json.dumps({"error": "no_sequence", "product_id": product_id})
    return json.dumps(seq, indent=2, default=str)


def compliance_rules() -> str:
    return get_kb().load_compliance_md()


def company_overview() -> str:
    return get_kb().load_company_md()


def get_crewai_tools() -> list[Any]:
    try:
        from crewai.tools import BaseTool
    except ImportError:
        return []

    class PackageInput(BaseModel):
        product_id: str = Field(description="Package id e.g. tv_sponsorship, tv_membership")

    class LookupPackageTool(BaseTool):
        name: str = "lookup_package"
        description: str = "Load full rate card / package JSON for a product_id from the MUPO knowledge base."
        args_schema: Type[BaseModel] = PackageInput

        def _run(self, product_id: str) -> str:
            return lookup_package(product_id)

    class ListPackagesTool(BaseTool):
        name: str = "list_packages"
        description: str = "List all MUPO product packages with price ranges."

        def _run(self) -> str:
            return list_packages()

    class SequenceTool(BaseTool):
        name: str = "get_outreach_sequence"
        description: str = "Load outreach sequence template for a product_id."
        args_schema: Type[BaseModel] = PackageInput

        def _run(self, product_id: str) -> str:
            return get_sequence(product_id)

    class ComplianceTool(BaseTool):
        name: str = "compliance_rules"
        description: str = "Return MUPO sales compliance rules and forbidden claims."

        def _run(self) -> str:
            return compliance_rules()

    return [LookupPackageTool(), ListPackagesTool(), SequenceTool(), ComplianceTool()]
