from typing import Dict, Any, List, Optional
from llm_client import LLMClient
from src.tools.database_tools import DatabaseTools, SchemaContextManager
from src.embedders.structured_embedder import StructuredMetadataEmbedder
from src.tools.date_handler import DateHandler
from src.config.config import Config
import re
import difflib
import sqlparse
import traceback
import logging

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
        self._schema_cache = {}  # {table_name: [col1, col2, ...]} populated during context formatting

        logger.info("Agent initialized")

    def _extract_relevant_context(self, query: str, top_k: int = 10) -> Dict[str, Any]:
        logger.info(f"Extracting context: {query}")

        layer_decision = self.embedder.search_with_layer_preference(query, top_k=top_k)
        recommended_db = layer_decision.get("recommended_db", "OLAP")

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

        relationship_queries = [query, f"join {query}"]
        detected_tables = self._detect_table_names(
            query, column_results + table_results
        )
        for table in detected_tables[:3]:
            relationship_queries.append(f"join {table}")

        all_relationship_results = []
        seen_relationships = set()

        for rel_query in relationship_queries[:3]:
            rel_results = self.embedder.search_relationships(rel_query, top_k=top_k)
            for result in rel_results:
                rel_key = f"{result.get('primary_table', '')}_{result.get('foreign_table', '')}"
                if rel_key not in seen_relationships:
                    seen_relationships.add(rel_key)
                    all_relationship_results.append(result)

        logger.info(f"Relationships: {len(all_relationship_results)} unique matches")

        relevant_tables = set()
        relevant_columns = {}
        relationships = []

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

        for result in all_relationship_results:
            primary_table = result.get("primary_table", "").strip()
            foreign_table = result.get("foreign_table", "").strip()
            primary_key = result.get("primary_key", "").strip()
            foreign_key = result.get("foreign_key", "").strip()
            rel_type = result.get("relationship_type", "")
            join_condition = result.get("join_condition", "")

            if primary_table and foreign_table:
                relevant_tables.add(primary_table.lower())
                relevant_tables.add(foreign_table.lower())

                relationships.append(
                    {
                        "primary_table": primary_table.lower(),
                        "foreign_table": foreign_table.lower(),
                        "primary_key": primary_key.lower() if primary_key else "",
                        "foreign_key": foreign_key.lower() if foreign_key else "",
                        "join_condition": join_condition,
                        "relationship_type": rel_type,
                        "from": primary_table.lower(),
                        "to": foreign_table.lower(),
                        "hybrid_score": result.get("hybrid_score", 0),
                    }
                )

        relationships.sort(key=lambda x: x.get("hybrid_score", 0), reverse=True)

        context = {
            "relevant_tables": list(relevant_tables),
            "relevant_columns": relevant_columns,
            "relationships": relationships,
            "column_results": column_results[:10],
            "table_results": table_results[:5],
            "relationship_results": all_relationship_results[:10],
            "recommended_db": recommended_db,
            "layer_decision": layer_decision,
        }

        logger.info(
            f"Context extracted: Tables={len(relevant_tables)}, Relationships={len(relationships)}"
        )
        return context

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
        parts.append(f"**Search Configuration:**")
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

            top_tables = list(context["relevant_tables"])[:5]

            try:
                schema_result = self.db_tools.sql_db_schema(top_tables)

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
                        f"   **SQL:** `JOIN {rel['foreign_table']} ON {rel['join_condition']}`"
                    )

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
            "6. **NEVER use ILIKE or LIKE** - Use exact values or LOWER() function for case-insensitive matching"
        )
        parts.append("")

        return "\n".join(parts)

    def _create_react_prompt(
        self,
        user_query: str,
        rag_context: str,
        iteration: int,
        previous_steps: List[Dict],
    ) -> str:
        date_instructions = self.date_handler.create_dateid_replacement_instructions(
            user_query
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

        prompt = f"""You are an expert SQL agent that converts natural language questions into SQL queries.
You have access to a **PostgreSQL database** and must use the ReAct pattern to solve the query.

{rag_context}

{date_instructions}

## USER QUESTION:
{user_query}

{steps_context}

## YOUR TASK:
Generate SQL using the ReAct pattern. Follow these critical rules:

**Iteration {iteration}/{self.max_iterations}**

## JOIN RULES:
When generating SQL queries involving these tables, ALWAYS use the following join rules:
1. **Dim_Specifier1.PartnerID joins to Dim_Partner.PartnerID**
2. **Fact_Transaction_Detail.Specifier1ID joins to Dim_Specifier1.Specifier1ID**
3. **Dim_EndUser.PartnerID joins to Dim_Partner.PartnerID**
4. **Fact_Transaction_Detail.EndUserID joins to Dim_EndUser.EndUserID**
5. **Fact_Transaction_Detail.PartnerID joins directly to Dim_Partner.PartnerID**
6. **Fact_Transaction_Detail.ItemID joins to Dim_Item.SkuID**
7. **Dim_Item.SubCategoryID joins to Dim_SubCategory_Item.SubCategoryID**
8. **Dim_SubCategory_Item.CategoryID joins to Dim_Item_Category.CategoryID**
9. **Always follow this hierarchy**:
    -Fact_Transaction_Detail
        → Dim_Item
            → Dim_SubCategory_Item
                → Dim_Item_Category



## CRITICAL RULES:
1. **general Rules MOST CRITICAL always follow**
   - NEVER join Fact_Transaction_Detail directly to Dim_Partner for Specifier1 or EndUser relationships.
   - ALWAYS go through the intermediate table (Dim_Specifier1 or Dim_EndUser) when required.
   - Use Fact_Transaction_Detail as the driving table.
   - Do NOT invent alternative join paths.
   - NEVER join Fact_Transaction_Detail directly to Dim_SubCategory_Item.
   - NEVER join Fact_Transaction_Detail directly to Dim_Item_Category.
       
1. **DATES - MOST CRITICAL**: ALWAYS use f.dateid in YYYYMMDD format as INTEGER
   - FORBIDDEN: WHERE d.date = '2025-11-25' or any date string format
   - CORRECT: WHERE f.dateid = 20251125 (integer format, no quotes)
   - CORRECT: WHERE f.dateid BETWEEN 20251101 AND 20251130
   - DateID format: YYYYMMDD (e.g., 20251125 = November 25, 2025)

2. **TRANSACTION TYPES - BUSINESS LOGIC**:
   - "Invoice" (transactiontypeid = 1000) = Actual shipment/delivery/revenue
   - "Sales Order" (transactiontypeid = 1002) = Orders placed, not yet shipped
   - "Quotation" (transactiontypeid = 1001) = Initial proposals
   - "Credit Memo" (transactiontypeid = 1004) = Returns/refunds
   - User says "shipped" or "delivered" -> Use transactiontypeid = 1000

3. **DATA QUALITY RULES (ALWAYS APPLY)**:
   - Positive amounts only: WHERE f.amount > 0
   - Exclude tariff items: WHERE f.itemid NOT IN ('Subtotal for Tariff Recovery Fee', 'Subtotal for Canadian Tariff Credit')
   - Use COUNT(DISTINCT) to prevent duplicate counting
   - Active records only: WHERE active_flag = 1 (for dim_end_user, dim_specifier1)

4. **GROUP BY is MANDATORY** when mixing aggregate functions with non-aggregate columns:
   - CORRECT: SELECT c.clientname, SUM(f.amount) FROM ... GROUP BY c.clientname
   - WRONG: SELECT c.clientname, SUM(f.amount) FROM ... (missing GROUP BY)

5. **NEVER use ILIKE or LIKE** - Use exact values or LOWER() for case-insensitive matching:
   - WRONG: WHERE name ILIKE '%value%'
   - CORRECT: WHERE LOWER(name) = LOWER('value')

6. **PRODUCT NAMES**: When user asks for products, SELECT ONLY itemid

7. **PostgreSQL Syntax**:
   - Use LIMIT N (not TOP N)
   - Window functions available: OVER (PARTITION BY ...)

8.**Product Dimensions:**
  - **dim_item** (connects via `fact.itemid` = `dim_item.skuid`)
  - `skuid` - Unique product identifier in dim_item (used for JOIN)
  - `itemid` - Product ID/SKU (use for display)
  - Configuration: `option_1`, `option_2`, `option_3` and their values
  - Links to: `brandpartnerid`, `subcategoryid`

  **CRITICAL - Product Rules:**
  - `itemid` = Unique product identifier (e.g., "PROD-12345")
  - Return ONLY itemid for products

9.**Active Records Only** (for specific tables):
  - `dim_end_user`: `WHERE eu.active_flag = 1`
  - `dim_specifier1`: `WHERE sp.active_flag = 1`   

## HANDLING MULTIPLE QUERIES:

If user asks for multiple separate analyses/tables, generate MULTIPLE queries in ONE Action:

**Example - Multiple Queries:**
```
Action: sql_db_query[SELECT c.clientname, SUM(f.amount) as total FROM ... GROUP BY c.clientname]
sql_db_query[SELECT i.itemid, SUM(f.amount) as total FROM ... GROUP BY i.itemid]
sql_db_query[SELECT p.partnername, SUM(f.amount) as total FROM ... GROUP BY p.partnername]
```

When to use multiple queries:
- "Show me three tables" -> 3 separate queries
- "Display X AND Y" -> 2 queries
- "Compare A versus B" -> 2 queries
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
- For dates: Always use dateid as INTEGER in YYYYMMDD format
- For aggregates: Always include GROUP BY for non-aggregate columns
- Action format: sql_db_query[SELECT ...] NOT markdown code blocks

{self._format_column_quick_reference()}
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

    def process_query(self, user_query: str) -> Dict[str, Any]:
        try:
            logger.info(f"Processing query: {user_query}")

            date_filters = self.date_handler.extract_date_filters(user_query)
            if date_filters["has_date_filter"]:
                logger.info("Date filters extracted")

            rag_context_data = self._extract_relevant_context(user_query, top_k=10)
            rag_context_str = self._format_rag_context(rag_context_data)

            self.recommended_db = rag_context_data.get("recommended_db", "OLAP")

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
                    user_query, rag_context_str, iteration, previous_steps
                )

                logger.info("Sending prompt to LLM")
                response = self.llm_client.generate(
                    prompt, temperature=0.0, max_tokens=4000
                )

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

                    observation = self._execute_action(action)
                    thought_action_log.append(
                        {"type": "observation", "content": observation}
                    )
                    previous_steps.append(
                        {"type": "observation", "content": observation}
                    )

                    if (
                        "sql_db_query[" in action.lower()
                        and "row" in observation.lower()
                    ):
                        queries = self._extract_multiple_sql_queries(action)
                        all_sql_queries.extend(queries)

                        if "Executed" in observation and "quer" in observation:
                            query_blocks = observation.split("=" * 60)
                            for block in query_blocks[1:]:
                                if "Query" in block and "of" in block:
                                    query_result = {"raw_text": block.strip()}
                                    rows_match = re.search(r"Rows:\s*(\d+)", block)
                                    if rows_match:
                                        query_result["row_count"] = int(
                                            rows_match.group(1)
                                        )
                                    all_query_results.append(query_result)

                        final_sql = self._extract_sql_from_action(action)
                        final_results = observation
                        logger.info("Query executed successfully")
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
            }

            logger.info(
                f"Query processing complete (Success: {result['success']}, Iterations: {iteration})"
            )
            return result

        except Exception as e:
            logger.error(f"Error processing query: {str(e)}")
            logger.error(traceback.format_exc())
            return {"query": user_query, "error": str(e), "success": False}

    def _extract_section(self, text: str, section_name: str) -> Optional[str]:
        pattern = f"{section_name}:(.+?)(?:Action:|Observation:|Final Answer:|$)"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None

    def _extract_multiple_sql_queries(self, action: str) -> List[str]:
        queries = []
        pattern = r"sql_db_query\[((?:[^\[\]]|\[(?:[^\[\]]|\[[^\[\]]*\])*\])*)\]"
        matches = re.finditer(pattern, action, re.IGNORECASE | re.DOTALL)

        for match in matches:
            sql = match.group(1).strip()
            sql = self._clean_sql_query(sql)
            if sql and sql.upper().startswith(
                ("SELECT", "WITH", "INSERT", "UPDATE", "DELETE")
            ):
                queries.append(sql)

        if queries:
            logger.info(f"Extracted {len(queries)} queries")
            return queries

        sql = self._extract_sql_from_action(action)
        if sql:
            if ";" in sql:
                for query in sql.split(";"):
                    query = query.strip()
                    if query and query.upper().startswith(
                        ("SELECT", "WITH", "INSERT", "UPDATE", "DELETE")
                    ):
                        queries.append(query)
            else:
                queries.append(sql)

        return queries

    def _execute_action(self, action: str) -> str:
        try:
            action_lower = action.lower()

            if "sql_db_list_tables" in action_lower:
                result = self.db_tools.sql_db_list_tables()
                if result["success"]:
                    return f"Available tables: {', '.join(result['tables'])}"
                else:
                    return (
                        f"Error listing tables: {result.get('error', 'Unknown error')}"
                    )

            if "sql_db_schema" in action_lower:
                tables = self._extract_tables_from_action(action)
                if tables:
                    result = self.db_tools.sql_db_schema(tables)
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

                        return "\n".join(schema_output)
                    else:
                        return f"Error getting schema: {result.get('error', 'Unknown error')}"

            if "sql_db_query_checker" in action_lower:
                sql = self._extract_sql_from_action(action)
                if sql:
                    result = self.db_tools.sql_db_query_checker(sql)
                    if result["success"]:
                        return (
                            f"Query validation: Valid - {result.get('message', 'OK')}"
                        )
                    else:
                        return f"Query validation: Invalid - {result.get('error', 'Unknown error')}"

            if (
                "sql_db_query" in action_lower
                or ("```sql" in action_lower)
                or ("select " in action_lower and "from " in action_lower)
            ):
                sql_queries = self._extract_multiple_sql_queries(action)

                if not sql_queries:
                    return "No valid SQL queries found in action"

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
                                    "execution_time": result.get("execution_time", 0),
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
                                    "execution_time": result.get("execution_time", 0),
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

                return "\n".join(response_parts)

            return "Action not recognized. Please use proper format: sql_db_query[SELECT ...]"

        except Exception as e:
            return f"Error executing action: {str(e)}"

    def _extract_tables_from_action(self, action: str) -> List[str]:
        match = re.search(r"sql_db_schema\[(.*?)\]", action, re.IGNORECASE)
        if match:
            tables_str = match.group(1)
            return [t.strip().strip("\"'") for t in tables_str.split(",")]
        return []

    def _extract_sql_from_action(self, action: str) -> Optional[str]:
        sql = None

        match = re.search(r"sql_db_query\[(.+)\]", action, re.IGNORECASE | re.DOTALL)
        if match:
            sql = match.group(1).strip()

        if not sql:
            match = re.search(
                r"sql_db_query_checker\[(.+)\]", action, re.IGNORECASE | re.DOTALL
            )
            if match:
                sql = match.group(1).strip()

        if not sql:
            match = re.search(
                r"```sql\s*\n?(.*?)\n?\s*```", action, re.IGNORECASE | re.DOTALL
            )
            if match:
                sql = match.group(1).strip()

        if not sql:
            match = re.search(
                r"\b(SELECT\s+.+?)(?:;|\]|```|$)", action, re.IGNORECASE | re.DOTALL
            )
            if match:
                sql = match.group(1).strip()

        if sql:
            sql = self._clean_sql_query(sql)

        return sql

    def _clean_sql_query(self, sql: str) -> str:
        if not sql:
            return sql

        sql = sql.rstrip(";").rstrip("]").strip()
        sql = re.sub(r"^```\w*\s*", "", sql)
        sql = re.sub(r"\s*```$", "", sql)
        sql = re.sub(r"\s+", " ", sql).strip()

        try:
            parsed = sqlparse.parse(sql)
            if parsed and len(parsed) > 0:
                stmt = parsed[0]
                stmt_type = stmt.get_type()

                if stmt_type in ("SELECT", "INSERT", "UPDATE", "DELETE", "UNKNOWN"):
                    sql = sqlparse.format(
                        sql, reindent=False, keyword_case="upper", strip_whitespace=True
                    )
        except Exception:
            pass

        return sql

    def _validate_sql_clauses(self, sql: str) -> Dict[str, Any]:
        result = {"valid": True, "errors": [], "warnings": []}

        try:
            parsed = sqlparse.parse(sql)
            if not parsed or len(parsed) == 0:
                result["valid"] = False
                result["errors"].append("Could not parse SQL statement")
                return result

            sql_upper = sql.upper()

            dangerous_keywords = ["DROP", "DELETE", "TRUNCATE", "ALTER", "CREATE"]
            for keyword in dangerous_keywords:
                if keyword in sql_upper:
                    result["valid"] = False
                    result["errors"].append(f"Dangerous operation: {keyword}")
                    return result

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

            if re.search(r"\b(ILIKE|LIKE)\b", sql_upper):
                result["valid"] = False
                result["errors"].append(
                    "Do NOT use ILIKE or LIKE. Use exact values with = or IN operators."
                )

            # Validate column names against cached schema
            if self._schema_cache:
                col_refs = re.findall(
                    r'\b([a-z_][a-z0-9_]*)\.([a-z_][a-z0-9_]*)\b', sql.lower()
                )
                for table_ref, col_ref in col_refs:
                    # Resolve table aliases from FROM/JOIN clauses
                    alias_pattern = rf'\b(?:FROM|JOIN)\s+([a-z_][a-z0-9_]*)\s+(?:AS\s+)?{re.escape(table_ref)}\b'
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
                                if suggestions else ""
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
