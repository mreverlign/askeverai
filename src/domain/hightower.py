"""Validated HighTower schema relationships and routing rules.

The source relationship CSV is incomplete and contains shifted columns.  This
module is deliberately small and explicit so SQL generation never relies on a
join that does not exist in the loaded databases.
"""

from __future__ import annotations

import re
from collections import deque
from typing import Dict, Iterable, List, Optional, Sequence, Set


OLAP_TABLES = frozenset(
    {
        "dim_date",
        "dim_item",
        "dim_transaction_status",
        "dim_transaction_type",
        "fact_transaction_detail",
    }
)

OLTP_TABLES = frozenset(
    {
        "dim_brand_partner_item",
        "dim_client",
        "dim_client_category",
        "dim_date",
        "dim_dealer_alignment",
        "dim_design_firm",
        "dim_end_user",
        "dim_end_user_type",
        "dim_item",
        "dim_item_category",
        "dim_partner",
        "dim_project",
        "dim_project_manager",
        "dim_project_type",
        "dim_sales_rep",
        "dim_specifier1",
        "dim_specifier2",
        "dim_specifier_sub_type",
        "dim_specifier_type",
        "dim_subcategory_item",
        "dim_transaction_status",
        "dim_transaction_type",
        "dim_vertical_market",
        "fact_transaction_detail",
    }
)

TABLES_BY_LAYER = {"OLAP": OLAP_TABLES, "OLTP": OLTP_TABLES}

# These ranges are verified during ingestion and are included in the prompt so
# phrases such as "current month" are not silently interpreted as "latest
# available month".
DATA_COVERAGE = {
    "OLAP": {"min_dateid": 20210104, "max_dateid": 20251231},
    "OLTP": {"min_dateid": 20210104, "max_dateid": 20260127},
}

FACT_ROW_COUNTS = {"OLAP": 351345, "OLTP": 356243}

TRANSACTION_TYPES = {
    "invoice": 1000,
    "quotation": 1001,
    "sales_order": 1002,
    "credit_memo": 1004,
}

SALES_SUBTOTAL_ITEM_IDS = (
    "Subtotal for Tariff Recovery Fee",
    "Subtotal for Canadian Tariff Credit",
)


def _relationship(
    left_table: str,
    left_column: str,
    right_table: str,
    right_column: str,
    *,
    layer: str,
    coverage: str = "complete",
    note: str = "",
) -> Dict[str, str]:
    return {
        "left_table": left_table,
        "left_column": left_column,
        "right_table": right_table,
        "right_column": right_column,
        "layer": layer,
        "coverage": coverage,
        "note": note,
        # Backward-compatible names consumed by the existing RAG formatter.
        "primary_table": right_table,
        "primary_key": right_column,
        "foreign_table": left_table,
        "foreign_key": left_column,
        "from": left_table,
        "to": right_table,
        "relationship_type": "Many-to-One",
        "join_condition": (
            f"{left_table}.{left_column} = {right_table}.{right_column}"
        ),
        "hybrid_score": 1.0,
    }


COMMON_RELATIONSHIPS = (
    _relationship(
        "fact_transaction_detail", "dateid", "dim_date", "dateid", layer="BOTH"
    ),
    _relationship(
        "fact_transaction_detail", "itemid", "dim_item", "skuid", layer="BOTH",
        note="Join to dim_item.skuid, never dim_item.itemid.",
    ),
    _relationship(
        "fact_transaction_detail",
        "transactionstatusid",
        "dim_transaction_status",
        "transactionstatusid",
        layer="BOTH",
    ),
    _relationship(
        "fact_transaction_detail",
        "transactiontypeid",
        "dim_transaction_type",
        "transactiontypeid",
        layer="BOTH",
    ),
)


