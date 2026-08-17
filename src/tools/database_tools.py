import psycopg2
from psycopg2 import sql
import sqlparse
from sqlparse import tokens as sql_tokens
from typing import Dict, List, Any, Tuple
import pandas as pd
from src.config.config import Config
from src.domain.hightower import TABLES_BY_LAYER
import json
import re
from collections import deque
import logging

logger = logging.getLogger(__name__)


class SchemaContextManager:
    def __init__(self, db_tools):
        self.db_tools = db_tools
        self.loaded_schemas = {}
        self.table_stats = {}

    def get_relevant_tables(self, user_question: str) -> List[str]:
        question_lower = user_question.lower()
        all_tables_result = self.db_tools.sql_db_list_tables()

        if not all_tables_result["success"]:
            return ["fact_transaction_detail"]  # Default to fact table

        all_tables = all_tables_result["tables"]

        # Domain-specific keyword to table mapping
        keyword_map = {
            # Transaction & Financial
            "sales|revenue|amount|money|dollar|total|sum|value|price|cost|financial": [
                "fact_transaction_detail"
            ],
            
            "quantity|volume|units|count|items sold|number of": [
                "fact_transaction_detail"
            ],
            "rate|unit price|item price|price per": ["fact_transaction_detail"],
            # Product related
            "product|item|sku|inventory|goods|merchandise": [
                "dim_item",
                "dim_item_category",
                "dim_subcategory_item",
                "fact_transaction_detail",
            ],
            "category|product category|product line": [
                "dim_item_category",
                "dim_subcategory_item",
            ],
            "subcategory|product subcategory|subline": ["dim_subcategory_item"],
            "bifma": ["dim_subcategory_item"],
            "family|product family": ["dim_item"],
            "configuration|option|customization|variant": ["dim_item"],
            "brand|manufacturer|supplier|vendor": [
                "dim_item",
                "dim_brand_partner_item",
            ],
            # Customer & Client
            "client|customer|buyer|purchaser|account": [
                "dim_client",
                "fact_transaction_detail",
            ],
            "client category|customer type|account type|client classification": [
                "dim_client_category"
            ],
            "key account|major account|strategic account": [
                "dim_client",
                "dim_partner",
            ],
            # Date & Time - Use dateid and yearid columns only
            "date|time|month|year|quarter|week|when|period|fiscal|timeline|dateid|yearid": [
                "dim_date",
                "fact_transaction_detail",
            ],
            # Location
            "city|location|urban|metro|geography": [
                "fact_transaction_detail",
                "dim_partner",
                "dim_specifier1",
            ],
            "state|province|region": [
                "fact_transaction_detail",
                "dim_partner",
                "dim_specifier1",
            ],
            "country|nation|international": ["fact_transaction_detail", "dim_partner"],
            "zip|postal|zipcode|postal code": ["fact_transaction_detail"],
            "shipping|delivery|shipment|freight|delivered|shipped": [
                "fact_transaction_detail",
                "dim_transaction_type",
            ],
            "address|billing address|shipping address": ["dim_partner"],
            # Sales & Team
            "sales rep|representative|salesperson|sales team|seller": [
                "dim_sales_rep",
                "fact_transaction_detail",
            ],
            # Opportunity & Deal
            "opportunity|opp|deal|potential sale|pipeline": ["fact_transaction_detail"],
            "probability|likelihood|chance|win rate": ["fact_transaction_detail"],
            "projected|forecast|estimated|expected|projection": [
                "fact_transaction_detail"
            ],
            # Project
            "project|job|engagement|initiative": [
                "dim_project",
                "dim_project_type",
                "fact_transaction_detail",
            ],
            "project manager|pm|project lead": [
                "dim_project_manager",
                "fact_transaction_detail",
            ],
            "project type|project category|job type": ["dim_project_type"],
            # Partners & Relationships
            "partner|business partner|affiliate": [
                "dim_partner",
                "fact_transaction_detail",
            ],
            "dealer|distributor|reseller|channel": ["dim_dealer_alignment"],
            "design firm|architect|designer|design company": ["dim_design_firm"],
            # Specifiers
            "specifier|specification|spec": [
                "dim_specifier1",
                "dim_specifier2",
                "dim_specifier_type",
                "dim_specifier_sub_type",
            ],
            "specifier type|spec type": ["dim_specifier_type"],
            "specifier subtype|spec subtype": ["dim_specifier_sub_type"],
            # Market & Industry
            "market|vertical|industry|sector|segment": ["dim_vertical_market"],
            "vertical market|industry vertical": ["dim_vertical_market"],
            # Transaction Type & Status
            "transaction type|order type|doc type|document type": [
                "dim_transaction_type",
                "fact_transaction_detail",
            ],
            "quote|quotation|estimate|proposal": [
                "dim_transaction_type",
                "fact_transaction_detail",
            ],
            "order|sales order|purchase order": [
                "dim_transaction_type",
                "fact_transaction_detail",
            ],
            "invoice|bill|billing": ["dim_transaction_type", "fact_transaction_detail"],
            "credit memo|credit note|return": [
                "dim_transaction_type",
                "fact_transaction_detail",
            ],
            "status|state|condition|transaction status": [
                "dim_transaction_status",
                "fact_transaction_detail",
            ],
            # End User
            "end user|final user|consumer|ultimate customer": [
                "dim_end_user",
                "_type",
                "fact_transaction_detail",
            ],
            "end user type|consumer type|user category": ["dim_end_user_type"],
            # Other attributes
            "memo|note|comment|remark|description": ["fact_transaction_detail"],
            "title|name": ["fact_transaction_detail"],
            "active|inactive|enabled|disabled": ["fact_transaction_detail"],
        }

        relevant_tables = set()

        for pattern, tables in keyword_map.items():
            if re.search(pattern, question_lower):
                for table in tables:
                    if table in all_tables:
                        relevant_tables.add(table)

        # Always include the main fact table if no matches
        if not relevant_tables and "fact_transaction_detail" in all_tables:
            relevant_tables.add("fact_transaction_detail")

        # Include commonly joined dimension tables if fact table is included
        if "fact_transaction_detail" in relevant_tables:
            common_dims = ["dim_client", "dim_item", "dim_date", "dim_sales_rep"]
            for dim in common_dims:
                if dim in all_tables:
                    relevant_tables.add(dim)

        return list(relevant_tables)[:10]  # Limit to 10 tables

    def get_progressive_context(self, user_question: str) -> str:
        relevant_tables = self.get_relevant_tables(user_question)

        if not relevant_tables:
            return "No relevant tables found for your query."

        # Get detailed schema for relevant tables
        result = self.db_tools.sql_db_schema(relevant_tables)

        if not result["success"]:
            return f"Failed to get schema: {result.get('error')}"

        schemas = result["schemas"]

        context = "## DATABASE SCHEMA FOR YOUR QUERY ##\n\n"
        context += f"Based on your question, here are the relevant tables with sample data:\n\n"

        for table_name, schema in schemas.items():
            context += f"### Table: `{table_name}`\n"
            context += f"**Row Count:** {schema['row_count']:,}\n\n"

            # Column information
            context += "**Columns:**\n"
            for col in schema["columns"]:
                context += f"- `{col['name']}` ({col['type']})\n"

            # Primary keys
            if schema.get("primary_keys"):
                context += f"\n**Primary Key:** {', '.join(schema['primary_keys'])}\n"

            # Foreign key relationships
            if schema.get("foreign_keys"):
                context += "\n**Relationships (Foreign Keys):**\n"
                for fk in schema["foreign_keys"]:
                    context += f"- `{fk['column']}` → `{fk['references_table']}.{fk['references_column']}`\n"

            # Sample data
            if schema.get("sample_rows"):
                context += "\n**Sample Data (helps understand actual values):**\n"
                context += "```\n"
                for i, row in enumerate(schema["sample_rows"][:2], 1):
                    context += f"Row {i}:\n"
                    for key, value in list(row.items())[:5]:
                        context += f"  {key}: {value}\n"
                context += "```\n"

            # Statistical context for numeric columns
            if schema.get("numeric_stats"):
                context += "\n**Numeric Column Statistics:**\n"
                for col_name, stats in schema["numeric_stats"].items():
                    if stats["min"] is not None:
                        avg_formatted = (
                            f"{stats['avg']:.2f}" if stats["avg"] is not None else "N/A"
                        )
                        context += f"- `{col_name}`: min={stats['min']}, max={stats['max']}, avg={avg_formatted}\n"

            context += "\n" + "─" * 60 + "\n\n"

        return context


