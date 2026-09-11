from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Any, List, Optional
from llm_client import LLMClient
from src.tools.database_tools import DatabaseTools, SchemaContextManager
from src.tools.date_handler import DateHandler
from src.config.config import Config
from src.domain.hightower import (
    DATA_COVERAGE,
    FACT_ROW_COUNTS,
    TABLES_BY_LAYER,
    choose_layer_for_counts,
    infer_layer_from_query,
    is_explanation_query,
    join_closure,
    tables_for_query_intent,
)
import re
import difflib
import sqlparse
import traceback
import logging

if TYPE_CHECKING:
    from src.embedders.structured_embedder import StructuredMetadataEmbedder

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EnhancedRAGReActAgent:
    def __init__(
        self,
        llm_client: LLMClient,
        db_tools: DatabaseTools,
        embedder: StructuredMetadataEmbedder,
    ):
        self.llm_client = llm_client
        self.db_tools = db_tools
        self.schema_manager = SchemaContextManager(db_tools)
        self.embedder = embedder
        self.date_handler = DateHandler(db_tools)
        self.conversation_history = []
        self.max_iterations = Config.MAX_AGENT_ITERATIONS
        self.recommended_db = None
        self._schema_cache = (
            {}
        )  # {table_name: [col1, col2, ...]} populated during context formatting
        self._fact_row_counts = dict(FACT_ROW_COUNTS)
        self._data_coverage = {
            layer: dict(coverage) for layer, coverage in DATA_COVERAGE.items()
        }

        logger.info("Agent initialized")

    def _extract_relevant_context(
        self, query: str, top_k: int = 10, forced_db: str = None
    ) -> Dict[str, Any]:
        logger.info(f"Extracting context: {query}")

        if forced_db:
            # An intent-level selection is authoritative; avoid doing an
            # unnecessary second-layer embedding search just to overwrite it.
            recommended_db = str(forced_db).upper()
            layer_decision = {
                "recommended_db": recommended_db,
                "olap_score": 0.0,
                "oltp_score": 0.0,
                "confidence": 1.0,
                "reason": "domain_intent",
            }
        else:
            layer_decision = self.embedder.search_with_layer_preference(
                query, top_k=top_k
            )
            recommended_db = choose_layer_for_counts(
                query,
                layer_decision.get("recommended_db", "OLAP"),
                self._fact_row_counts.get("OLAP", 0),
                self._fact_row_counts.get("OLTP", 0),
            )

        logger.info(
            f"Recommended DB: {recommended_db} (OLAP: {layer_decision.get('olap_score', 0):.3f}, OLTP: {layer_decision.get('oltp_score', 0):.3f})"
        )

        column_results = self.embedder.search_columns(
            query, layer=recommended_db, top_k=top_k
        )
        logger.info(f"Columns ({recommended_db}): {len(column_results)} matches")

        table_results = self.embedder.search_tables(
            query, layer=recommended_db, top_k=5
        )
        logger.info(f"Tables ({recommended_db}): {len(table_results)} matches")

        relevant_tables = set()
        relevant_columns = {}

        for result in table_results:
            table = result.get("table", "").strip()
            if table:
                relevant_tables.add(table.lower())

        for result in column_results:
            table = result.get("table", "").strip()
            column = result.get("column", "").strip()
            description = result.get("description", "")
            role = result.get("role", "")

            if table:
                table_lower = table.lower()
                relevant_tables.add(table_lower)

                if table_lower not in relevant_columns:
                    relevant_columns[table_lower] = []

                if column:
                    relevant_columns[table_lower].append(
                        {
                            "column": column.lower(),
                            "description": description,
                            "role": role,
                            "hybrid_score": result.get("hybrid_score", 0),
                        }
                    )

        # The source relationship CSV has shifted/blank fields and describes
        # two fact joins incorrectly. Use the validated live-data manifest and
        # include only the join closure needed by the retrieved tables.
        available_tables = TABLES_BY_LAYER.get(recommended_db, frozenset())
        intent_tables = set(tables_for_query_intent(query, recommended_db))
        if intent_tables:
            seed_tables = intent_tables
        else:
            candidate_scores = {}
            for result in table_results + column_results:
                table = result.get("table", "").strip().lower()
                if table in available_tables:
                    candidate_scores[table] = max(
                        candidate_scores.get(table, 0.0),
                        float(result.get("hybrid_score", 0.0)),
                    )
            best_score = max(candidate_scores.values(), default=0.0)
            threshold = max(0.15, best_score * 0.75)
            seed_tables = {
                table for table, score in candidate_scores.items() if score >= threshold
            }
            if not seed_tables and candidate_scores:
                seed_tables = {max(candidate_scores, key=candidate_scores.get)}

        closure = join_closure(recommended_db, seed_tables)
        relevant_tables = set(closure["tables"])
        relationships = list(closure["relationships"])
        all_relationship_results = relationships
        column_results = [
            result
            for result in column_results
            if result.get("table", "").strip().lower() in relevant_tables
        ]
        table_results = [
            result
            for result in table_results
            if result.get("table", "").strip().lower() in relevant_tables
        ]
        relevant_columns = {
            table: columns
            for table, columns in relevant_columns.items()
            if table in relevant_tables
        }
        logger.info(
            "Validated relationships (%s): %d",
            recommended_db,
            len(relationships),
        )

        context = {
            "relevant_tables": sorted(relevant_tables),
            "relevant_columns": relevant_columns,
            "relationships": relationships,
            "column_results": column_results[:10],
            "table_results": table_results[:5],
            "relationship_results": all_relationship_results[:10],
            "recommended_db": recommended_db,
            "layer_decision": layer_decision,
            "data_coverage": self._data_coverage.get(recommended_db, {}),
            "retrieval_schema_notice": (
                "Actual live schema below is authoritative for names and types; "
                "legacy embedding descriptions may be stale."
            ),
        }

        logger.info(
            f"Context extracted: Tables={len(relevant_tables)}, Relationships={len(relationships)}"
        )
        return context

    def _refresh_fact_row_counts(self) -> set:
        """Refresh routing and date cutoffs from live data without failing a query."""

        unavailable_layers = set()
        for layer in ("OLAP", "OLTP"):
            try:
                coverage = self.db_tools.sql_db_fact_coverage(layer)
                if coverage.get("success"):
                    self._fact_row_counts[layer] = int(coverage["row_count"])
                    self._data_coverage[layer] = {
                        "min_dateid": coverage["min_dateid"],
                        "max_dateid": coverage["max_dateid"],
                    }
                else:
                    unavailable_layers.add(layer)
                    self._fact_row_counts[layer] = 0
            except Exception as error:
                logger.warning("Could not refresh %s fact count: %s", layer, error)
                unavailable_layers.add(layer)
                self._fact_row_counts[layer] = 0
        return unavailable_layers

    def _detect_table_names(self, query: str, search_results: List[Dict]) -> List[str]:
        tables = set()
        for result in search_results:
            table = result.get("table", "")
            if table:
                tables.add(table.lower())

            primary_table = result.get("primary_table", "")
            if primary_table:
                tables.add(primary_table.lower())

            foreign_table = result.get("foreign_table", "")
            if foreign_table:
                tables.add(foreign_table.lower())

        return list(tables)

    def _format_rag_context(
        self, context: Dict[str, Any], include_schema: bool = True
    ) -> str:
        parts = []

        parts.append("## RAG HYBRID SEARCH RESULTS (BM25 + Semantic):")
        parts.append("")
        parts.append(
            "**Authority:** Actual database schema and validated relationships below "
            "override legacy embedding descriptions."
        )
        parts.append(f"**Search Configuration:**")
        parts.append(f"- Selected database layer: {self.recommended_db}")
        parts.append(f"- BM25 Weight: {self.embedder.bm25_weight} (keyword matching)")
        parts.append(
            f"- Semantic Weight: {self.embedder.semantic_weight} (conceptual similarity)"
        )
        parts.append("")

        if include_schema and context.get("relevant_tables"):
            parts.append("### ACTUAL DATABASE SCHEMA (Most Relevant Tables)")
            parts.append(
                "**IMPORTANT: Use these EXACT column names in your SQL queries**"
            )
            parts.append("")

            top_tables = list(context["relevant_tables"])[:10]

            try:
                schema_result = self.db_tools.sql_db_schema(
                    top_tables, target_db=self.recommended_db
                )

                if schema_result["success"]:
                    for table_name, schema_info in schema_result["schemas"].items():
                        # Cache column names for validation
                        self._schema_cache[table_name.lower()] = [
                            col["name"].lower() for col in schema_info["columns"]
                        ]
                        parts.append(f"**Table: `{table_name}`**")
                        parts.append(f"Columns:")
                        for col in schema_info["columns"]:
                            parts.append(f"   - `{col['name']}` ({col['type']})")

                        if schema_info.get("primary_keys"):
                            parts.append(
                                f"Primary Keys: {', '.join(f'`{pk}`' for pk in schema_info['primary_keys'])}"
                            )

                        if schema_info.get("foreign_keys"):
                            parts.append("Foreign Keys (for JOINs):")
                            for fk in schema_info["foreign_keys"]:
                                parts.append(
                                    f"   - `{fk['column']}` -> `{fk['references_table']}.{fk['references_column']}`"
                                )

                        parts.append(f"Row Count: {schema_info['row_count']:,}")
                        parts.append("")
                else:
                    logger.warning(
                        f"Schema loading skipped: {schema_result.get('error')}"
                    )
                    parts.append(
                        f"Schema loading skipped (will use sql_db_schema action instead)"
                    )
                    parts.append("")
            except Exception as e:
                logger.error(f"Error loading schema: {e}")
                parts.append(
                    f"Schema loading skipped (will use sql_db_schema action instead)"
                )
                parts.append("")

            parts.append("---")
            parts.append("")

        parts.append("### STEP 1: RELATIONSHIPS - JOIN CONDITIONS (MOST IMPORTANT)")
        parts.append("**Use these exact join conditions in your SQL queries:**")
        parts.append("")

        if context["relationships"]:
            for i, rel in enumerate(context["relationships"][:8], 1):
                parts.append(f"**Relationship {i}:**")
                parts.append(f"   Primary Table: `{rel['primary_table']}`")
                parts.append(f"   Primary Key: `{rel['primary_key']}`")
                parts.append(f"   Foreign Table: `{rel['foreign_table']}`")
                parts.append(f"   Foreign Key: `{rel['foreign_key']}`")

                if rel["join_condition"]:
                    parts.append(f"   **EXACT JOIN SYNTAX:** `{rel['join_condition']}`")
                    parts.append(
                        f"   **SQL:** `JOIN {rel['primary_table']} ON {rel['join_condition']}`"
                    )

                if rel.get("coverage"):
                    parts.append(f"   Coverage: {rel['coverage']}")
                if rel.get("note"):
                    parts.append(f"   Important: {rel['note']}")

                parts.append(f"   Relationship Type: {rel['relationship_type']}")
                parts.append("")
        else:
            parts.append("No relationships found. Query may not require joins.")
            parts.append("")

        parts.append("### STEP 2: METADATA - Column Information")
        parts.append("")

        if context["column_results"]:
            for i, result in enumerate(context["column_results"][:8], 1):
                table = result.get("table", "")
                column = result.get("column", "")
                desc = result.get("description", "")
                role = result.get("role", "")

                parts.append(f"**Column {i}:**")
                parts.append(f"   Table: `{table}`")
                parts.append(f"   Column: `{column}`")
                parts.append(f"   Full Name: `{table}.{column}`")
                parts.append(f"   Role: {role}")

                if desc:
                    parts.append(f"   Description: {desc}")

                parts.append("")
        else:
            parts.append("No metadata matches found.")
            parts.append("")

        parts.append("### STEP 3: RELEVANT TABLES SUMMARY:")
        if context["relevant_tables"]:
            for table in sorted(context["relevant_tables"])[:10]:
                parts.append(f"   - `{table}`")
        parts.append("")

        parts.append("### CRITICAL SQL GENERATION INSTRUCTIONS:")
        parts.append("1. **ALWAYS use the exact join conditions provided above**")
        parts.append(
            "2. **Use fully qualified column names** (e.g., `dim_client.clientid`, not just `clientid`)"
        )
        parts.append("3. **Reference the relationship section** when joining tables")
        parts.append(
            "4. **GROUP BY is MANDATORY** when using aggregates (SUM, COUNT, AVG) with non-aggregate columns"
        )
        parts.append("5. **Verify table names** from the relevant tables summary")
        parts.append(
            "6. For free-text matching, use ILIKE only when the user asks for a contains/partial match; use = for exact values"
        )
        parts.append("")

        return "\n".join(parts)

    def _create_react_prompt(
        self,
        user_query: str,
        rag_context: str,
        iteration: int,
        previous_steps: List[Dict],
        conversation_history: list = None,
        is_why_query: bool = False,
    ) -> str:
        date_instructions = self.date_handler.create_dateid_replacement_instructions(
            user_query, layer=self.recommended_db
        )

        steps_context = ""
        if previous_steps:
            steps_context = "\n### Previous Steps:\n"
            for i, step in enumerate(previous_steps, 1):
                if step["type"] == "thought":
                    steps_context += f"\nThought {i}: {step['content']}\n"
                elif step["type"] == "action":
                    steps_context += f"Action {i}: {step['content']}\n"
                elif step["type"] == "observation":
                    steps_context += f"Observation {i}: {step['content']}\n"

        conv_context = ""
        if conversation_history:
            conv_context = "## CONVERSATION CONTEXT:\nYou are continuing an ongoing conversation. Previous exchanges:\n"
            for item in conversation_history[-5:]:
                conv_context += f"\nUser: {item.get('query', '')}\n"
                if item.get("sql"):
                    conv_context += f"SQL Used: {item['sql']}\n"
                if item.get("answer"):
                    conv_context += f"Result: {item['answer']}\n"
            conv_context += "\nUse this context to understand follow-up questions. "
            conv_context += "If the user says 'it', 'that', 'those', 'break it down', 'more details', etc., refer to the previous context.\n"

        memo_instructions = ""
        if is_why_query:
            memo_instructions = """
## MEMO/EXPLANATION ANALYSIS:
The user is asking for explanations or reasons. CRITICAL:
- ALWAYS include the memo column from fact_transaction_detail in your SELECT
- The memo column (OLTP only) contains notes explaining transactions, adjustments, delays, and changes
- Include memo alongside other relevant columns so the system can analyze and summarize reasons
- If asking about changes/drops/increases, also include date-based comparisons when possible
- Target the OLTP database since memo is only available there
"""

        prompt = f"""You are an expert SQL agent that converts natural language questions into SQL queries.
You have access to a **PostgreSQL database** and must use the ReAct pattern to solve the query.

{rag_context}

{date_instructions}

{conv_context}

## USER QUESTION:
{user_query}

{steps_context}

## YOUR TASK:
Generate SQL using the ReAct pattern. Follow these critical rules:

**Iteration {iteration}/{self.max_iterations}**

## CRITICAL RULES:
1. **LAYER AND JOINS**:
   - Execute only on the selected `{self.recommended_db}` layer.
   - Use only the validated join conditions in the relationship section.
   - Fact grain is one line: `(transactionid, transactiolineid)`.
   - Count business transactions with `COUNT(DISTINCT f.transactionid)`.
   - Join fact `itemid` to `dim_item.skuid`, NEVER to `dim_item.itemid`.
   - `dim_item.skuid` has one duplicate source sentinel (`'1'`), but no current fact references it.
   - Fact `specifier1id` and `enduserid` contain partner IDs despite their names. Follow the validated relationships; never join either to the same-named dimension primary key.
   - When joining `dim_specifier1` or `dim_end_user` by `partnerid`, require `active_flag = 1` to avoid duplicate-row inflation.
   - For product categories, follow fact -> dim_item -> dim_subcategory_item -> dim_item_category.
   - `projectedtotal` repeats on fact lines; aggregate it once per transaction, not once per line.
   - `createdfrom` is transaction-level; join it only to a one-row-per-transaction subquery, never raw fact lines.

2. **DATES**:
   - Transaction-date filters use `f.dateid` as an unquoted YYYYMMDD integer.
   - Use `closedate`, `createddate`, `shipdate`, `expectedclosedate`, or `oppclosedate` only when the user explicitly asks about that event.
   - Selected-layer fact coverage is {self._data_coverage.get(self.recommended_db, {})}. Do not reinterpret "current" as "latest available"; a period beyond this range can correctly return no rows.
   - Treat `oppclosedate` values after year 2100 as source anomalies unless the user explicitly requests them.

3. **TRANSACTION TYPES - BUSINESS LOGIC**:
   - Generic "sales" or "revenue" means Invoice: `f.transactiontypeid = 1000`.
   - Sales Order / ordered value: `f.transactiontypeid = 1002`.
   - Quotation / proposal / pipeline: `f.transactiontypeid = 1001`.
   - Credit Memo / refund / return: `f.transactiontypeid = 1004`.
   - "Shipped", "delivered", or invoiced also uses `1000`.
   - Do not sum all transaction types for revenue; that double-counts stages of the lifecycle.

4. **AMOUNT AND DATA QUALITY**:
   - `amount` is already the source line amount; do not recompute it from quantity × rate.
   - Preserve negative adjustments and zero-value lines unless the user explicitly asks for positive-only sales.
   - For net product sales, exclude subtotal-only IDs `Subtotal for Tariff Recovery Fee` and `Subtotal for Canadian Tariff Credit`; do not add this exclusion to unrelated questions.
   - The `itemtype` and `bifmacategoryname` fields are entirely empty in this extract; do not use them unless requested.

5. **GROUP BY is MANDATORY** when mixing aggregate functions with non-aggregate columns:
   - CORRECT: SELECT c.clientname, SUM(f.amount) FROM ... GROUP BY c.clientname
   - WRONG: SELECT c.clientname, SUM(f.amount) FROM ... (missing GROUP BY)

6. **PRODUCT DISPLAY**:
   - Join on `dim_item.skuid`; display `dim_item.itemid` and `dim_item.productname` when helpful.
   - `dim_item.itemid` is a family-level value and is not unique. Group at the level requested by the user.

7. **TEXT MATCHING**:
   - Use `=`/`IN` for known exact values. Use `ILIKE` only when the user requests partial/contains matching.

8. **PostgreSQL and safety**:
   - Use LIMIT N (not TOP N)
   - Window functions available: OVER (PARTITION BY ...)
   - Generate exactly one read-only SELECT (or WITH ... SELECT) per action. Never generate INSERT, UPDATE, DELETE, DDL, SELECT INTO, or data-modifying CTEs.

## HANDLING MULTIPLE QUERIES:

Prefer one SQL statement. Combine comparisons with conditional aggregation,
UNION ALL, or CTEs. The database tool intentionally accepts exactly one
read-only statement per action.
###
### ReAct Pattern:
1. **Thought**: Analyze what you need to do. Reference the ACTUAL DATABASE SCHEMA section above.
2. **Action**: Choose ONE action from:
   - `sql_db_list_tables[]` - List all available tables
   - `sql_db_schema[table1, table2]` - Get schema for specific tables
   - `sql_db_query_checker[SELECT ...]` - Validate SQL syntax
   - `sql_db_query[SELECT ...]` - Execute final SQL query
3. **Observation**: (System will provide the result)

### Response Format:
Thought: [Your reasoning - reference the schema and relationships above]
Action: [One of the available actions in format: action_name[parameters]]

### IMPORTANT REMINDERS:
- ONLY use exact column names from the "rag_context". NEVER abbreviate or guess column names.
- Only use column names that exist in the provided schema.
- Do NOT invent column names.
-
- If unsure, select the ID column.
- Use EXACT join conditions from "rag_context" section and "JOIN RULES"
- For transaction dates use dateid as an INTEGER in YYYYMMDD format; for explicitly named date events use their actual DATE column
- For aggregates: Always include GROUP BY for non-aggregate columns
- Action format: sql_db_query[SELECT ...] NOT markdown code blocks

{self._format_column_quick_reference()}
{memo_instructions}
Now, proceed with your Thought and Action:
"""

        return prompt

    def _format_column_quick_reference(self) -> str:
        if not self._schema_cache:
            return ""
        lines = ["## COLUMN QUICK REFERENCE (use these EXACT column names):"]
        for table, cols in sorted(self._schema_cache.items()):
            lines.append(f"  {table}: {', '.join(cols)}")
        return "\n".join(lines)

    def process_query(
        self, user_query: str, conversation_history: list = None
    ) -> Dict[str, Any]:
        try:
            logger.info(f"Processing query: {user_query}")

            # Schema names overlap across layers but their columns differ. Pick
            # the layer before retrieval/schema formatting and clear the
            # per-query schema cache so OLAP columns cannot leak into OLTP.
            self._schema_cache = {}
            unavailable_layers = self._refresh_fact_row_counts()

            # Memo text exists only in OLTP, so a genuine "why" question has
            # to go there. Metric words like "increase" are not on their own a
            # why question, which is what is_explanation_query screens for.
            is_why_query = is_explanation_query(user_query)
            layer_override = infer_layer_from_query(user_query)
            if is_why_query:
                layer_override = "OLTP"
            if layer_override in unavailable_layers:
                error = f"The required {layer_override} database is unavailable."
                logger.error(error)
                return {"query": user_query, "error": error, "success": False}
            if layer_override:
                logger.info("Query intent selects %s", layer_override)

            date_filters = self.date_handler.extract_date_filters(user_query)
            if date_filters["has_date_filter"]:
                logger.info("Date filters extracted")

            rag_context_data = self._extract_relevant_context(
                user_query, top_k=10, forced_db=layer_override
            )
            self.recommended_db = rag_context_data.get("recommended_db", "OLAP")
            if self.recommended_db in unavailable_layers:
                available = sorted({"OLAP", "OLTP"} - unavailable_layers)
                if not available:
                    error = "Neither HighTower database is available."
                    return {"query": user_query, "error": error, "success": False}
                self.recommended_db = available[0]
                rag_context_data = self._extract_relevant_context(
                    user_query, top_k=10, forced_db=self.recommended_db
                )
            rag_context_str = self._format_rag_context(rag_context_data)

            if rag_context_data["relationships"]:
                logger.info("Key relationships found")
                for rel in rag_context_data["relationships"][:3]:
                    logger.info(
                        f"   {rel['primary_table']}.{rel['primary_key']} = {rel['foreign_table']}.{rel['foreign_key']}"
                    )

            thought_action_log = []
            previous_steps = []
            final_sql = None
            final_results = None
            all_sql_queries = []
            all_query_results = []

            for iteration in range(1, self.max_iterations + 1):
                logger.info(f"Iteration {iteration}/{self.max_iterations}")

                prompt = self._create_react_prompt(
                    user_query,
                    rag_context_str,
                    iteration,
                    previous_steps,
                    conversation_history=conversation_history,
                    is_why_query=is_why_query,
                )

                logger.info("Sending prompt to LLM")
                response = self.llm_client.generate(
                    prompt, temperature=0.0, max_tokens=4000
                )

                # Surface LLM/transport failures instead of mistaking the error
                # string for a model reply with "No action found".
                if response.startswith("Error:"):
                    logger.error("LLM call failed, aborting query: %s", response)
                    final_results = response
                    break

                thought = self._extract_section(response, "Thought")
                if thought:
                    thought_action_log.append({"type": "thought", "content": thought})
                    previous_steps.append({"type": "thought", "content": thought})
                    logger.info(f"Thought: {thought[:100]}...")

                action = self._extract_section(response, "Action")
                if action:
                    thought_action_log.append({"type": "action", "content": action})
                    previous_steps.append({"type": "action", "content": action})
                    logger.info(f"Action: {action[:100]}...")

                    action_result = self._execute_action(action)
                    observation = action_result["observation"]
                    thought_action_log.append(
                        {"type": "observation", "content": observation}
                    )
                    previous_steps.append(
                        {"type": "observation", "content": observation}
                    )

                    if action_result.get("kind") == "query" and action_result.get(
                        "success"
                    ):
                        queries = action_result.get("queries", [])
                        all_sql_queries.extend(queries)
                        all_query_results.extend(action_result.get("results", []))
                        final_sql = queries[0] if queries else None
                        final_results = observation
                        logger.info("Query executed successfully")
                        break

                    # Newer instruction-following behavior can regress into
                    # repeating a discovery action forever. Stop after the same
                    # action produces the same observation twice in a row.
                    observations = [
                        step["content"]
                        for step in previous_steps
                        if step["type"] == "observation"
                    ]
                    actions = [
                        step["content"]
                        for step in previous_steps
                        if step["type"] == "action"
                    ]
                    if (
                        len(actions) >= 2
                        and len(observations) >= 2
                        and actions[-1].strip() == actions[-2].strip()
                        and observations[-1].strip() == observations[-2].strip()
                    ):
                        logger.warning("Stopping repeated identical action")
                        final_results = (
                            "Agent repeated the same action without making progress: "
                            f"{actions[-1]}"
                        )
                        break
                else:
                    logger.warning("No action found")
                    break

            result = {
                "query": user_query,
                "rag_context": rag_context_data,
                "sql": final_sql,
                "all_sql_queries": (
                    all_sql_queries
                    if all_sql_queries
                    else ([final_sql] if final_sql else [])
                ),
                "results": final_results,
                "all_query_results": all_query_results,
                "multiple_queries": len(all_sql_queries) > 1,
                "thought_process": thought_action_log,
                "iterations": iteration,
                "relevant_tables": rag_context_data["relevant_tables"],
                "relationships_used": rag_context_data["relationships"][:5],
                "success": final_sql is not None,
                "error": (
                    None
                    if final_sql is not None
                    else (
                        final_results
                        or "The agent did not produce a successful read-only SQL query."
                    )
                ),
            }

            logger.info(
                f"Query processing complete (Success: {result['success']}, Iterations: {iteration})"
            )
            return result

        except Exception as e:
            logger.error(f"Error processing query: {str(e)}")
            logger.error(traceback.format_exc())
            return {"query": user_query, "error": str(e), "success": False}

    @staticmethod
    def _find_matching_square_bracket(text: str, open_index: int) -> Optional[int]:
        """Find an action wrapper's closing bracket without parsing SQL literals.

        PostgreSQL uses square brackets for arrays and subscripts, so looking for
        the next ``]`` (or using a finite-depth regex) is not sufficient.  This
        scanner balances nested brackets and ignores bracket characters inside
        quoted strings, quoted identifiers, dollar-quoted strings, and comments.
        """

        if open_index < 0 or open_index >= len(text) or text[open_index] != "[":
            return None

        depth = 1
        index = open_index + 1
        quote = None
        dollar_tag = None
        escape_string = False
        block_comment_depth = 0
        in_line_comment = False

        while index < len(text):
            char = text[index]
            next_char = text[index + 1] if index + 1 < len(text) else ""

            if in_line_comment:
                if char in "\r\n":
                    in_line_comment = False
                index += 1
                continue

            if block_comment_depth:
                if char == "/" and next_char == "*":
                    block_comment_depth += 1
                    index += 2
                elif char == "*" and next_char == "/":
                    block_comment_depth -= 1
                    index += 2
                else:
                    index += 1
                continue

            if dollar_tag is not None:
                if text.startswith(dollar_tag, index):
                    index += len(dollar_tag)
                    dollar_tag = None
                else:
                    index += 1
                continue

            if quote == "'":
                if escape_string and char == "\\" and next_char:
                    index += 2
                elif char == "'" and next_char == "'":
                    index += 2
                elif char == "'":
                    quote = None
                    escape_string = False
                    index += 1
                else:
                    index += 1
                continue

            if quote == '"':
                if char == '"' and next_char == '"':
                    index += 2
                elif char == '"':
                    quote = None
                    index += 1
                else:
                    index += 1
                continue

            if char == "-" and next_char == "-":
                in_line_comment = True
                index += 2
                continue
            if char == "/" and next_char == "*":
                block_comment_depth = 1
                index += 2
                continue

            if char == "'":
                quote = "'"
                previous = text[index - 1] if index else ""
                before_previous = text[index - 2] if index > 1 else ""
                escape_string = previous in "Ee" and not (
                    before_previous.isalnum() or before_previous == "_"
                )
                index += 1
                continue
            if char == '"':
                quote = '"'
                index += 1
                continue

            if char == "$":
                tag_match = re.match(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$", text[index:])
                if tag_match:
                    dollar_tag = tag_match.group(0)
                    index += len(dollar_tag)
                    continue

            if char == "[":
                depth += 1
            elif char == "]":
                depth -= 1
                if depth == 0:
                    return index

            index += 1

        return None

    def _find_bracketed_action_calls(
        self, text: str, action_name: str
    ) -> List[Dict[str, Any]]:
        """Return balanced ``action_name[...]`` calls and their source spans."""

        calls = []
        pattern = re.compile(
            rf"(?<![A-Za-z0-9_]){re.escape(action_name)}\s*\[",
            re.IGNORECASE,
        )
        search_position = 0

        while True:
            match = pattern.search(text, search_position)
            if not match:
                break

            open_index = match.end() - 1
            close_index = self._find_matching_square_bracket(text, open_index)
            if close_index is None:
                search_position = match.end()
                continue

            calls.append(
                {
                    "start": match.start(),
                    "end": close_index + 1,
                    "argument": text[open_index + 1 : close_index],
                }
            )
            search_position = close_index + 1

        return calls

    def _extract_section(self, text: str, section_name: str) -> Optional[str]:
        # Actions are structured wrappers.  Extract the complete balanced call
        # so section-like words inside SQL literals cannot truncate the query.
        if section_name.lower() == "action":
            marker_pattern = re.compile(
                r"^[ \t]*Action\s*:", re.IGNORECASE | re.MULTILINE
            )
            markers = list(marker_pattern.finditer(text))
            if not markers:
                markers = list(re.finditer(r"\bAction\s*:", text, re.IGNORECASE))

            action_names = (
                "sql_db_query_checker",
                "sql_db_query",
                "sql_db_schema",
                "sql_db_list_tables",
            )
            for marker in markers:
                remainder = text[marker.end() :]
                calls = [
                    call
                    for name in action_names
                    for call in self._find_bracketed_action_calls(remainder, name)
                ]
                if calls:
                    first_call = min(calls, key=lambda call: call["start"])
                    # Preserve every action wrapper in this section so the
                    # executor can enforce its exactly-one-query policy.  A
                    # section-looking label inside any balanced wrapper is SQL
                    # content, not the beginning of the next ReAct section.
                    boundary = None
                    section_markers = re.finditer(
                        r"^[ \t]*(?:Thought|Action|Observation|Final Answer)\s*:",
                        remainder,
                        re.IGNORECASE | re.MULTILINE,
                    )
                    for candidate in section_markers:
                        position = candidate.start()
                        if position <= first_call["start"]:
                            continue
                        if any(
                            call["start"] <= position < call["end"] for call in calls
                        ):
                            continue
                        boundary = position
                        break

                    section_end = boundary if boundary is not None else len(remainder)
                    return remainder[first_call["start"] : section_end].strip()

        # Section labels normally begin a line.  Anchoring them prevents words
        # such as "Final Answer:" inside an ordinary inline value from acting
        # as structural delimiters.
        marker = re.search(
            rf"^[ \t]*{re.escape(section_name)}\s*:",
            text,
            re.IGNORECASE | re.MULTILINE,
        )
        if marker:
            remainder = text[marker.end() :]
            boundary = re.search(
                r"^[ \t]*(?:Thought|Action|Observation|Final Answer)\s*:",
                remainder,
                re.IGNORECASE | re.MULTILINE,
            )
            return remainder[: boundary.start() if boundary else None].strip()

        # Keep compatibility with compact one-line model responses.
        pattern = (
            rf"{re.escape(section_name)}\s*:(.+?)"
            r"(?:Thought\s*:|Action\s*:|Observation\s*:|Final Answer\s*:|$)"
        )
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        return match.group(1).strip() if match else None

    def _extract_multiple_sql_queries(self, action: str) -> List[str]:
        queries = []
        calls = self._find_bracketed_action_calls(action, "sql_db_query")

        for call in calls:
            sql = call["argument"].strip()
            sql = self._clean_sql_query(sql)
            if sql and sql.upper().startswith(("SELECT", "WITH")):
                queries.append(sql)

        if queries:
            logger.info(f"Extracted {len(queries)} queries")
            return queries

        sql = self._extract_sql_from_action(action)
        if sql:
            if sql.upper().startswith(("SELECT", "WITH")):
                queries.append(sql)

        return queries

    def _execute_action(self, action: str) -> Dict[str, Any]:
        try:
            action_lower = action.lower()

            if "sql_db_list_tables" in action_lower:
                result = self.db_tools.sql_db_list_tables(target_db=self.recommended_db)
                if result["success"]:
                    return {
                        "kind": "list_tables",
                        "success": True,
                        "observation": (
                            f"Available {self.recommended_db} tables: "
                            f"{', '.join(result['tables'])}"
                        ),
                        "result": result,
                    }
                else:
                    return {
                        "kind": "list_tables",
                        "success": False,
                        "observation": (
                            f"Error listing tables: {result.get('error', 'Unknown error')}"
                        ),
                        "result": result,
                    }

            if "sql_db_schema" in action_lower:
                tables = self._extract_tables_from_action(action)
                if tables:
                    result = self.db_tools.sql_db_schema(
                        tables, target_db=self.recommended_db
                    )
                    if result["success"]:
                        schema_output = []
                        for table_name, schema_info in result["schemas"].items():
                            schema_output.append(f"\n=== Table: {table_name} ===")
                            schema_output.append(f"Columns:")
                            for col in schema_info["columns"]:
                                schema_output.append(
                                    f"  - {col['name']} ({col['type']})"
                                )

                            if schema_info.get("primary_keys"):
                                schema_output.append(
                                    f"Primary Keys: {', '.join(schema_info['primary_keys'])}"
                                )

                            if schema_info.get("foreign_keys"):
                                schema_output.append("Foreign Keys:")
                                for fk in schema_info["foreign_keys"]:
                                    schema_output.append(
                                        f"  - {fk['column']} -> {fk['references_table']}.{fk['references_column']}"
                                    )

                            schema_output.append(
                                f"Row Count: {schema_info['row_count']:,}"
                            )

                            self._schema_cache[table_name.lower()] = [
                                column["name"].lower()
                                for column in schema_info["columns"]
                            ]

                        if not schema_output:
                            return {
                                "kind": "schema",
                                "success": False,
                                "observation": (
                                    f"No requested tables exist in {self.recommended_db}: "
                                    f"{', '.join(tables)}"
                                ),
                                "result": result,
                            }
                        return {
                            "kind": "schema",
                            "success": True,
                            "observation": "\n".join(schema_output),
                            "result": result,
                        }
                    else:
                        return {
                            "kind": "schema",
                            "success": False,
                            "observation": f"Error getting schema: {result.get('error', 'Unknown error')}",
                            "result": result,
                        }
                return {
                    "kind": "schema",
                    "success": False,
                    "observation": "No table names were provided for schema lookup",
                }

            if "sql_db_query_checker" in action_lower:
                sql = self._extract_sql_from_action(action)
                if sql:
                    result = self.db_tools.sql_db_query_checker(
                        sql, target_db=self.recommended_db
                    )
                    if result["success"]:
                        return {
                            "kind": "query_checker",
                            "success": True,
                            "observation": f"Query validation: Valid - {result.get('message', 'OK')}",
                            "result": result,
                        }
                    else:
                        return {
                            "kind": "query_checker",
                            "success": False,
                            "observation": f"Query validation: Invalid - {result.get('error', 'Unknown error')}",
                            "result": result,
                        }
                return {
                    "kind": "query_checker",
                    "success": False,
                    "observation": "No SQL query was provided for validation",
                }

            if (
                "sql_db_query" in action_lower
                or ("```sql" in action_lower)
                or ("select " in action_lower and "from " in action_lower)
            ):
                sql_queries = self._extract_multiple_sql_queries(action)

                if not sql_queries:
                    return {
                        "kind": "query",
                        "success": False,
                        "observation": "No valid read-only SQL query found in action",
                        "queries": [],
                        "results": [],
                    }

                if len(sql_queries) != 1:
                    return {
                        "kind": "query",
                        "success": False,
                        "observation": (
                            "Exactly one SQL statement is allowed per action; "
                            "combine the analysis with CTEs or UNION ALL."
                        ),
                        "queries": sql_queries,
                        "results": [],
                    }

                all_results = []
                total_execution_time = 0

                for idx, sql in enumerate(sql_queries, 1):
                    logger.info(f"Executing Query {idx}/{len(sql_queries)}")

                    validation = self._validate_sql_clauses(sql)

                    if not validation["valid"]:
                        error_msg = f"Query {idx} validation failed:\n"
                        for error in validation["errors"]:
                            error_msg += f"  - ERROR: {error}\n"
                        all_results.append(
                            {
                                "query_number": idx,
                                "sql": sql,
                                "success": False,
                                "error": error_msg,
                            }
                        )
                        continue

                    result = self.db_tools.sql_db_query(
                        sql, target_db=self.recommended_db
                    )
                    total_execution_time += result.get("execution_time", 0)

                    if result["success"]:
                        import pandas as pd

                        if result.get("data") and result["row_count"] > 0:
                            df = pd.DataFrame(result["data"])
                            all_results.append(
                                {
                                    "query_number": idx,
                                    "sql": sql,
                                    "success": True,
                                    "row_count": result["row_count"],
                                    "data": result["data"],
                                    "columns": result.get("columns", []),
                                    "execution_time": result.get("execution_time", 0),
                                    "db_source": result.get("db_source"),
                                    "fallback_used": result.get("fallback_used", False),
                                    "truncated": result.get("truncated", False),
                                    "row_limit": result.get("row_limit"),
                                    "preview": df.head(10).to_string(),
                                }
                            )
                        else:
                            all_results.append(
                                {
                                    "query_number": idx,
                                    "sql": sql,
                                    "success": True,
                                    "row_count": 0,
                                    "data": [],
                                    "columns": result.get("columns", []),
                                    "execution_time": result.get("execution_time", 0),
                                    "db_source": result.get("db_source"),
                                    "fallback_used": result.get("fallback_used", False),
                                    "truncated": result.get("truncated", False),
                                    "row_limit": result.get("row_limit"),
                                    "message": "Query executed successfully but returned no rows",
                                }
                            )
                    else:
                        all_results.append(
                            {
                                "query_number": idx,
                                "sql": sql,
                                "success": False,
                                "error": result.get("error", "Unknown error"),
                                "db_source": result.get("db_source"),
                            }
                        )

                response_parts = []
                response_parts.append(
                    f"Executed {len(sql_queries)} quer{'y' if len(sql_queries) == 1 else 'ies'}"
                )
                response_parts.append(
                    f"Total execution time: {total_execution_time:.2f}s\n"
                )

                for result in all_results:
                    response_parts.append(f"\n{'='*60}")
                    response_parts.append(
                        f"Query {result['query_number']} of {len(sql_queries)}"
                    )
                    response_parts.append(f"{'='*60}")

                    if result["success"]:
                        response_parts.append(
                            f"Success | Rows: {result.get('row_count', 0)} | Time: {result.get('execution_time', 0):.2f}s"
                        )
                        if result.get("preview"):
                            response_parts.append(f"\nPreview:\n{result['preview']}")
                        elif result.get("message"):
                            response_parts.append(f"\n{result['message']}")
                    else:
                        response_parts.append(
                            f"Failed: {result.get('error', 'Unknown error')}"
                        )

                return {
                    "kind": "query",
                    "success": bool(all_results)
                    and all(result["success"] for result in all_results),
                    "observation": "\n".join(response_parts),
                    "queries": sql_queries,
                    "results": all_results,
                }

            return {
                "kind": "unknown",
                "success": False,
                "observation": "Action not recognized. Please use proper format: sql_db_query[SELECT ...]",
            }

        except Exception as e:
            return {
                "kind": "error",
                "success": False,
                "observation": f"Error executing action: {str(e)}",
            }

    def _extract_tables_from_action(self, action: str) -> List[str]:
        match = re.search(r"sql_db_schema\[(.*?)\]", action, re.IGNORECASE)
        if match:
            tables_str = match.group(1)
            return [t.strip().strip("\"'") for t in tables_str.split(",")]
        return []

    def _extract_sql_from_action(self, action: str) -> Optional[str]:
        sql = None

        for action_name in ("sql_db_query", "sql_db_query_checker"):
            calls = self._find_bracketed_action_calls(action, action_name)
            if calls:
                sql = calls[0]["argument"].strip()
                break

        if not sql:
            match = re.search(
                r"```sql\s*\n?(.*?)\n?\s*```", action, re.IGNORECASE | re.DOTALL
            )
            if match:
                sql = match.group(1).strip()

        if not sql:
            match = re.search(r"\b(?:SELECT|WITH)\b", action, re.IGNORECASE)
            if match:
                sql = action[match.start() :].strip()

        if sql:
            sql = self._clean_sql_query(sql)

        return sql

    def _clean_sql_query(self, sql: str) -> str:
        if not sql:
            return sql

        sql = sql.strip()
        if sql.endswith(";"):
            sql = sql[:-1].rstrip()
        sql = re.sub(r"^```\w*\s*", "", sql)
        sql = re.sub(r"\s*```$", "", sql)
        sql = sql.strip()

        try:
            parsed = sqlparse.parse(sql)
            if parsed and len(parsed) > 0:
                stmt = parsed[0]
                stmt_type = stmt.get_type()

                if stmt_type in ("SELECT", "UNKNOWN"):
                    sql = sqlparse.format(
                        sql, reindent=False, keyword_case="upper", strip_whitespace=True
                    )
        except Exception:
            pass

        return sql

    def _validate_sql_clauses(self, sql: str) -> Dict[str, Any]:
        result = {"valid": True, "errors": [], "warnings": []}

        try:
            read_only = self.db_tools._validate_read_only_query(sql)
            if not read_only["success"]:
                result["valid"] = False
                result["errors"].append(read_only["error"])
                return result

            parsed = sqlparse.parse(sql)
            if not parsed or len(parsed) == 0:
                result["valid"] = False
                result["errors"].append("Could not parse SQL statement")
                return result

            sql_upper = sql.upper()

            if re.search(r"\bJOIN\b", sql_upper) and not re.search(
                r"\bON\b", sql_upper
            ):
                result["valid"] = False
                result["errors"].append("JOIN clause without ON condition")

            has_aggregate = any(
                re.search(rf"\b{agg}\s*\(", sql_upper)
                for agg in ["SUM", "COUNT", "AVG", "MIN", "MAX"]
            )
            has_window = re.search(r"\bOVER\s*\(", sql_upper)

            if (
                has_aggregate
                and not has_window
                and not re.search(r"\bGROUP\s+BY\b", sql_upper)
            ):
                select_match = re.search(
                    r"SELECT\s+(DISTINCT\s+)?(.*?)\s+FROM", sql_upper, re.DOTALL
                )
                if select_match:
                    select_part = select_match.group(2).strip()
                    cleaned_select = re.sub(
                        r"\b(SUM|COUNT|AVG|MIN|MAX)\s*\([^)]+\)",
                        "",
                        select_part,
                        flags=re.IGNORECASE,
                    )
                    has_non_aggregate_columns = bool(
                        cleaned_select and cleaned_select not in [",", "", "*"]
                    )
                    has_multiple_columns = "," in select_part

                    if has_non_aggregate_columns and has_multiple_columns:
                        result["valid"] = False
                        result["errors"].append(
                            "Aggregate functions used with non-aggregate columns. Must include GROUP BY clause."
                        )

            if re.search(r"\bTOP\s+\d+", sql_upper):
                result["valid"] = False
                result["errors"].append(
                    "TOP is SQL Server syntax. Use LIMIT for PostgreSQL"
                )

            # Validate column names against cached schema
            if self._schema_cache:
                col_refs = re.findall(
                    r"\b([a-z_][a-z0-9_]*)\.([a-z_][a-z0-9_]*)\b", sql.lower()
                )
                for table_ref, col_ref in col_refs:
                    # Resolve table aliases from FROM/JOIN clauses
                    alias_pattern = rf"\b(?:FROM|JOIN)\s+([a-z_][a-z0-9_]*)\s+(?:AS\s+)?{re.escape(table_ref)}\b"
                    alias_match = re.search(alias_pattern, sql.lower())
                    actual_table = alias_match.group(1) if alias_match else table_ref

                    if actual_table in self._schema_cache:
                        valid_cols = self._schema_cache[actual_table]
                        if col_ref not in valid_cols:
                            suggestions = difflib.get_close_matches(
                                col_ref, valid_cols, n=1, cutoff=0.4
                            )
                            suggestion_msg = (
                                f" Did you mean '{suggestions[0]}'?"
                                if suggestions
                                else ""
                            )
                            result["valid"] = False
                            result["errors"].append(
                                f"Column '{col_ref}' does not exist in table '{actual_table}'. "
                                f"Available columns: {', '.join(valid_cols)}.{suggestion_msg}"
                            )

        except Exception as e:
            result["valid"] = False
            result["errors"].append(f"SQL parsing error: {str(e)}")

        return result


RAGEnhancedReActAgent = EnhancedRAGReActAgent