OLTP_RELATIONSHIPS = (
    _relationship("fact_transaction_detail", "clientid", "dim_client", "clientid", layer="OLTP"),
    _relationship(
        "fact_transaction_detail",
        "clientcategoryid",
        "dim_client_category",
        "clientcategoryid",
        layer="OLTP",
    ),
    _relationship(
        "fact_transaction_detail",
        "dealeralignmentid",
        "dim_dealer_alignment",
        "dealeralignmentid",
        layer="OLTP",
    ),
    _relationship(
        "fact_transaction_detail", "designfirmid", "dim_design_firm", "designfirmid", layer="OLTP"
    ),
    _relationship(
        "fact_transaction_detail", "projectid", "dim_project", "projectid", layer="OLTP"
    ),
    _relationship(
        "fact_transaction_detail",
        "projectmanagerid",
        "dim_project_manager",
        "projectmanagerid",
        layer="OLTP",
    ),
    _relationship(
        "fact_transaction_detail", "projecttypeid", "dim_project_type", "projecttypeid", layer="OLTP"
    ),
    _relationship(
        "fact_transaction_detail", "salesrepid", "dim_sales_rep", "salesrepid", layer="OLTP"
    ),
    _relationship(
        "fact_transaction_detail", "specifier1id", "dim_specifier1", "partnerid", layer="OLTP",
        coverage="complete_nonunique",
        note=(
            "The fact value is a partner ID despite its name. dim_specifier1.partnerid "
            "is non-unique; add dim_specifier1.active_flag = 1, which makes the "
            "join complete and one-to-one for the loaded facts."
        ),
    ),
    _relationship(
        "fact_transaction_detail", "specifier2id", "dim_specifier2", "specifier2id", layer="OLTP"
    ),
    _relationship(
        "fact_transaction_detail", "enduserid", "dim_end_user", "partnerid", layer="OLTP",
        coverage="complete_nonunique",
        note=(
            "The fact value is a partner ID despite its name. dim_end_user.partnerid "
            "is non-unique; add dim_end_user.active_flag = 1, which makes the "
            "join complete and one-to-one for the loaded facts."
        ),
    ),
    _relationship(
        "fact_transaction_detail", "partnerid", "dim_partner", "partnerid", layer="OLTP"
    ),
    _relationship(
        "fact_transaction_detail", "specifier1id", "dim_partner", "partnerid", layer="OLTP",
        note=(
            "For partner-level analysis this unique join is safer than joining "
            "the non-unique dim_specifier1.partnerid."
        ),
    ),
    _relationship(
        "fact_transaction_detail", "enduserid", "dim_partner", "partnerid", layer="OLTP",
        note=(
            "For partner-level analysis this unique join is safer than joining "
            "the non-unique dim_end_user.partnerid."
        ),
    ),
    _relationship(
        "fact_transaction_detail",
        "specifiertypeid",
        "dim_specifier_type",
        "specifiertypeid",
        layer="OLTP",
    ),
    _relationship(
        "fact_transaction_detail",
        "specifiersubtypeid",
        "dim_specifier_sub_type",
        "specifiersubtypeid",
        layer="OLTP",
    ),
    _relationship(
        "fact_transaction_detail", "endusertypeid", "dim_end_user_type", "endusertypeid", layer="OLTP"
    ),
    _relationship(
        "fact_transaction_detail",
        "verticalmarketid",
        "dim_vertical_market",
        "verticalmarketid",
        layer="OLTP",
    ),
    _relationship("dim_item", "brandpartnerid", "dim_brand_partner_item", "brandpartnerid", layer="OLTP"),
    _relationship("dim_item", "subcategoryid", "dim_subcategory_item", "subcategoryid", layer="OLTP"),
    _relationship(
        "dim_subcategory_item", "categoryid", "dim_item_category", "categoryid", layer="OLTP"
    ),
    _relationship("dim_specifier1", "partnerid", "dim_partner", "partnerid", layer="OLTP"),
    _relationship(
        "dim_end_user", "partnerid", "dim_partner", "partnerid", layer="OLTP",
        coverage="partial",
        note="Four source partner IDs have no dimension row; use LEFT JOIN when retaining all end users.",
    ),
    _relationship(
        "dim_partner", "specifiertypeid", "dim_specifier_type", "specifiertypeid", layer="OLTP"
    ),
    _relationship(
        "dim_partner",
        "specifiersubtypeid",
        "dim_specifier_sub_type",
        "specifiersubtypeid",
        layer="OLTP",
    ),
    _relationship(
        "dim_partner", "endusertypeid", "dim_end_user_type", "endusertypeid", layer="OLTP"
    ),
)