class DatabaseTools:
    # PostgreSQL permits function calls from a SELECT, and several built-ins
    # can read server files, change session state, signal other sessions, or
    # otherwise cause side effects.  The database connection is also forced
    # read-only, but that setting alone does not make every SELECT function
    # harmless (for example, pg_read_file and pg_notify).
    _UNSAFE_SELECT_FUNCTIONS = frozenset(
        {
            # Server filesystem access.
            "pg_read_file",
            "pg_read_binary_file",
            "pg_stat_file",
            "pg_logdir_ls",
            "pg_file_write",
            "pg_file_rename",
            "pg_file_unlink",
            # Session and process control.
            "set_config",
            "setseed",
            "pg_notify",
            "pg_cancel_backend",
            "pg_terminate_backend",
            "pg_reload_conf",
            "pg_rotate_logfile",
            "pg_log_backend_memory_contexts",
            "pg_sleep",
            "pg_sleep_for",
            "pg_sleep_until",
            # WAL, backup, and replication control.
            "pg_promote",
            "pg_switch_wal",
            "pg_create_restore_point",
            "pg_wal_replay_pause",
            "pg_wal_replay_resume",
            "pg_backup_start",
            "pg_backup_stop",
            "pg_start_backup",
            "pg_stop_backup",
            "pg_create_physical_replication_slot",
            "pg_create_logical_replication_slot",
            "pg_drop_replication_slot",
            "pg_replication_slot_advance",
            "pg_import_system_collations",
            # Sequence and large-object writes can be invoked by SELECT.
            "nextval",
            "setval",
            "lo_import",
            "lo_export",
            "lo_create",
            "lo_creat",
            "lo_from_bytea",
            "lo_unlink",
            "lo_put",
            "lowrite",
            # These accept SQL text or connect outside the selected database,
            # which would otherwise permit a dangerous call to be hidden in a
            # string literal.
            "query_to_xml",
            "query_to_xmlschema",
        }
    )
    _UNSAFE_SELECT_FUNCTION_PATTERNS = (
        re.compile(r"^pg_(?:try_)?advisory_"),
        re.compile(r"^pg_ls_"),
        re.compile(r"^pg_file_"),
        re.compile(r"^pg_replication_origin_"),
        re.compile(r"^dblink(?:_|$)"),
        # Common PostgreSQL HTTP extensions expose outbound network access.
        re.compile(r"^http(?:_|$)"),
    )

    def __init__(self, olap_config: Dict = None, oltp_config: Dict = None):
        # Support both old single-DB and new dual-DB initialization
        if olap_config is None and oltp_config is None:
            # Legacy mode: single DB (backward compatibility)
            self.olap_config = Config.DB_CONFIG
            self.oltp_config = None
            self.dual_mode = False
        else:
            # Dual DB mode
            self.olap_config = olap_config or Config.OLAP_DB_CONFIG
            self.oltp_config = oltp_config or Config.OLTP_DB_CONFIG
            self.dual_mode = True

        self.conn = None  # Primary connection (OLAP in dual mode, single DB in legacy mode)
        self.oltp_conn = None  # OLTP connection (only in dual mode)
        self.query_history = []
        self.metadata_cache = {}
        self.transaction_in_error = False

    @staticmethod
    def _normalize_target_db(target_db: str = None) -> str:
        if target_db is None:
            return ""
        normalized = str(target_db).strip().upper()
        if normalized not in {"OLAP", "OLTP"}:
            raise ValueError("target_db must be 'OLAP', 'OLTP', or None")
        return normalized

    def _connection_for_target(self, target_db: str):
        target = self._normalize_target_db(target_db)
        if target == "OLTP":
            if (
                not self.dual_mode
                or self.oltp_conn is None
                or getattr(self.oltp_conn, "closed", 0)
            ):
                raise RuntimeError("OLTP database is not connected")
            return self.oltp_conn, "OLTP"
        if self.conn is None or getattr(self.conn, "closed", 0):
            raise RuntimeError("OLAP database is not connected")
        return self.conn, "OLAP"

    @staticmethod
    def _configure_connection(connection) -> None:
        """Apply the same safety and timeout settings to every DB session."""

        connection.autocommit = False
        timeout = Config.DB_QUERY_TIMEOUT
        with connection.cursor() as cur:
            cur.execute(f"SET statement_timeout = {timeout * 1000};")
            cur.execute("SET default_transaction_read_only = on;")
            cur.execute("SET search_path = public, pg_temp;")
        connection.commit()

    @staticmethod
    def _plan_relations(plan: Any) -> set:
        """Return every schema/relation pair referenced by a JSON EXPLAIN plan."""

        relations = set()
        if isinstance(plan, dict):
            relation = plan.get("Relation Name")
            if relation:
                relations.add((str(plan.get("Schema", "public")), str(relation)))
            for value in plan.values():
                relations.update(DatabaseTools._plan_relations(value))
        elif isinstance(plan, (list, tuple)):
            for value in plan:
                relations.update(DatabaseTools._plan_relations(value))
        return relations

    @classmethod
    def _validate_explain_plan_relations(
        cls, plan: Any, db_label: str
    ) -> Dict[str, Any]:
        """Restrict generated SQL to the managed HighTower public tables."""

        layer = str(db_label or "").upper()
        allowed_tables = TABLES_BY_LAYER.get(layer)
        if not allowed_tables:
            return {
                "success": False,
                "error": f"Unknown database layer for relation validation: {db_label}",
            }

        relations = cls._plan_relations(plan)
        disallowed = sorted(
            (schema, relation)
            for schema, relation in relations
            if schema != "public" or relation not in allowed_tables
        )
        if disallowed:
            rendered = ", ".join(
                f"{schema}.{relation}" for schema, relation in disallowed
            )
            return {
                "success": False,
                "error": (
                    "Query may only read the managed HighTower "
                    f"{layer} tables; disallowed relation(s): {rendered}."
                ),
            }
        return {"success": True, "relations": sorted(relations)}

    @classmethod
    def _explain_and_validate_relations(
        cls, cursor, query: str, db_label: str
    ) -> Dict[str, Any]:
        cursor.execute("EXPLAIN (FORMAT JSON) " + query)
        row = cursor.fetchone()
        plan = row[0] if row else []
        return cls._validate_explain_plan_relations(plan, db_label)

    def _connect_oltp(self):
        """Open only the OLTP connection, leaving a healthy OLAP session alone."""

        if not self.dual_mode or not self.oltp_config:
            raise RuntimeError("OLTP database is not configured")

        new_connection = None
        try:
            new_connection = psycopg2.connect(**self.oltp_config)
            self._configure_connection(new_connection)
        except Exception:
            if new_connection is not None:
                try:
                    new_connection.close()
                except Exception:
                    pass
            self.oltp_conn = None
            raise

        old_connection = self.oltp_conn
        self.oltp_conn = new_connection
        if old_connection is not None and old_connection is not new_connection:
            try:
                old_connection.close()
            except Exception:
                pass
        logger.info("Connected to OLTP database")
        return new_connection

    @staticmethod
    def _validate_read_only_query(query: str) -> Dict[str, Any]:
        """Accept one analytics SELECT and reject mutations or unsafe calls."""

        if not query or not query.strip():
            return {"success": False, "error": "Empty query provided."}

        statements = [
            statement
            for statement in sqlparse.parse(query)
            if str(statement).strip().strip(";")
        ]
        if len(statements) != 1:
            return {
                "success": False,
                "error": "Exactly one SQL statement is allowed.",
            }

        statement = statements[0]
        if statement.get_type() != "SELECT":
            return {
                "success": False,
                "error": "Only SELECT and WITH ... SELECT queries are allowed.",
            }

        forbidden_keywords = {
            "INSERT",
            "UPDATE",
            "DELETE",
            "MERGE",
            "DROP",
            "TRUNCATE",
            "ALTER",
            "CREATE",
            "GRANT",
            "REVOKE",
            "COPY",
            "CALL",
            "DO",
            "VACUUM",
            "ANALYZE",
            "REFRESH",
            "REINDEX",
            "CLUSTER",
            "LOCK",
            "SET",
            "RESET",
            "EXECUTE",
            "PREPARE",
            "DEALLOCATE",
            "INTO",
        }
        for token in statement.flatten():
            if token.ttype in sql_tokens.Comment or token.ttype in sql_tokens.Literal.String:
                continue
            normalized = token.normalized.upper()
            normalized_parts = normalized.split()
            first_keyword = normalized_parts[0] if normalized_parts else ""
            if normalized in forbidden_keywords or first_keyword in forbidden_keywords:
                return {
                    "success": False,
                    "error": (
                        f"Read-only query required; {first_keyword or normalized} "
                        "is not allowed."
                    ),
                }

        # Build security-sensitive text without comments or string/identifier
        # literals.  This prevents harmless text such as 'FOR UPDATE' from
        # triggering the row-lock check while still closing comment-based
        # spacing tricks such as FOR/**/UPDATE.
        normalized_sql = " ".join(
            token.normalized.upper()
            for token in statement.flatten()
            if token.ttype not in sql_tokens.Comment
            and token.ttype not in sql_tokens.Literal.String
            and not token.is_whitespace
        )
        if re.search(
            r"\bFOR\s+(?:NO\s+KEY\s+UPDATE|UPDATE|KEY\s+SHARE|SHARE)\b",
            normalized_sql,
        ):
            return {
                "success": False,
                "error": "Row-locking SELECT statements are not allowed.",
            }

        # sqlparse represents a called function's final identifier immediately
        # before its opening parenthesis.  Inspecting flattened tokens catches
        # nested CTE calls, schema qualification, quoted identifiers, and
        # comments between the function name and "(" without inspecting string
        # contents (where words such as pg_read_file are harmless data).
        significant_tokens = []
        called_functions = set()
        for token in statement.flatten():
            if token.ttype in sql_tokens.Comment or token.is_whitespace:
                continue
            if token.value == "(" and significant_tokens:
                candidate = significant_tokens[-1]
                value = candidate.value.strip()
                if (
                    candidate.ttype in sql_tokens.Literal.String.Symbol
                    and len(value) >= 2
                    and value.startswith('"')
                    and value.endswith('"')
                ):
                    value = value[1:-1].replace('""', '"')
                called_functions.add(value.casefold())
            significant_tokens.append(token)

        for function_name in sorted(called_functions):
            if function_name in DatabaseTools._UNSAFE_SELECT_FUNCTIONS or any(
                pattern.match(function_name)
                for pattern in DatabaseTools._UNSAFE_SELECT_FUNCTION_PATTERNS
            ):
                return {
                    "success": False,
                    "error": (
                        "Read-only analytics query required; function "
                        f"{function_name} is not allowed."
                    ),
                }

        return {"success": True, "statement": statement}

    def connect(self) -> bool:
        try:
            # Connect to OLAP (or single DB in legacy mode)
            self.conn = psycopg2.connect(**self.olap_config)
            self._configure_connection(self.conn)
            self.transaction_in_error = False

            # Connect to OLTP if in dual mode
            if self.dual_mode and self.oltp_config:
                try:
                    self._connect_oltp()
                    logger.info("Connected to both OLAP and OLTP databases")
                except Exception as oltp_error:
                    logger.warning(f"OLTP connection failed: {oltp_error}. Operating in OLAP-only mode.")
                    self.oltp_conn = None

            return True
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return False

    def ensure_clean_transaction(self):
        try:
            if self.transaction_in_error:
                logger.info("Rolling back failed transaction...")
                self.conn.rollback()
                self.transaction_in_error = False

            # Test the connection
            with self.conn.cursor() as cur:
                cur.execute("SELECT 1")
                self.conn.commit()

        except psycopg2.OperationalError:
            # Connection lost, try to reconnect
            logger.warning("Database connection lost. Attempting to reconnect...")
            self.connect()
        except Exception as e:
            logger.error(f"Error ensuring clean transaction: {e}")
            try:
                if self.conn:
                    self.conn.rollback()
                    self.transaction_in_error = False
            except:
                # If rollback fails, try to reconnect
                self.connect()

    @staticmethod
    def _list_tables_on_connection(connection) -> List[str]:
        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
                ORDER BY tablename;
                """
            )
            return [row[0] for row in cur.fetchall()]

    def _ensure_connection_ready(self, target_db: str):
        """Validate the selected connection and lazily reconnect it once."""

        target = self._normalize_target_db(target_db)
        if not target:
            target = "OLAP"

        try:
            conn, label = self._connection_for_target(target)
        except RuntimeError:
            logger.info("%s connection is unavailable; attempting to connect", target)
            try:
                if target == "OLTP":
                    self._connect_oltp()
                elif not self.connect():
                    raise RuntimeError("OLAP connection attempt failed")
                return self._connection_for_target(target)
            except Exception as error:
                raise RuntimeError(
                    f"Could not connect to {target} database: {error}"
                ) from error

        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            conn.commit()
            return conn, label
        except (psycopg2.InterfaceError, psycopg2.OperationalError):
            logger.warning("%s connection lost; reconnecting", label)
            try:
                if target == "OLTP":
                    self._connect_oltp()
                elif not self.connect():
                    raise RuntimeError("OLAP reconnection attempt failed")
                return self._connection_for_target(target)
            except Exception as error:
                raise RuntimeError(
                    f"Could not reconnect to {label} database: {error}"
                ) from error

    def sql_db_list_tables(self, target_db: str = None) -> Dict[str, Any]:
        try:
            self.ensure_clean_transaction()
            target = self._normalize_target_db(target_db)
            if target:
                self._ensure_connection_ready(target)

            olap_tables = []
            if target != "OLTP":
                olap_tables = self._list_tables_on_connection(self.conn)
                self.conn.commit()

            oltp_tables = []
            if target != "OLAP" and self.dual_mode and self.oltp_conn:
                try:
                    oltp_tables = self._list_tables_on_connection(self.oltp_conn)
                    self.oltp_conn.commit()
                except Exception as oltp_error:
                    self.oltp_conn.rollback()
                    logger.warning(f"Could not list OLTP tables: {oltp_error}")

            if target == "OLAP":
                tables = olap_tables
            elif target == "OLTP":
                tables = oltp_tables
            else:
                tables = sorted(set(olap_tables) | set(oltp_tables))
            return {
                "success": True,
                "tables": tables,
                "count": len(tables),
                "olap_tables": olap_tables,
                "oltp_tables": oltp_tables,
                "target_db": target or "ALL",
                "message": (
                    f"Found {len(tables)} table(s) for {target or 'all configured layers'}."
                ),
            }
        except Exception as e:
            self.transaction_in_error = True
            self.conn.rollback()
            if self.oltp_conn:
                try:
                    self.oltp_conn.rollback()
                except Exception:
                    pass
            return {"success": False, "error": str(e), "tables": []}

    def sql_db_fact_coverage(self, target_db: str) -> Dict[str, Any]:
        """Return the live fact row count and transaction-date coverage."""

        try:
            target = self._normalize_target_db(target_db)
            if not target:
                raise ValueError("target_db is required for fact coverage")
            conn, db_label = self._ensure_connection_ready(target)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*), MIN(dateid), MAX(dateid)
                    FROM fact_transaction_detail
                    """
                )
                row_count, min_dateid, max_dateid = cur.fetchone()
            conn.commit()
            return {
                "success": True,
                "db_source": db_label,
                "row_count": int(row_count),
                "min_dateid": min_dateid,
                "max_dateid": max_dateid,
            }
        except Exception as error:
            try:
                conn.rollback()
            except Exception:
                pass
            return {
                "success": False,
                "db_source": str(target_db or "").upper(),
                "error": str(error),
            }

    def sql_db_schema(
        self, tables: List[str], target_db: str = None
    ) -> Dict[str, Any]:
        try:
            self.ensure_clean_transaction()
            target = self._normalize_target_db(target_db)
            if target:
                preferred_conn, preferred_label = self._ensure_connection_ready(target)
            else:
                preferred_conn, preferred_label = self.conn, "OLAP"

            schemas = {}
            for table in tables:
                table = str(table).strip().lower()
                if not re.fullmatch(r"[a-z_][a-z0-9_]*", table):
                    logger.warning("Ignoring invalid table identifier: %r", table)
                    continue

                # Duplicate table names have different columns in OLAP and
                # OLTP, so the selected layer is part of the cache identity.
                cache_key = f"schema_{target or 'AUTO'}_public_{table}"
                if cache_key in self.metadata_cache:
                    schemas[table] = self.metadata_cache[cache_key]
                    continue

                source_conn = preferred_conn
                source_label = preferred_label
                try:
                    def get_columns(connection):
                        with connection.cursor() as column_cur:
                            column_cur.execute(
                                """
                                SELECT column_name, data_type, is_nullable
                                FROM information_schema.columns
                                WHERE table_schema = 'public' AND table_name = %s
                                ORDER BY ordinal_position;
                                """,
                                (table,),
                            )
                            return [
                                {
                                    "name": row[0],
                                    "type": row[1],
                                    "nullable": row[2] == "YES",
                                }
                                for row in column_cur.fetchall()
                            ]

                    columns = get_columns(source_conn)
                    if not columns and not target:
                        if self.dual_mode and self.oltp_conn:
                            columns = get_columns(self.oltp_conn)
                            if columns:
                                source_conn = self.oltp_conn
                                source_label = "OLTP"
                                logger.info(f"Table {table} found in OLTP (not in OLAP)")

                    if not columns:
                        logger.warning(f"Table {table} not found or has no columns")
                        continue

                    with source_conn.cursor() as cur:
                        # Every query below must use the connection on which the
                        # table was discovered. Previously OLTP-only tables were
                        # introspected with the OLAP cursor after fallback.
                        cur.execute(
                            """
                            SELECT kcu.column_name
                            FROM information_schema.table_constraints AS tc
                            JOIN information_schema.key_column_usage AS kcu
                              ON tc.constraint_name = kcu.constraint_name
                             AND tc.table_schema = kcu.table_schema
                            WHERE tc.table_schema = 'public'
                              AND tc.table_name = %s
                              AND tc.constraint_type = 'PRIMARY KEY'
                            ORDER BY kcu.ordinal_position;
                            """,
                            (table,),
                        )
                        primary_keys = [row[0] for row in cur.fetchall()]

                        cur.execute(
                            """
                            SELECT
                                kcu.column_name,
                                ccu.table_name AS foreign_table_name,
                                ccu.column_name AS foreign_column_name
                            FROM information_schema.table_constraints AS tc
                            JOIN information_schema.key_column_usage AS kcu
                              ON tc.constraint_name = kcu.constraint_name
                              AND tc.table_schema = kcu.table_schema
                            JOIN information_schema.constraint_column_usage AS ccu
                              ON ccu.constraint_name = tc.constraint_name
                              AND ccu.table_schema = tc.table_schema
                            WHERE tc.constraint_type = 'FOREIGN KEY'
                              AND tc.table_schema = 'public'
                              AND tc.table_name = %s;
                            """,
                            (table,),
                        )
                        foreign_keys = [
                            {
                                "column": row[0],
                                "references_table": row[1],
                                "references_column": row[2],
                            }
                            for row in cur.fetchall()
                        ]

                        cur.execute(
                            sql.SQL("SELECT COUNT(*) FROM {}").format(
                                sql.Identifier(table)
                            )
                        )
                        row_count = cur.fetchone()[0]

                        cur.execute(
                            sql.SQL("SELECT * FROM {} LIMIT 3").format(
                                sql.Identifier(table)
                            )
                        )
                        columns_names = [desc[0] for desc in cur.description]
                        sample_rows = [
                            dict(zip(columns_names, row)) for row in cur.fetchall()
                        ]

                        numeric_stats = {}
                        for col in columns:
                            if col["type"].lower() in [
                                "integer",
                                "bigint",
                                "numeric",
                                "decimal",
                                "real",
                                "double precision",
                            ]:
                                try:
                                    cur.execute(
                                        sql.SQL(
                                            "SELECT MIN({column}), MAX({column}), AVG({column}) "
                                            "FROM {table} WHERE {column} IS NOT NULL"
                                        ).format(
                                            column=sql.Identifier(col["name"]),
                                            table=sql.Identifier(table),
                                        )
                                    )
                                    result = cur.fetchone()
                                    if result and result[0] is not None:
                                        min_val, max_val, avg_val = result
                                        numeric_stats[col["name"]] = {
                                            "min": (
                                                float(min_val)
                                                if min_val is not None
                                                else None
                                            ),
                                            "max": (
                                                float(max_val)
                                                if max_val is not None
                                                else None
                                            ),
                                            "avg": (
                                                float(avg_val)
                                                if avg_val is not None
                                                else None
                                            ),
                                        }
                                except Exception as stat_error:
                                    logger.debug(
                                        f"Could not get stats for {table}.{col['name']}: {stat_error}"
                                    )

                        schema_info = {
                            "columns": columns,
                            "primary_keys": primary_keys,
                            "foreign_keys": foreign_keys,
                            "row_count": row_count,
                            "sample_rows": sample_rows,
                            "numeric_stats": numeric_stats,
                            "db_source": source_label,
                        }

                        self.metadata_cache[cache_key] = schema_info
                        schemas[table] = schema_info

                    source_conn.commit()

                except Exception as table_error:
                    logger.error(
                        f"Error getting schema for table {table}: {table_error}"
                    )
                    try:
                        source_conn.rollback()
                    except Exception:
                        pass
                    self.ensure_clean_transaction()
                    continue

            self.conn.commit()
            if self.oltp_conn:
                self.oltp_conn.commit()

            return {
                "success": True,
                "schemas": schemas,
                "target_db": target or "AUTO",
                "message": f"Retrieved schema for {len(schemas)} table(s).",
            }

        except Exception as e:
            self.transaction_in_error = True
            self.conn.rollback()
            if self.oltp_conn:
                try:
                    self.oltp_conn.rollback()
                except Exception:
                    pass
            logger.error(f"Error in sql_db_schema: {e}")
            return {"success": False, "error": str(e), "schemas": {}}

    def sql_db_query_checker(
        self, query: str, target_db: str = None
    ) -> Dict[str, Any]:
        try:
            self.ensure_clean_transaction()
            validation = self._validate_read_only_query(query)
            if not validation["success"]:
                return {
                    "success": False,
                    "error": validation["error"],
                    "suggestion": "Provide one read-only SELECT query.",
                }

            conn, db_label = self._ensure_connection_ready(target_db or "OLAP")
            try:
                with conn.cursor() as cur:
                    relation_validation = self._explain_and_validate_relations(
                        cur, query, db_label
                    )
                    if not relation_validation["success"]:
                        conn.rollback()
                        return {
                            "success": False,
                            "error": relation_validation["error"],
                            "db_source": db_label,
                            "suggestion": (
                                "Use only the managed HighTower tables in the "
                                "selected database layer."
                            ),
                        }
                conn.commit()
                return {
                    "success": True,
                    "message": f"Query syntax is valid on {db_label}.",
                    "db_source": db_label,
                    "suggestion": (
                        "The query passed validation and can be executed with "
                        "sql_db_query[]."
                    ),
                }
            except psycopg2.Error as error:
                conn.rollback()
                if conn is self.conn:
                    self.transaction_in_error = False
                return {
                    "success": False,
                    "error": str(error),
                    "db_source": db_label,
                    "suggestion": (
                        "Check names and joins against the selected database schema."
                    ),
                }

        except Exception as e:
            self.transaction_in_error = True
            if self.conn:
                self.conn.rollback()
            return {"success": False, "error": str(e)}

    def _is_result_sufficient(self, result: Dict[str, Any]) -> bool:
        """Check if query result is sufficient (has data)"""
        if not result.get("success"):
            return False

        # Check if we got any rows
        row_count = result.get("row_count", 0)
        if row_count > 0:
            return True

        # Empty result - insufficient
        return False

    def _execute_query_on_connection(
        self, query: str, conn, db_label: str = ""
    ) -> Dict[str, Any]:
        """Execute a validated read-only query on a specific connection."""
        import time
        start_time = time.time()

        try:
            validation = self._validate_read_only_query(query)
            if not validation["success"]:
                return {
                    "success": False,
                    "error": validation["error"],
                    "execution_time": 0,
                    "data": [],
                    "row_count": 0,
                    "columns": [],
                    "db_source": db_label,
                }

            row_limit = max(1, int(Config.OLTP_QUERY_LIMIT))
            with conn.cursor() as cur:
                relation_validation = self._explain_and_validate_relations(
                    cur, query, db_label
                )
                if not relation_validation["success"]:
                    conn.rollback()
                    return {
                        "success": False,
                        "error": relation_validation["error"],
                        "execution_time": round(time.time() - start_time, 3),
                        "data": [],
                        "row_count": 0,
                        "columns": [],
                        "db_source": db_label,
                    }
                cur.execute(query)
                columns = (
                    [desc[0] for desc in cur.description] if cur.description else []
                )
                rows = cur.fetchmany(row_limit + 1)
                truncated = len(rows) > row_limit
                if truncated:
                    rows = rows[:row_limit]

                # Convert to list of dicts
                data = [dict(zip(columns, row)) for row in rows]
                execution_time = time.time() - start_time
                conn.commit()

                msg = f"Query executed successfully on {db_label}. Returned {len(data)} row(s) in {execution_time:.3f}s."
                return {
                    "success": True,
                    "data": data,
                    "row_count": len(data),
                    "columns": columns,
                    "execution_time": round(execution_time, 3),
                    "message": msg,
                    "db_source": db_label,
                    "truncated": truncated,
                    "row_limit": row_limit,
                }

        except Exception as e:
            execution_time = time.time() - start_time
            conn.rollback()
            return {
                "success": False,
                "error": str(e),
                "execution_time": round(execution_time, 3),
                "data": [],
                "row_count": 0,
                "columns": [],
                "db_source": db_label,
            }

    def sql_db_query(self, query: str, target_db: str = None) -> Dict[str, Any]:
        """
        Execute query with intelligent routing

        Args:
            query: SQL query string
            target_db: Optional target database ('OLAP' or 'OLTP')
                      If None, tries OLAP first with fallback
        """
        try:
            self.ensure_clean_transaction()
            validation = self._validate_read_only_query(query)
            if not validation["success"]:
                return {
                    "success": False,
                    "error": validation["error"],
                    "data": [],
                    "row_count": 0,
                    "columns": [],
                }

            target = self._normalize_target_db(target_db)
            primary_conn, primary_label = self._ensure_connection_ready(
                target or "OLAP"
            )
            logger.info("Querying selected %s database", primary_label)
            primary_result = self._execute_query_on_connection(
                query, primary_conn, primary_label
            )
            self.query_history.append(
                {
                    "query": query,
                    "row_count": primary_result.get("row_count", 0),
                    "execution_time": primary_result.get("execution_time", 0),
                    "db_source": primary_label,
                    "success": primary_result.get("success", False),
                }
            )

            # An explicitly selected layer is authoritative. An empty result is
            # valid and must not silently change meaning by querying a different
            # database.
            if target or primary_result.get("success"):
                if target:
                    primary_result["rag_recommended"] = True
                return primary_result

            # Backward-compatible auto routing: fallback only when OLAP could
            # not execute the SQL (for example, an OLTP-only table). Never
            # fallback merely because a valid SELECT returned zero rows.
            if self.dual_mode and self.oltp_conn and Config.ENABLE_OLTP_FALLBACK:
                logger.info("OLAP execution failed; trying OLTP fallback")
                fallback_result = self._execute_query_on_connection(
                    query, self.oltp_conn, "OLTP"
                )
                self.query_history.append(
                    {
                        "query": query,
                        "row_count": fallback_result.get("row_count", 0),
                        "execution_time": fallback_result.get("execution_time", 0),
                        "db_source": "OLTP",
                        "success": fallback_result.get("success", False),
                    }
                )
                if fallback_result.get("success"):
                    fallback_result["fallback_used"] = True
                    return fallback_result

            return primary_result

        except Exception as e:
            logger.error(f"Error in sql_db_query: {e}")
            self.transaction_in_error = True
            if self.conn:
                self.conn.rollback()
            return {
                "success": False,
                "error": str(e),
                "data": [],
                "row_count": 0,
                "columns": [],
            }

    def create_visualization_config(
        self,
        data: List[Dict],
        chart_type: str,
        x_column: str,
        y_column: str,
        title: str,
    ) -> Dict[str, Any]:

        try:
            if not data:
                return {
                    "success": False,
                    "error": "No data provided for visualization.",
                }

            # Validate columns exist
            if data and x_column not in data[0]:
                return {
                    "success": False,
                    "error": f"Column '{x_column}' not found in data.",
                }

            if data and y_column not in data[0]:
                return {
                    "success": False,
                    "error": f"Column '{y_column}' not found in data.",
                }

            viz_config = {
                "chart_type": chart_type,
                "x_column": x_column,
                "y_column": y_column,
                "title": title,
                "data_preview": data[:5],  # First 5 rows for preview
            }

            return {
                "success": True,
                "viz_config": viz_config,
                "message": f"Visualization config created: {chart_type} chart with {x_column} vs {y_column}.",
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_join_path(self, from_table: str, to_table: str) -> List[Dict]:
        try:
            self.ensure_clean_transaction()

            # Build FK graph
            fk_graph = {}
            tables_result = self.sql_db_list_tables()

            if not tables_result["success"]:
                return []

            schemas_result = self.sql_db_schema(tables_result["tables"])

            if not schemas_result["success"]:
                return []

            for table, schema in schemas_result["schemas"].items():
                fk_graph[table] = []
                for fk in schema["foreign_keys"]:
                    fk_graph[table].append(
                        {
                            "from_col": fk["column"],
                            "to_table": fk["references_table"],
                            "to_col": fk["references_column"],
                        }
                    )

            # BFS to find shortest path
            queue = deque([(from_table, [])])
            visited = {from_table}

            while queue:
                current, path = queue.popleft()

                if current == to_table:
                    return path

                for fk in fk_graph.get(current, []):
                    if fk["to_table"] not in visited:
                        visited.add(fk["to_table"])
                        new_path = path + [
                            {
                                "from_table": current,
                                "from_col": fk["from_col"],
                                "to_table": fk["to_table"],
                                "to_col": fk["to_col"],
                            }
                        ]
                        queue.append((fk["to_table"], new_path))

            return []  # No path found

        except Exception as e:
            logger.error(f"Error finding join path: {e}")
            self.conn.rollback()
            return []

    def close(self):
        """Close database connections"""
        if self.conn:
            try:
                self.conn.rollback()
            except:
                pass
            self.conn.close()

        if self.oltp_conn:
            try:
                self.oltp_conn.rollback()
            except:
                pass
            self.oltp_conn.close()
