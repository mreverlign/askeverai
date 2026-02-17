import psycopg2
from typing import Dict, List, Any, Tuple
import pandas as pd
from src.config.config import Config
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

    def connect(self) -> bool:
        try:
            # Connect to OLAP (or single DB in legacy mode)
            self.conn = psycopg2.connect(**self.olap_config)
            self.conn.autocommit = False
            timeout = Config.DB_QUERY_TIMEOUT
            with self.conn.cursor() as cur:
                cur.execute(f"SET statement_timeout = {timeout * 1000};")
            self.conn.commit()
            self.transaction_in_error = False

            # Connect to OLTP if in dual mode
            if self.dual_mode and self.oltp_config:
                try:
                    self.oltp_conn = psycopg2.connect(**self.oltp_config)
                    self.oltp_conn.autocommit = False
                    with self.oltp_conn.cursor() as cur:
                        cur.execute(f"SET statement_timeout = {timeout * 1000};")
                    self.oltp_conn.commit()
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

    def sql_db_list_tables(self) -> Dict[str, Any]:
        try:
            self.ensure_clean_transaction()

            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT tablename
                    FROM pg_tables
                    WHERE schemaname = 'public'
                    ORDER BY tablename;
                    """
                )
                tables = [row[0] for row in cur.fetchall()]
                self.conn.commit()

                return {
                    "success": True,
                    "tables": tables,
                    "count": len(tables),
                    "message": f"Found {len(tables)} tables in the database.",
                }
        except Exception as e:
            self.transaction_in_error = True
            self.conn.rollback()
            return {"success": False, "error": str(e), "tables": []}

    def sql_db_schema(self, tables: List[str]) -> Dict[str, Any]:
        try:
            self.ensure_clean_transaction()

            schemas = {}
            for table in tables:
                # Check cache first
                cache_key = f"schema_{table}"
                if cache_key in self.metadata_cache:
                    schemas[table] = self.metadata_cache[cache_key]
                    continue

                try:
                    with self.conn.cursor() as cur:
                        # Get column information
                        cur.execute(
                            f"""
                            SELECT column_name, data_type, is_nullable
                            FROM information_schema.columns
                            WHERE table_schema = 'public' AND table_name = '{table}'
                            ORDER BY ordinal_position;
                            """
                        )
                        columns = [
                            {
                                "name": row[0],
                                "type": row[1],
                                "nullable": row[2] == "YES",
                            }
                            for row in cur.fetchall()
                        ]

                        # If table not found in OLAP, try OLTP fallback
                        if not columns and self.dual_mode and self.oltp_conn:
                            try:
                                with self.oltp_conn.cursor() as oltp_cur:
                                    oltp_cur.execute(
                                        f"""
                                        SELECT column_name, data_type, is_nullable
                                        FROM information_schema.columns
                                        WHERE table_schema = 'public' AND table_name = '{table}'
                                        ORDER BY ordinal_position;
                                        """
                                    )
                                    columns = [
                                        {
                                            "name": row[0],
                                            "type": row[1],
                                            "nullable": row[2] == "YES",
                                        }
                                        for row in oltp_cur.fetchall()
                                    ]
                                    if columns:
                                        logger.info(f"Table {table} found in OLTP (not in OLAP)")
                                self.oltp_conn.commit()
                            except Exception as oltp_err:
                                logger.warning(f"OLTP schema fallback failed for {table}: {oltp_err}")
                                try:
                                    self.oltp_conn.rollback()
                                except Exception:
                                    pass

                        # Skip if table doesn't exist in either database
                        if not columns:
                            logger.warning(f"Table {table} not found or has no columns")
                            continue

                        # Get primary keys - use safer query
                        try:
                            cur.execute(
                                f"""
                                SELECT a.attname
                                FROM pg_index i
                                JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                                JOIN pg_class c ON c.oid = i.indrelid
                                WHERE c.relname = '{table}' AND i.indisprimary;
                                """
                            )
                            primary_keys = [row[0] for row in cur.fetchall()]
                        except Exception as pk_error:
                            logger.warning(
                                f"Could not get primary keys for {table}: {pk_error}"
                            )
                            primary_keys = []

                        # Get foreign keys
                        cur.execute(
                            f"""
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
                              AND tc.table_name = '{table}';
                            """
                        )
                        foreign_keys = [
                            {
                                "column": row[0],
                                "references_table": row[1],
                                "references_column": row[2],
                            }
                            for row in cur.fetchall()
                        ]

                        # Get row count - use safer query
                        try:
                            cur.execute(f'SELECT COUNT(*) FROM "{table}";')
                            row_count = cur.fetchone()[0]
                        except Exception as count_error:
                            logger.warning(
                                f"Could not get row count for {table}: {count_error}"
                            )
                            row_count = 0

                        # Get sample rows - with error handling
                        sample_rows = []
                        try:
                            sample_query = f'SELECT * FROM "{table}" LIMIT 3'
                            cur.execute(sample_query)
                            columns_names = [desc[0] for desc in cur.description]
                            sample_rows = [
                                dict(zip(columns_names, row)) for row in cur.fetchall()
                            ]
                        except Exception as sample_error:
                            logger.warning(
                                f"Could not get sample rows for {table}: {sample_error}"
                            )

                        # Get statistics for numeric columns
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
                                        f'SELECT MIN("{col["name"]}"), MAX("{col["name"]}"), AVG("{col["name"]}") FROM "{table}" WHERE "{col["name"]}" IS NOT NULL'
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

                        # Build schema info
                        schema_info = {
                            "columns": columns,
                            "primary_keys": primary_keys,
                            "foreign_keys": foreign_keys,
                            "row_count": row_count,
                            "sample_rows": sample_rows,
                            "numeric_stats": numeric_stats,
                        }

                        # Cache the schema
                        self.metadata_cache[cache_key] = schema_info
                        schemas[table] = schema_info

                except Exception as table_error:
                    logger.error(
                        f"Error getting schema for table {table}: {table_error}"
                    )
                    self.conn.rollback()  # Rollback the transaction for this table
                    self.ensure_clean_transaction()  # Ensure clean state for next table
                    continue

            self.conn.commit()  # Commit all successful schema retrievals

            return {
                "success": True,
                "schemas": schemas,
                "message": f"Retrieved schema for {len(schemas)} table(s).",
            }

        except Exception as e:
            self.transaction_in_error = True
            self.conn.rollback()
            logger.error(f"Error in sql_db_schema: {e}")
            return {"success": False, "error": str(e), "schemas": {}}

    def sql_db_query_checker(self, query: str) -> Dict[str, Any]:
        try:
            self.ensure_clean_transaction()

            if not query or not query.strip():
                return {
                    "success": False,
                    "error": "Empty query provided.",
                    "suggestion": "Please provide a valid SQL query.",
                }

            query_upper = query.upper()

            # Check for dangerous operations
            dangerous_keywords = ["DROP", "DELETE", "TRUNCATE", "ALTER", "CREATE"]
            for keyword in dangerous_keywords:
                if keyword in query_upper:
                    return {
                        "success": False,
                        "error": f"Query contains dangerous operation: {keyword}",
                        "suggestion": "Only SELECT queries are allowed for safety.",
                    }

            # Validate with PostgreSQL EXPLAIN
            with self.conn.cursor() as cur:
                try:
                    cur.execute(f"EXPLAIN {query}")
                    self.conn.commit()  # Commit successful validation
                    return {
                        "success": True,
                        "message": "Query syntax is valid.",
                        "suggestion": "The query passed validation. You can now execute it with sql_db_query[].",
                    }
                except psycopg2.Error as e:
                    self.conn.rollback()
                    self.transaction_in_error = (
                        False  # Reset error state after rollback
                    )
                    return {
                        "success": False,
                        "error": str(e),
                        "suggestion": "Check your SQL syntax. Common issues: missing quotes around table/column names, incorrect JOIN conditions, or invalid column references.",
                    }

        except Exception as e:
            self.transaction_in_error = True
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

    def _execute_query_on_connection(self, query: str, conn, db_label: str = "") -> Dict[str, Any]:
        """Execute query on a specific connection"""
        import time
        start_time = time.time()

        try:
            with conn.cursor() as cur:
                cur.execute(query)
                columns = (
                    [desc[0] for desc in cur.description] if cur.description else []
                )
                rows = cur.fetchall()

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

            # If target_db specified by RAG, try that first
            if target_db == 'OLTP' and self.dual_mode and self.oltp_conn:
                logger.info("RAG recommends OLTP - Querying OLTP database...")
                oltp_result = self._execute_query_on_connection(query, self.oltp_conn, "OLTP")

                self.query_history.append({
                    "query": query,
                    "row_count": oltp_result.get("row_count", 0),
                    "execution_time": oltp_result.get("execution_time", 0),
                    "db_source": "OLTP",
                })

                # If OLTP succeeds, return it
                if oltp_result.get("success") and oltp_result.get("row_count", 0) > 0:
                    logger.info(f"OLTP returned {oltp_result['row_count']} rows")
                    oltp_result["rag_recommended"] = True
                    return oltp_result

                # OLTP failed or empty, try OLAP as fallback
                logger.info("OLTP returned no results, trying OLAP fallback...")
                olap_result = self._execute_query_on_connection(query, self.conn, "OLAP")

                self.query_history.append({
                    "query": query,
                    "row_count": olap_result.get("row_count", 0),
                    "execution_time": olap_result.get("execution_time", 0),
                    "db_source": "OLAP",
                })

                if olap_result.get("success"):
                    logger.info(f"OLAP fallback returned {olap_result.get('row_count', 0)} rows")
                    olap_result["fallback_used"] = True
                    olap_result["oltp_row_count"] = oltp_result.get("row_count", 0)
                    return olap_result

                # Both failed, return OLTP error (primary target)
                return oltp_result

            # Default: Try OLAP first
            logger.info("🔍 Querying OLAP database...")
            olap_result = self._execute_query_on_connection(query, self.conn, "OLAP")

            self.query_history.append({
                "query": query,
                "row_count": olap_result.get("row_count", 0),
                "execution_time": olap_result.get("execution_time", 0),
                "db_source": "OLAP",
            })

            # Check if OLAP result is sufficient
            if self._is_result_sufficient(olap_result):
                logger.info(f"OLAP returned {olap_result['row_count']} rows - sufficient")
                return olap_result

            # If dual mode enabled and OLTP connection available, try fallback
            if self.dual_mode and self.oltp_conn and Config.ENABLE_OLTP_FALLBACK:
                logger.info(f"OLAP returned {olap_result.get('row_count', 0)} rows - insufficient")
                logger.info("Falling back to OLTP database...")

                oltp_result = self._execute_query_on_connection(query, self.oltp_conn, "OLTP")

                self.query_history.append({
                    "query": query,
                    "row_count": oltp_result.get("row_count", 0),
                    "execution_time": oltp_result.get("execution_time", 0),
                    "db_source": "OLTP",
                })

                if oltp_result.get("success"):
                    logger.info(f"OLTP returned {oltp_result['row_count']} rows")
                    oltp_result["fallback_used"] = True
                    oltp_result["olap_row_count"] = olap_result.get("row_count", 0)
                    return oltp_result
                else:
                    logger.error(f"OLTP query failed: {oltp_result.get('error')}")
                    return oltp_result

            # No fallback available or not needed, return OLAP result
            return olap_result

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