RELATIONSHIPS_BY_LAYER = {
    "OLAP": COMMON_RELATIONSHIPS,
    "OLTP": COMMON_RELATIONSHIPS + OLTP_RELATIONSHIPS,
}


OLTP_INTENT_PATTERN = re.compile(
    r"\b(?:"
    r"client|customer|partner|dealer|design\s+firm|end\s*user|specifier|"
    r"sales\s*rep|project|vertical\s+market|category|subcategory|brand|"
    r"memo|note|reason|why|explain|cause|latest|recent|current|this\s+"
    r"(?:day|week|month|quarter|year)"
    r")\b",
    re.IGNORECASE,
)


def infer_layer_from_query(query: str) -> Optional[str]:
    """Return an intent-based layer override, or ``None`` for RAG scoring."""

    if query and OLTP_INTENT_PATTERN.search(query):
        return "OLTP"
    return None


def tables_for_query_intent(query: str, layer: str) -> List[str]:
    """Map explicit business concepts to the smallest useful table set."""

    text = str(query or "").lower()
    tables: Set[str] = set()

    client_category_intent = re.search(
        r"\b(?:client|customer)\s+(?:category|type|classification)\b", text
    )
    if client_category_intent:
        tables.add("dim_client_category")
    elif re.search(r"\b(?:client|customer|buyer|account)\b", text):
        tables.add("dim_client")

    if not client_category_intent and re.search(
        r"\b(?:product|item)\s+categor(?:y|ies)\b|\bcategory\b", text
    ):
        tables.add("dim_item_category")
    if re.search(r"\bsubcategor(?:y|ies)\b|\bbifma\b", text):
        tables.add("dim_subcategory_item")
    if re.search(r"\b(?:product|products|item|items|sku|skus|product\s+family)\b", text):
        tables.add("dim_item")
    if re.search(r"\b(?:brand|manufacturer)\b", text):
        tables.update({"dim_item", "dim_brand_partner_item"})

    explicit_patterns = (
        (r"\bsales\s*(?:rep|representative|person)|\bsalesperson\b", "dim_sales_rep"),
        (r"\bpartner\b", "dim_partner"),
        (r"\bdealer\b", "dim_dealer_alignment"),
        (r"\bdesign\s*firm\b|\barchitect\b", "dim_design_firm"),
        (r"\bproject\s*manager\b", "dim_project_manager"),
        (r"\bproject\s*type\b", "dim_project_type"),
        (r"\bproject\b(?!\s*(?:manager|type))", "dim_project"),
        (r"\bend\s*user\s*type\b", "dim_end_user_type"),
        (r"\bend\s*user\b(?!\s*type)", "dim_end_user"),
        (r"\bspecifier\s*sub\s*type\b", "dim_specifier_sub_type"),
        (r"\bspecifier\s*type\b", "dim_specifier_type"),
        (r"\bspecifier\s*2\b|\bsecondary\s+specifier\b", "dim_specifier2"),
        (r"\bspecifier\b(?!\s*(?:sub\s*type|type|2))", "dim_specifier1"),
        (r"\bvertical\s*market\b|\bindustry\b|\bsector\b", "dim_vertical_market"),
        (r"\btransaction\s*status\b|\bstatus\b", "dim_transaction_status"),
        (
            r"\btransaction\s*type\b|\binvoice|quotation|quote|sales\s*order|credit\s*memo\b",
            "dim_transaction_type",
        ),
        (r"\bdate|daily|weekly|monthly|quarterly|yearly|trend|period\b", "dim_date"),
    )
    for pattern, table in explicit_patterns:
        if re.search(pattern, text):
            tables.add(table)

    fact_intent = re.search(
        r"\b(?:sales|revenue|amount|quantity|rate|transaction|order|invoice|"
        r"quotation|quote|credit|shipment|shipped|delivered|memo|opportunity|"
        r"total|average|avg|sum|count|top|bottom|trend|increase|decrease|why)\b",
        text,
    )
    if fact_intent or tables:
        tables.add("fact_transaction_detail")

    available = TABLES_BY_LAYER.get(str(layer or "OLAP").upper(), frozenset())
    return sorted(table for table in tables if table in available)


