#!/usr/bin/env python3
"""Load the HighTower OLAP and OLTP CSV exports into PostgreSQL.

The import is repeatable and transactional per database. Only the managed
HighTower tables are replaced; the databases themselves are never dropped.

Usage:
    python scripts/ingest_dual_servers.py --dry-run
    python scripts/ingest_dual_servers.py --yes
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Mapping, Sequence, Tuple

import psycopg2
from psycopg2 import sql


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config.config import Config  # noqa: E402


logger = logging.getLogger("hightower_ingestion")


@dataclass(frozen=True)
class SourceTable:
    filename: str
    table_name: str


@dataclass(frozen=True)
class ColumnDefinition:
    name: str
    pg_type: str


@dataclass(frozen=True)
class PreparedTable:
    layer: str
    source: SourceTable
    csv_path: Path
    columns: Tuple[ColumnDefinition, ...]
    source_rows: int


@dataclass(frozen=True)
class RelationshipCheck:
    """A relationship that must remain safe for canonical analytics joins."""

    source_table: str
    source_column: str
    target_table: str
    target_column: str
    target_filter_column: str | None = None
    allowed_orphan_keys: Tuple[str, ...] = ()
    max_orphan_rows: int = 0


OLAP_SOURCES: Tuple[SourceTable, ...] = (
    SourceTable("Hightower OLAP Dim Date.csv", "dim_date"),
    SourceTable("Hightower OLAP Dim Item.csv", "dim_item"),
    SourceTable(
        "Hightower OLAP Dim Transaction Status.csv", "dim_transaction_status"
    ),
    SourceTable("Hightower OLAP Dim Transaction Type.csv", "dim_transaction_type"),
    SourceTable(
        "Hightower OLAP Fact Transaction Detail.csv", "fact_transaction_detail"
    ),
)


OLTP_SOURCES: Tuple[SourceTable, ...] = (
    SourceTable("Hightower OLTP Dim Date.csv", "dim_date"),
    SourceTable("Hightower OLTP Dim Specifier Type.csv", "dim_specifier_type"),
    SourceTable(
        "Hightower OLTP Dim Specifier Sub Type.csv", "dim_specifier_sub_type"
    ),
    SourceTable("Hightower OLTP End User Type.csv", "dim_end_user_type"),
    SourceTable(
        "Hightower OLTP AE Dim Brand Partner Item.csv", "dim_brand_partner_item"
    ),
    SourceTable("Hightower OLTP Dim Item Category.csv", "dim_item_category"),
    SourceTable(
        "Hightower OLTP Dim Transaction Status.csv", "dim_transaction_status"
    ),
    SourceTable("Hightower OLTP Dim Transaction Type.csv", "dim_transaction_type"),
    SourceTable("Hightower OLTP AE Vertical Market.csv", "dim_vertical_market"),
    SourceTable("Hightower OLTP Dim Client Category.csv", "dim_client_category"),
    SourceTable("Hightower_OLTP_AE(Dim_Client).csv", "dim_client"),
    SourceTable("Hightower OLTP Dim Dealer Alignment.csv", "dim_dealer_alignment"),
    SourceTable("Hightower OLTP AE Dim Design Firm.csv", "dim_design_firm"),
    SourceTable("Hightower OLTP Dim Project.csv", "dim_project"),
    SourceTable("Hightower OLTP Dim Project Type.csv", "dim_project_type"),
    SourceTable("Hightower OLTP Dim Project Manager.csv", "dim_project_manager"),
    SourceTable("Hightower OLTP Dim Sales Rep.csv", "dim_sales_rep"),
    SourceTable("Hightower OLTP Dim Specifier 2.csv", "dim_specifier2"),
    SourceTable("Hightower OLTP Dim SubCategory Item.csv", "dim_subcategory_item"),
    SourceTable("Hightower OLTP AE Dim Partner.csv", "dim_partner"),
    SourceTable("Hightower OLTP Dim Item.csv", "dim_item"),
    SourceTable("Hightower OLTP AE Dim End User.csv", "dim_end_user"),
    SourceTable("Hightower OLTP Dim Specifier 1.csv", "dim_specifier1"),
    SourceTable(
        "Hightower OLTP Fact Transaction Detail.csv", "fact_transaction_detail"
    ),
)


LAYER_SETTINGS = {
    "OLAP": {
        "sources": OLAP_SOURCES,
        "data_dir": next(
            (
                path
                for path in (
                    PROJECT_ROOT / "data" / "olap",
                    PROJECT_ROOT / "olap",
                )
                if path.is_dir()
            ),
            PROJECT_ROOT / "data" / "olap",
        ),
        "metadata": PROJECT_ROOT
        / "data"
        / "schemas"
        / "HighTowerDataModelSchemaOLAP.csv",
        "db_config": Config.OLAP_DB_CONFIG,
    },
    "OLTP": {
        "sources": OLTP_SOURCES,
        "data_dir": next(
            (
                path
                for path in (
                    PROJECT_ROOT / "data" / "oltp",
                    PROJECT_ROOT / "oltp",
                )
                if path.is_dir()
            ),
            PROJECT_ROOT / "data" / "oltp",
        ),
        "metadata": PROJECT_ROOT
        / "data"
        / "schemas"
        / "HighTower_DataModel_Schema(OLTP).csv",
        "db_config": Config.OLTP_DB_CONFIG,
    },
}


# The OLAP metadata file labels these columns incorrectly. These overrides are
# based on a complete value audit of the corresponding source CSV.
TYPE_OVERRIDES: Mapping[Tuple[str, str, str], str] = {
    ("OLAP", "fact_transaction_detail", "itemquantity"): "NUMERIC",
    ("OLAP", "fact_transaction_detail", "itemrate"): "NUMERIC",
    ("OLAP", "fact_transaction_detail", "oppclosedate"): "DATE",
    ("OLAP", "fact_transaction_detail", "opportunitynumber"): "TEXT",
    ("OLAP", "fact_transaction_detail", "customerkeyaccount"): "BOOLEAN",
    ("OLAP", "fact_transaction_detail", "insts"): (
        "TIMESTAMP WITHOUT TIME ZONE"
    ),
}


PRIMARY_KEYS: Mapping[Tuple[str, str], Tuple[str, ...]] = {
    ("OLAP", "dim_date"): ("dateid",),
    ("OLAP", "dim_transaction_status"): ("transactionstatusid",),
    ("OLAP", "dim_transaction_type"): ("transactiontypeid",),
    ("OLAP", "fact_transaction_detail"): (
        "transactionid",
        "transactiolineid",
    ),
    ("OLTP", "dim_date"): ("dateid",),
    ("OLTP", "dim_specifier_type"): ("specifiertypeid",),
    ("OLTP", "dim_specifier_sub_type"): ("specifiersubtypeid",),
    ("OLTP", "dim_end_user_type"): ("endusertypeid",),
    ("OLTP", "dim_brand_partner_item"): ("brandpartnerid",),
    ("OLTP", "dim_item_category"): ("categoryid",),
    ("OLTP", "dim_transaction_status"): ("transactionstatusid",),
    ("OLTP", "dim_transaction_type"): ("transactiontypeid",),
    ("OLTP", "dim_vertical_market"): ("verticalmarketid",),
    ("OLTP", "dim_client_category"): ("clientcategoryid",),
    ("OLTP", "dim_client"): ("clientid",),
    ("OLTP", "dim_dealer_alignment"): ("dealeralignmentid",),
    ("OLTP", "dim_design_firm"): ("designfirmid",),
    ("OLTP", "dim_project"): ("projectid",),
    ("OLTP", "dim_project_type"): ("projecttypeid",),
    ("OLTP", "dim_project_manager"): ("projectmanagerid",),
    ("OLTP", "dim_sales_rep"): ("salesrepid",),
    ("OLTP", "dim_specifier2"): ("specifier2id",),
    ("OLTP", "dim_subcategory_item"): ("subcategoryid",),
    ("OLTP", "dim_partner"): ("partnerid",),
    ("OLTP", "dim_end_user"): ("enduserid",),
    ("OLTP", "dim_specifier1"): ("specifier1id",),
    ("OLTP", "fact_transaction_detail"): (
        "transactionid",
        "transactiolineid",
    ),
}


# dim_item intentionally has non-unique indexes: the source contains two
# different records with SkuID='1', and all source records must be preserved.
INDEXES: Mapping[Tuple[str, str], Tuple[Tuple[str, ...], ...]] = {
    ("OLAP", "dim_item"): (("skuid",), ("itemid",)),
    ("OLAP", "fact_transaction_detail"): (
        ("dateid",),
        ("itemid",),
        ("transactionstatusid",),
        ("transactiontypeid",),
    ),
    ("OLTP", "dim_item"): (
        ("skuid",),
        ("itemid",),
        ("brandpartnerid",),
        ("subcategoryid",),
    ),
    ("OLTP", "fact_transaction_detail"): (
        ("dateid",),
        ("itemid",),
        ("clientid",),
        ("salesrepid",),
        ("transactionstatusid",),
        ("transactiontypeid",),
    ),
}


IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
SLASH_DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


BASE_RELATIONSHIP_CHECKS: Tuple[RelationshipCheck, ...] = (
    RelationshipCheck("fact_transaction_detail", "dateid", "dim_date", "dateid"),
    RelationshipCheck("fact_transaction_detail", "itemid", "dim_item", "skuid"),
    RelationshipCheck(
        "fact_transaction_detail",
        "transactiontypeid",
        "dim_transaction_type",
        "transactiontypeid",
    ),
    RelationshipCheck(
        "fact_transaction_detail",
        "transactionstatusid",
        "dim_transaction_status",
        "transactionstatusid",
    ),
)


OLTP_RELATIONSHIP_CHECKS: Tuple[RelationshipCheck, ...] = (
    RelationshipCheck("fact_transaction_detail", "clientid", "dim_client", "clientid"),
    RelationshipCheck(
        "fact_transaction_detail",
        "clientcategoryid",
        "dim_client_category",
        "clientcategoryid",
    ),
    RelationshipCheck(
        "fact_transaction_detail",
        "dealeralignmentid",
        "dim_dealer_alignment",
        "dealeralignmentid",
    ),
    RelationshipCheck(
        "fact_transaction_detail", "designfirmid", "dim_design_firm", "designfirmid"
    ),
    RelationshipCheck(
        "fact_transaction_detail",
        "enduserid",
        "dim_end_user",
        "partnerid",
        "active_flag",
    ),
    RelationshipCheck(
        "fact_transaction_detail",
        "endusertypeid",
        "dim_end_user_type",
        "endusertypeid",
    ),
    RelationshipCheck("fact_transaction_detail", "partnerid", "dim_partner", "partnerid"),
    RelationshipCheck("fact_transaction_detail", "projectid", "dim_project", "projectid"),
    RelationshipCheck(
        "fact_transaction_detail",
        "projectmanagerid",
        "dim_project_manager",
        "projectmanagerid",
    ),
    RelationshipCheck(
        "fact_transaction_detail",
        "projecttypeid",
        "dim_project_type",
        "projecttypeid",
    ),
    RelationshipCheck(
        "fact_transaction_detail", "salesrepid", "dim_sales_rep", "salesrepid"
    ),
    RelationshipCheck(
        "fact_transaction_detail",
        "specifier1id",
        "dim_specifier1",
        "partnerid",
        "active_flag",
    ),
    RelationshipCheck(
        "fact_transaction_detail", "specifier2id", "dim_specifier2", "specifier2id"
    ),
    RelationshipCheck(
        "fact_transaction_detail",
        "specifiersubtypeid",
        "dim_specifier_sub_type",
        "specifiersubtypeid",
    ),
    RelationshipCheck(
        "fact_transaction_detail",
        "specifiertypeid",
        "dim_specifier_type",
        "specifiertypeid",
    ),
    RelationshipCheck(
        "fact_transaction_detail",
        "verticalmarketid",
        "dim_vertical_market",
        "verticalmarketid",
    ),
    # Product hierarchy and brand joins used by category/product analyses.
    RelationshipCheck("dim_item", "subcategoryid", "dim_subcategory_item", "subcategoryid"),
    RelationshipCheck(
        "dim_subcategory_item", "categoryid", "dim_item_category", "categoryid"
    ),
    RelationshipCheck(
        "dim_item", "brandpartnerid", "dim_brand_partner_item", "brandpartnerid"
    ),
    # Partner hierarchy used to enrich specifier and end-user analyses.
    RelationshipCheck("dim_specifier1", "partnerid", "dim_partner", "partnerid"),
    RelationshipCheck(
        "dim_end_user",
        "partnerid",
        "dim_partner",
        "partnerid",
        allowed_orphan_keys=("2485", "2605", "2970", "3024"),
        max_orphan_rows=4,
    ),
    RelationshipCheck(
        "dim_partner", "specifiertypeid", "dim_specifier_type", "specifiertypeid"
    ),
    RelationshipCheck(
        "dim_partner",
        "specifiersubtypeid",
        "dim_specifier_sub_type",
        "specifiersubtypeid",
    ),
    RelationshipCheck(
        "dim_partner", "endusertypeid", "dim_end_user_type", "endusertypeid"
    ),
)


def normalized_identifier(value: str) -> str:
    identifier = value.strip().lower()
    if not IDENTIFIER_RE.fullmatch(identifier):
        raise ValueError(f"Unsafe or unsupported SQL identifier: {value!r}")
    return identifier


def metadata_type_to_postgres(data_type: str, char_max: str) -> str:
    normalized_type = data_type.strip().lower()
    if normalized_type == "int":
        return "INTEGER"
    if normalized_type == "tinyint":
        return "SMALLINT"
    if normalized_type == "float":
        return "NUMERIC"
    if normalized_type == "datetime":
        return "TIMESTAMP WITHOUT TIME ZONE"
    if normalized_type == "date":
        return "DATE"
    if normalized_type in {"varchar", "nvarchar"}:
        max_value = char_max.strip()
        if max_value and max_value.upper() != "NULL":
            return f"VARCHAR({int(max_value)})"
        return "TEXT"
    raise ValueError(f"Unsupported metadata type: {data_type!r}")


def read_metadata(layer: str, metadata_path: Path) -> Dict[str, List[ColumnDefinition]]:
    tables: Dict[str, List[ColumnDefinition]] = {}
    seen: set[Tuple[str, str]] = set()

    with metadata_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        required = {"TABLE_NAME", "COLUMN_NAME", "Data_Type", "Char_Max"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(
                f"Metadata file {metadata_path} is missing required columns"
            )

        for row in reader:
            table_name = normalized_identifier(row["TABLE_NAME"])
            column_name = normalized_identifier(row["COLUMN_NAME"])
            key = (table_name, column_name)
            if key in seen:
                raise ValueError(f"Duplicate metadata definition: {table_name}.{column_name}")
            seen.add(key)

            pg_type = TYPE_OVERRIDES.get(
                (layer, table_name, column_name),
                metadata_type_to_postgres(row["Data_Type"], row["Char_Max"]),
            )
            tables.setdefault(table_name, []).append(
                ColumnDefinition(column_name, pg_type)
            )

    return tables


def validate_date_literal(value: str) -> None:
    """Reject invalid supported date literals before PostgreSQL is changed."""

    if value in {"", "NULL"}:
        return

    slash_match = SLASH_DATE_RE.fullmatch(value)
    if slash_match:
        month, day, year = (int(part) for part in slash_match.groups())
        date(year, month, day)
        return

    if ISO_DATE_RE.fullmatch(value):
        date.fromisoformat(value)
        return

    raise ValueError(
        "unsupported date format; expected M/D/YYYY, MM/DD/YYYY, or YYYY-MM-DD"
    )


def validate_csv(csv_path: Path, columns: Sequence[ColumnDefinition]) -> int:
    expected_header = [column.name for column in columns]
    date_columns = [
        (index, column.name)
        for index, column in enumerate(columns)
        if column.pg_type == "DATE"
    ]
    row_count = 0

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, strict=True)
        try:
            raw_header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"CSV is empty: {csv_path}") from exc

        actual_header = [normalized_identifier(value) for value in raw_header]
        if actual_header != expected_header:
            raise ValueError(
                f"Header mismatch in {csv_path.name}:\n"
                f"  expected={expected_header}\n  actual={actual_header}"
            )

        expected_width = len(expected_header)
        for row in reader:
            row_count += 1
            if len(row) != expected_width:
                raise ValueError(
                    f"Malformed row in {csv_path.name} near CSV record "
                    f"{reader.line_num}: expected {expected_width} values, got {len(row)}"
                )

            for column_index, column_name in date_columns:
                try:
                    validate_date_literal(row[column_index])
                except ValueError as exc:
                    raise ValueError(
                        f"Invalid DATE value in {csv_path.name} near CSV record "
                        f"{reader.line_num}, column {column_name}: "
                        f"{row[column_index]!r}"
                    ) from exc

    return row_count


def prepare_layer(layer: str) -> List[PreparedTable]:
    settings = LAYER_SETTINGS[layer]
    sources: Sequence[SourceTable] = settings["sources"]  # type: ignore[assignment]
    data_dir: Path = settings["data_dir"]  # type: ignore[assignment]
    metadata_path: Path = settings["metadata"]  # type: ignore[assignment]
    metadata = read_metadata(layer, metadata_path)

    prepared: List[PreparedTable] = []
    mapped_tables = {source.table_name for source in sources}
    metadata_tables = set(metadata)
    if mapped_tables != metadata_tables:
        raise ValueError(
            f"{layer} file mapping does not match metadata. "
            f"Missing mappings={sorted(metadata_tables - mapped_tables)}, "
            f"unknown mappings={sorted(mapped_tables - metadata_tables)}"
        )

    for source in sources:
        csv_path = data_dir / source.filename
        if not csv_path.is_file():
            raise FileNotFoundError(f"Missing source CSV: {csv_path}")
        columns = tuple(metadata[source.table_name])
        row_count = validate_csv(csv_path, columns)
        prepared.append(
            PreparedTable(layer, source, csv_path, columns, row_count)
        )

    return prepared


def connect(db_config: Mapping[str, object]):
    return psycopg2.connect(
        host=db_config["host"],
        port=db_config["port"],
        database=db_config["database"],
        user=db_config["user"],
        password=db_config.get("password", ""),
        connect_timeout=10,
        application_name="hightower_csv_ingestion",
    )


def create_managed_tables(cursor, prepared: Sequence[PreparedTable]) -> None:
    table_names = [table.source.table_name for table in prepared]
    drop_query = sql.SQL("DROP TABLE IF EXISTS {} ").format(
        sql.SQL(", ").join(sql.Identifier(name) for name in table_names)
    )
    cursor.execute(drop_query)

    for table in prepared:
        column_definitions = sql.SQL(", ").join(
            sql.SQL("{} {}").format(
                sql.Identifier(column.name), sql.SQL(column.pg_type)
            )
            for column in table.columns
        )
        cursor.execute(
            sql.SQL("CREATE TABLE {} ({})").format(
                sql.Identifier(table.source.table_name), column_definitions
            )
        )


def normalized_text_expression(column_name: str) -> sql.Composed:
    identifier = sql.Identifier(column_name)
    return sql.SQL("NULLIF(NULLIF({}, ''), 'NULL')").format(identifier)


def cast_expression(column: ColumnDefinition) -> sql.Composed:
    normalized = normalized_text_expression(column.name)
    pg_type = column.pg_type

    if pg_type == "DATE":
        return sql.SQL(
            "CASE WHEN {value} IS NULL THEN NULL "
            "WHEN {value} ~ '^[0-9]{{1,2}}/[0-9]{{1,2}}/[0-9]{{4}}$' "
            "THEN make_date(" 
            "split_part({value}, '/', 3)::INTEGER, "
            "split_part({value}, '/', 1)::INTEGER, "
            "split_part({value}, '/', 2)::INTEGER) "
            "ELSE ({value})::DATE END"
        ).format(value=normalized)

    if pg_type in {
        "INTEGER",
        "SMALLINT",
        "NUMERIC",
        "BOOLEAN",
        "TIMESTAMP WITHOUT TIME ZONE",
    }:
        return sql.SQL("({})::{}").format(normalized, sql.SQL(pg_type))

    # TEXT and VARCHAR columns are coerced by INSERT while preserving their
    # source text (apart from the documented NULL/empty markers).
    return normalized


def load_table(cursor, connection, table: PreparedTable) -> None:
    table_name = table.source.table_name
    staging_name = f"_stage_{table_name}"
    column_names = [column.name for column in table.columns]

    staging_columns = sql.SQL(", ").join(
        sql.SQL("{} TEXT").format(sql.Identifier(name)) for name in column_names
    )
    cursor.execute(
        sql.SQL("CREATE TEMP TABLE {} ({}) ON COMMIT DROP").format(
            sql.Identifier(staging_name), staging_columns
        )
    )

    copy_query = sql.SQL(
        "COPY {} ({}) FROM STDIN WITH "
        "(FORMAT CSV, HEADER TRUE, DELIMITER ',', QUOTE '\"', ESCAPE '\"', "
        "NULL 'NULL')"
    ).format(
        sql.Identifier(staging_name),
        sql.SQL(", ").join(sql.Identifier(name) for name in column_names),
    )

    with table.csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        cursor.copy_expert(copy_query.as_string(connection), handle)

    select_values = sql.SQL(", ").join(
        cast_expression(column) for column in table.columns
    )
    insert_query = sql.SQL("INSERT INTO {} ({}) SELECT {} FROM {}").format(
        sql.Identifier(table_name),
        sql.SQL(", ").join(sql.Identifier(name) for name in column_names),
        select_values,
        sql.Identifier(staging_name),
    )
    cursor.execute(insert_query)
    inserted_rows = cursor.rowcount
    if inserted_rows != table.source_rows:
        raise RuntimeError(
            f"Row-count mismatch for {table_name}: "
            f"source={table.source_rows}, inserted={inserted_rows}"
        )

    cursor.execute(sql.SQL("DROP TABLE {}").format(sql.Identifier(staging_name)))
    logger.info("  %-30s %10s rows", table_name, f"{inserted_rows:,}")


def add_keys_and_indexes(cursor, layer: str, prepared: Sequence[PreparedTable]) -> None:
    available_columns = {
        table.source.table_name: {column.name for column in table.columns}
        for table in prepared
    }

    for table in prepared:
        table_name = table.source.table_name
        key_columns = PRIMARY_KEYS.get((layer, table_name))
        if key_columns:
            missing = set(key_columns) - available_columns[table_name]
            if missing:
                raise ValueError(f"Primary-key columns missing from {table_name}: {missing}")
            constraint_name = f"pk_{table_name}"
            cursor.execute(
                sql.SQL("ALTER TABLE {} ADD CONSTRAINT {} PRIMARY KEY ({})").format(
                    sql.Identifier(table_name),
                    sql.Identifier(constraint_name),
                    sql.SQL(", ").join(
                        sql.Identifier(column) for column in key_columns
                    ),
                )
            )

        for index_columns in INDEXES.get((layer, table_name), ()):
            missing = set(index_columns) - available_columns[table_name]
            if missing:
                raise ValueError(f"Index columns missing from {table_name}: {missing}")
            index_name = f"idx_{table_name}_{'_'.join(index_columns)}"
            cursor.execute(
                sql.SQL("CREATE INDEX {} ON {} ({})").format(
                    sql.Identifier(index_name),
                    sql.Identifier(table_name),
                    sql.SQL(", ").join(
                        sql.Identifier(column) for column in index_columns
                    ),
                )
            )


def verify_relationship(cursor, layer: str, check: RelationshipCheck) -> None:
    """Verify one canonical join, allowing only documented source exceptions."""

    extra_predicate = sql.SQL("")
    if check.target_filter_column:
        extra_predicate = sql.SQL(" AND target.{} = 1").format(
            sql.Identifier(check.target_filter_column)
        )

    cursor.execute(
        sql.SQL(
            "SELECT source.{source_column}, COUNT(*) "
            "FROM {source_table} source "
            "WHERE source.{source_column} IS NOT NULL AND NOT EXISTS ("
            "SELECT 1 FROM {target_table} target "
            "WHERE target.{target_column} = source.{source_column}{extra_predicate}) "
            "GROUP BY source.{source_column}"
        ).format(
            source_column=sql.Identifier(check.source_column),
            source_table=sql.Identifier(check.source_table),
            target_table=sql.Identifier(check.target_table),
            target_column=sql.Identifier(check.target_column),
            extra_predicate=extra_predicate,
        )
    )
    orphan_groups = cursor.fetchall()
    if not orphan_groups:
        return

    orphan_rows = sum(group[1] for group in orphan_groups)
    allowed_keys = set(check.allowed_orphan_keys)
    unexpected_keys = sorted(
        str(group[0]) for group in orphan_groups if str(group[0]) not in allowed_keys
    )
    if unexpected_keys or orphan_rows > check.max_orphan_rows:
        details = unexpected_keys[:10] or [str(group[0]) for group in orphan_groups[:10]]
        raise RuntimeError(
            f"{layer} relationship verification failed: "
            f"{check.source_table}.{check.source_column} has {orphan_rows:,} rows "
            f"unmatched by {check.target_table}.{check.target_column}; "
            f"orphan keys include {details}"
        )

    logger.warning(
        "%s known partial relationship: %s.%s has %s documented orphan rows",
        layer,
        check.source_table,
        check.source_column,
        f"{orphan_rows:,}",
    )


def verify_active_natural_keys(cursor, layer: str) -> None:
    """Ensure active partner-key joins cannot multiply fact rows."""

    for table_name in ("dim_specifier1", "dim_end_user"):
        cursor.execute(
            sql.SQL(
                "SELECT partnerid, COUNT(*) FROM {} "
                "WHERE active_flag = 1 AND partnerid IS NOT NULL "
                "GROUP BY partnerid HAVING COUNT(*) > 1"
            ).format(sql.Identifier(table_name))
        )
        duplicate_keys = cursor.fetchall()
        if duplicate_keys:
            duplicate_rows = sum(group[1] for group in duplicate_keys)
            raise RuntimeError(
                f"{layer} active natural-key verification failed: "
                f"{table_name}.partnerid has {len(duplicate_keys):,} duplicate keys "
                f"across {duplicate_rows:,} active rows; keys include "
                f"{[str(group[0]) for group in duplicate_keys[:10]]}"
            )


def verify_layer(cursor, layer: str, prepared: Sequence[PreparedTable]) -> None:
    for table in prepared:
        cursor.execute(
            sql.SQL("SELECT COUNT(*) FROM {}").format(
                sql.Identifier(table.source.table_name)
            )
        )
        database_rows = cursor.fetchone()[0]
        if database_rows != table.source_rows:
            raise RuntimeError(
                f"Verification failed for {table.source.table_name}: "
                f"source={table.source_rows}, database={database_rows}"
            )

    cursor.execute(
        """
        SELECT
            COUNT(*),
            COUNT(DISTINCT transactionid),
            MIN(dateid),
            MAX(dateid),
            COALESCE(SUM(amount), 0)
        FROM fact_transaction_detail
        """
    )
    fact_rows, transactions, min_dateid, max_dateid, total_amount = cursor.fetchone()
    logger.info(
        "%s fact checks: rows=%s, transactions=%s, dateid=%s..%s, amount=%s",
        layer,
        f"{fact_rows:,}",
        f"{transactions:,}",
        min_dateid,
        max_dateid,
        total_amount,
    )

    relationship_checks = list(BASE_RELATIONSHIP_CHECKS)
    if layer == "OLTP":
        relationship_checks.extend(OLTP_RELATIONSHIP_CHECKS)
        verify_active_natural_keys(cursor, layer)

    for relationship_check in relationship_checks:
        verify_relationship(cursor, layer, relationship_check)

    for table in prepared:
        cursor.execute(
            sql.SQL("ANALYZE {}").format(sql.Identifier(table.source.table_name))
        )


def ingest_layer(layer: str, prepared: Sequence[PreparedTable]) -> None:
    settings = LAYER_SETTINGS[layer]
    db_config: Mapping[str, object] = settings["db_config"]  # type: ignore[assignment]
    started = time.monotonic()
    logger.info(
        "%s: loading %d tables into %s:%s/%s",
        layer,
        len(prepared),
        db_config["host"],
        db_config["port"],
        db_config["database"],
    )

    connection = connect(db_config)
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL statement_timeout TO 0")
                cursor.execute("SET LOCAL lock_timeout TO '30s'")
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    (f"hightower_ingestion_{layer.lower()}",),
                )
                create_managed_tables(cursor, prepared)

                for table in prepared:
                    load_table(cursor, connection, table)

                logger.info("%s: creating keys and indexes", layer)
                add_keys_and_indexes(cursor, layer, prepared)
                verify_layer(cursor, layer, prepared)
    finally:
        connection.close()

    logger.info("%s committed in %.1f seconds", layer, time.monotonic() - started)


def selected_layers(layer_argument: str) -> Tuple[str, ...]:
    if layer_argument == "all":
        return ("OLAP", "OLTP")
    return (layer_argument.upper(),)


def print_preflight(prepared_by_layer: Mapping[str, Sequence[PreparedTable]]) -> None:
    total_rows = 0
    print("\nValidated HighTower source data:")
    for layer, tables in prepared_by_layer.items():
        layer_rows = sum(table.source_rows for table in tables)
        total_rows += layer_rows
        print(f"  {layer}: {len(tables)} tables, {layer_rows:,} rows")
    print(f"  Total: {total_rows:,} rows")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--layer",
        choices=("all", "olap", "oltp"),
        default="all",
        help="Load both databases or only one layer (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate every CSV and schema mapping without changing PostgreSQL",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip the confirmation prompt",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    layers = selected_layers(args.layer)
    prepared_by_layer = {layer: prepare_layer(layer) for layer in layers}
    print_preflight(prepared_by_layer)

    if args.dry_run:
        print("Dry run complete; PostgreSQL was not changed.")
        return 0

    if not args.yes:
        targets = ", ".join(
            str(LAYER_SETTINGS[layer]["db_config"]["database"]) for layer in layers
        )
        confirmation = input(
            f"\nReplace the managed HighTower tables in {targets}? [yes/no] "
        )
        if confirmation.strip().lower() != "yes":
            print("Cancelled; PostgreSQL was not changed.")
            return 1

    for layer in layers:
        ingest_layer(layer, prepared_by_layer[layer])

    print("\nHighTower ingestion completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