def choose_query_layer(query: str, rag_recommendation: str = "OLAP") -> str:
    """Choose a complete layer without returning stale duplicated facts.

    The current OLAP extract is an exact subset of OLTP and ends earlier.  Use
    OLTP while it contains more fact rows; once a refresh brings the two layers
    back to parity, OLAP can again serve compact analytical questions.
    """

    intent_layer = infer_layer_from_query(query)
    if intent_layer:
        return intent_layer
    if FACT_ROW_COUNTS["OLTP"] > FACT_ROW_COUNTS["OLAP"]:
        return "OLTP"
    normalized = str(rag_recommendation or "OLAP").upper()
    return normalized if normalized in TABLES_BY_LAYER else "OLAP"


def choose_layer_for_counts(
    query: str,
    rag_recommendation: str,
    olap_fact_rows: int,
    oltp_fact_rows: int,
) -> str:
    """Runtime form of :func:`choose_query_layer` using live row counts."""

    intent_layer = infer_layer_from_query(query)
    if intent_layer:
        return intent_layer
    if int(oltp_fact_rows) > int(olap_fact_rows):
        return "OLTP"
    normalized = str(rag_recommendation or "OLAP").upper()
    return normalized if normalized in TABLES_BY_LAYER else "OLAP"


def canonical_relationships(layer: str) -> List[Dict[str, str]]:
    normalized = str(layer or "OLAP").upper()
    return [dict(item) for item in RELATIONSHIPS_BY_LAYER.get(normalized, ())]


def join_closure(
    layer: str,
    seed_tables: Iterable[str],
    root_table: str = "fact_transaction_detail",
) -> Dict[str, Sequence]:
    """Find the validated shortest join paths from seed tables to the fact.

    The returned tables and relationships are deterministic.  A standalone
    table is retained even if it has no path to the fact table.
    """

    relationships = canonical_relationships(layer)
    available = TABLES_BY_LAYER.get(str(layer).upper(), frozenset())
    seeds = {str(table).lower() for table in seed_tables if str(table).lower() in available}
    if not seeds:
        seeds = {root_table}

    graph: Dict[str, List[tuple[str, int]]] = {}
    for index, relationship in enumerate(relationships):
        left = relationship["left_table"]
        right = relationship["right_table"]
        graph.setdefault(left, []).append((right, index))
        graph.setdefault(right, []).append((left, index))

    selected_relationships: Set[int] = set()
    selected_tables = set(seeds)

    # Direct fact→dimension joins are authoritative when present. Without
    # this preference a breadth-first search could reach dim_partner through
    # the non-unique specifier/end-user bridge instead of the safe direct key.
    direct_by_seed: Dict[str, int] = {}
    for index, relationship in enumerate(relationships):
        if relationship["left_table"] != root_table:
            continue
        seed = relationship["right_table"]
        current_index = direct_by_seed.get(seed)
        if current_index is None:
            direct_by_seed[seed] = index
            continue
        current = relationships[current_index]
        # Prefer a same-concept key (partnerid→partnerid) when several fact
        # columns can reach the same dimension.
        current_exact = current["left_column"] == current["right_column"]
        candidate_exact = relationship["left_column"] == relationship["right_column"]
        if candidate_exact and not current_exact:
            direct_by_seed[seed] = index

    for seed in sorted(seeds):
        if seed == root_table or seed not in graph:
            continue
        if seed in direct_by_seed:
            relationship_index = direct_by_seed[seed]
            relationship = relationships[relationship_index]
            selected_relationships.add(relationship_index)
            selected_tables.add(root_table)
            selected_tables.add(relationship["right_table"])
            continue
        queue = deque([(seed, [])])
        visited = {seed}
        found_path: Optional[List[int]] = None
        while queue:
            table, path = queue.popleft()
            if table == root_table:
                found_path = path
                break
            for neighbor, relationship_index in graph.get(table, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [relationship_index]))
        if found_path is not None:
            selected_tables.add(root_table)
            for relationship_index in found_path:
                selected_relationships.add(relationship_index)
                relationship = relationships[relationship_index]
                selected_tables.add(relationship["left_table"])
                selected_tables.add(relationship["right_table"])

    ordered_relationships = [
        relationships[index] for index in sorted(selected_relationships)
    ]
    return {
        "tables": sorted(selected_tables),
        "relationships": ordered_relationships,
    }
