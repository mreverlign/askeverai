from typing import Dict, Any, List, Optional, Tuple
from llm_client import LLMClient
from database_tools import DatabaseTools, SchemaContextManager
from rag_metadata_embedder_focused import FocusedColumnEmbedder
from date_handler import DateHandler
from config import Config
import re
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
        embedder: FocusedColumnEmbedder,
    ):
        self.llm_client = llm_client
        self.db_tools = db_tools
        self.schema_manager = SchemaContextManager(db_tools)
        self.embedder = embedder
        self.date_handler = DateHandler(db_tools)
        self.conversation_history = []
        self.max_iterations = Config.MAX_AGENT_ITERATIONS

        logger.info("✅ Enhanced RAG ReAct Agent initialized")
        logger.info("✅ DateHandler initialized")

    def _extract_relevant_context(self, query: str, top_k: int = 10) -> Dict[str, Any]:

        logger.info(f"🔍 Extracting context for query: {query}")

        # Extract table names from query (for targeted relationship search)
        query_lower = query.lower()
        query_words = re.findall(r"\b\w+\b", query_lower)

        # Step 1: Search data model for table/column structure
        datamodel_results = self.embedder.search_datamodel(query, top_k=top_k)
        logger.info(f"📊 Data Model: Found {len(datamodel_results)} matches")

        # Step 2: Search metadata for column descriptions
        metadata_results = self.embedder.search_metadata(query, top_k=top_k)
        logger.info(f"📋 Metadata: Found {len(metadata_results)} matches")

        # Step 3: Enhanced relationship search
        # Try multiple relationship queries for better coverage
        relationship_queries = [
            query,  # Original query
            f"join {query}",  # Join-specific
            f"relationship {query}",  # Relationship-specific
        ]

        # Add specific table join queries if we detect table names
        detected_tables = self._detect_table_names(
            query, metadata_results + datamodel_results
        )
        for table in detected_tables:
            relationship_queries.append(f"join {table}")
            relationship_queries.append(f"{table} relationship")

        # Search relationships with multiple queries
        all_relationship_results = []
        seen_relationships = set()

        for rel_query in relationship_queries[:3]:  # Limit to avoid too many searches
            rel_results = self.embedder.search_relationships(rel_query, top_k=top_k)

            for result in rel_results:
                # Create unique key to avoid duplicates
                rel_key = f"{result.get('primary_table', '')}_{result.get('foreign_table', '')}"
                if rel_key not in seen_relationships:
                    seen_relationships.add(rel_key)
                    all_relationship_results.append(result)

        logger.info(
            f"🔗 Relationships: Found {len(all_relationship_results)} unique matches"
        )

        # Extract relevant information
        relevant_tables = set()
        relevant_columns = {}
        relationships = []

        # Process data model results
        for result in datamodel_results:
            for key in result.keys():
                if key.startswith(("Dim_", "Fact_", "dim_", "fact_")) or "_" in key:
                    table_name = key.lower()
                    if table_name not in ["source", "row_id"]:
                        relevant_tables.add(table_name)

        # Process metadata results
        for result in metadata_results:
            table = result.get("table_name", "").strip()
            column = result.get("column_name", "").strip()
            description = result.get("description", "")
            example = result.get("example", "")

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
                            "example": example,
                            "hybrid_score": result.get("hybrid_score", 0),
                            "bm25_score": result.get("bm25_score", 0),
                            "semantic_score": result.get("semantic_score", 0),
                        }
                    )

        # Process relationship results - ENHANCED
        for result in all_relationship_results:
            primary_table = result.get("primary_table", "").strip()
            foreign_table = result.get("foreign_table", "").strip()
            primary_key = result.get("primary_key", "").strip()
            foreign_key = result.get("foreign_key", "").strip()
            rel_type = result.get("relationship_type", "")

            if primary_table and foreign_table:
                primary_table_lower = primary_table.lower()
                foreign_table_lower = foreign_table.lower()

                relevant_tables.add(primary_table_lower)
                relevant_tables.add(foreign_table_lower)

                # Create fully qualified join condition
                join_condition = ""
                if primary_key and foreign_key:
                    join_condition = f"{primary_table_lower}.{primary_key.lower()} = {foreign_table_lower}.{foreign_key.lower()}"

                relationship = {
                    "primary_table": primary_table_lower,
                    "foreign_table": foreign_table_lower,
                    "primary_key": primary_key.lower() if primary_key else "",
                    "foreign_key": foreign_key.lower() if foreign_key else "",
                    "join_condition": join_condition,
                    "relationship_type": rel_type,
                    "from": primary_table_lower,
                    "to": foreign_table_lower,
                    "hybrid_score": result.get("hybrid_score", 0),
                    "bm25_score": result.get("bm25_score", 0),
                    "semantic_score": result.get("semantic_score", 0),
                }

                relationships.append(relationship)

        # Sort relationships by hybrid score
        relationships.sort(key=lambda x: x.get("hybrid_score", 0), reverse=True)

        context = {
            "relevant_tables": list(relevant_tables),
            "relevant_columns": relevant_columns,
            "relationships": relationships,
            "datamodel_results": datamodel_results[:10],
            "metadata_results": metadata_results[:10],
            "relationship_results": all_relationship_results[:10],
        }

        logger.info(f"✅ Context extracted:")
        logger.info(f"   - Tables: {len(relevant_tables)}")
        logger.info(f"   - Relationships: {len(relationships)}")
        logger.info(f"   - Top tables: {list(relevant_tables)[:5]}")

        return context

    def _detect_table_names(self, query: str, search_results: List[Dict]) -> List[str]:

        tables = set()

        # Common table prefixes
        table_prefixes = ["dim_", "fact_", "Dim_", "Fact_"]

        # Extract from search results
        for result in search_results:
            table = result.get("table_name", "")
            if table:
                tables.add(table.lower())

            primary_table = result.get("primary_table", "")
            if primary_table:
                tables.add(primary_table.lower())

            foreign_table = result.get("foreign_table", "")
            if foreign_table:
                tables.add(foreign_table.lower())

        return list(tables)

    def _extract_example_values(self, example_string: str) -> List[str]:
        """
        Extract individual values from example column in metadata.
        Example input: "CONF68420, CONF67658, INC95769"
        Returns: ["CONF68420", "CONF67658", "INC95769"]
        """
        if not example_string or str(example_string).strip() in ["", "nan", "none"]:
            return []

        # Split by comma and clean each value
        values = [v.strip() for v in str(example_string).split(",")]
        # Remove empty values
        values = [v for v in values if v and v.lower() not in ["nan", "none", ""]]
        return values

    def _get_examples_from_metadata(
        self, context: Dict[str, Any]
    ) -> Dict[str, List[str]]:
        """
        Build a lookup of column -> example values from metadata results.
        Returns dict like: {'transactiontypename': ['Quotation', 'Sales Order', 'Invoice']}
        """
        examples_by_column = {}

        for result in context.get("metadata_results", []):
            column = result.get("column_name", "").strip().lower()
            example = result.get("example", "")

            if column and example and str(example).strip() not in ["", "nan", "none"]:
                example_values = self._extract_example_values(example)
                if example_values:
                    if column not in examples_by_column:
                        examples_by_column[column] = []
                    examples_by_column[column].extend(example_values)

        # Remove duplicates while preserving order and case
        for column in examples_by_column:
            seen = set()
            unique_values = []
            for val in examples_by_column[column]:
                val_lower = val.lower()
                if val_lower not in seen:
                    seen.add(val_lower)
                    unique_values.append(val)
            examples_by_column[column] = unique_values

        return examples_by_column

    def _format_rag_context(
        self, context: Dict[str, Any], include_schema: bool = True
    ) -> str:

        parts = []

        parts.append("## 🔍 RAG HYBRID SEARCH RESULTS (BM25 + Semantic Search):")
        parts.append("")
        # Show search weights
        parts.append(f"**Search Configuration:**")
        parts.append(f"- BM25 Weight: {self.embedder.bm25_weight} (keyword matching)")
        parts.append(
            f"- Semantic Weight: {self.embedder.semantic_weight} (conceptual similarity)"
        )
        parts.append("")

        # CRITICAL: Add actual database schema for top relevant tables
        if include_schema and context.get("relevant_tables"):
            parts.append("### 🗂️ ACTUAL DATABASE SCHEMA (Most Relevant Tables)")
            parts.append(
                "**IMPORTANT: Use these EXACT column names in your SQL queries**"
            )
            parts.append("")

            # Get schema for top 3-5 most relevant tables
            top_tables = list(context["relevant_tables"])[:5]

            try:
                schema_result = self.db_tools.sql_db_schema(top_tables)

                if schema_result["success"]:
                    for table_name, schema_info in schema_result["schemas"].items():
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
                                    f"   - `{fk['column']}` → `{fk['references_table']}.{fk['references_column']}`"
                                )

                        parts.append(f"Row Count: {schema_info['row_count']:,}")
                        parts.append("")
                else:
                    logger.warning(
                        f"Could not load schema: {schema_result.get('error')}"
                    )
                    parts.append(
                        f"⚠️ Schema loading skipped (will use sql_db_schema action instead)"
                    )
                    parts.append("")
            except Exception as e:
                logger.error(f"Error loading schema in RAG context: {e}")
                parts.append(
                    f"⚠️ Schema loading skipped (will use sql_db_schema action instead)"
                )
                parts.append("")

            parts.append("---")
            parts.append("")

        # CRITICAL: Relationships FIRST (for join conditions)
        parts.append("### 🔗 STEP 1: RELATIONSHIPS - JOIN CONDITIONS (MOST IMPORTANT)")
        parts.append("**Use these exact join conditions in your SQL queries:**")
        parts.append("")

        if context["relationships"]:
            for i, rel in enumerate(context["relationships"][:8], 1):
                parts.append(f"**Relationship {i}:**")
                parts.append(f"   Primary Table: `{rel['primary_table']}`")
                parts.append(f"   Primary Key: `{rel['primary_key']}`")
                parts.append(f"   Foreign Table: `{rel['foreign_table']}`")
                parts.append(f"   Foreign Key: `{rel['foreign_key']}`")

                # CRITICAL: Fully qualified join condition
                if rel["join_condition"]:
                    parts.append(f"   **EXACT JOIN SYNTAX:** `{rel['join_condition']}`")
                    parts.append(
                        f"   **SQL:** `JOIN {rel['foreign_table']} ON {rel['join_condition']}`"
                    )

                parts.append(f"   Relationship Type: {rel['relationship_type']}")
                parts.append(
                    f"   Scores: Hybrid={rel['hybrid_score']:.3f}, BM25={rel['bm25_score']:.3f}, Semantic={rel['semantic_score']:.3f}"
                )
                parts.append("")
        else:
            parts.append("⚠️ No relationships found. Query may not require joins.")
            parts.append("")

        # Metadata results (column information)
        parts.append("### 📋 STEP 2: METADATA - Column Information")
        parts.append("")

        if context["metadata_results"]:
            for i, result in enumerate(context["metadata_results"][:8], 1):
                table = result.get("table_name", "")
                column = result.get("column_name", "")
                desc = result.get("description", "")
                example = result.get("example", "")

                parts.append(f"**Column {i}:**")
                parts.append(f"   Table: `{table}`")
                parts.append(f"   Column: `{column}`")
                parts.append(f"   Full Name: `{table}.{column}`")

                if desc:
                    parts.append(f"   Description: {desc}")

                if (
                    example
                    and str(example).strip()
                    and str(example) not in ["nan", "none", ""]
                ):
                    parts.append(f"   **Example Values: {example}**")
                    parts.append(
                        f"   💡 TIP: Use these exact values in WHERE clauses (e.g., WHERE {column} = 'value' or WHERE {column} IN ('val1', 'val2'))"
                    )

                parts.append(
                    f"   Scores: Hybrid={result.get('hybrid_score', 0):.3f}, BM25={result.get('bm25_score', 0):.3f}, Semantic={result.get('semantic_score', 0):.3f}"
                )
                parts.append("")
        else:
            parts.append("No metadata matches found.")
            parts.append("")

        # Extract and display available example values with EXACT casing
        examples_by_column = self._get_examples_from_metadata(context)
        if examples_by_column:
            parts.append(
                "### 💎 AVAILABLE EXAMPLE VALUES (Use EXACT Case - ILIKE/LIKE PROHIBITED)"
            )
            parts.append(
                "**CRITICAL: Use these EXACT values with proper casing. NEVER use ILIKE or LIKE!**"
            )
            parts.append("")
            for column, example_values in sorted(examples_by_column.items())[:10]:
                if example_values:
                    # Format values as SQL IN clause
                    formatted_values = "', '".join(
                        example_values[:8]
                    )  # Show up to 8 examples
                    parts.append(f"**Column: `{column}`**")
                    parts.append(
                        f"   Available Values: {', '.join(example_values[:8])}"
                    )
                    parts.append(
                        f"   SQL Example: `WHERE {column} = '{example_values[0]}'`"
                    )
                    if len(example_values) > 1:
                        parts.append(
                            f"   SQL Multiple: `WHERE {column} IN ('{formatted_values}')`"
                        )
                    parts.append("")
            parts.append(
                "🚫 **ILIKE and LIKE are FORBIDDEN - Use exact values with = or IN operators only**"
            )
            parts.append("")

        # Data model results
        parts.append("### 📊 STEP 3: DATA MODEL - Table Structure")
        parts.append("")

        if context["datamodel_results"]:
            for i, result in enumerate(context["datamodel_results"][:5], 1):
                parts.append(
                    f"**Data Model {i}:** (score: {result.get('hybrid_score', 0):.3f})"
                )

                # Show table names from data model
                for key, value in result.items():
                    if key not in [
                        "source",
                        "row_id",
                        "score",
                        "distance",
                        "text",
                        "hybrid_score",
                        "bm25_score",
                        "semantic_score",
                    ]:
                        if value and str(value).strip() and str(value) != "nan":
                            if key.startswith(("Dim_", "Fact_", "dim_", "fact_")):
                                parts.append(f"   Table: `{key}`")
                parts.append("")

        # Summary of relevant tables
        parts.append("### 📌 RELEVANT TABLES SUMMARY:")
        if context["relevant_tables"]:
            for table in sorted(context["relevant_tables"])[:10]:
                parts.append(f"   - `{table}`")
        parts.append("")

        # Critical instructions for SQL generation
        parts.append("### ⚠️ CRITICAL SQL GENERATION INSTRUCTIONS:")
        parts.append(
            "1. **ALWAYS check '💎 AVAILABLE EXAMPLE VALUES' section** - Use EXACT casing, ILIKE/LIKE FORBIDDEN!"
        )
        parts.append("2. **ALWAYS use the exact join conditions provided above**")
        parts.append(
            "3. **Use fully qualified column names** (e.g., `dim_client.clientid`, not just `clientid`)"
        )
        parts.append("4. **Reference the relationship section** when joining tables")
        parts.append(
            "5. **GROUP BY is MANDATORY** when using aggregates (SUM, COUNT, AVG) with non-aggregate columns"
        )
        parts.append("6. **Verify table names** from the relevant tables summary")
        parts.append("")

        return "\n".join(parts)

    def _create_react_prompt(
        self,
        user_query: str,
        rag_context: str,
        iteration: int,
        previous_steps: List[Dict],
    ) -> str:

        # Extract and enhance query with date information
        date_instructions = self.date_handler.create_dateid_replacement_instructions(
            user_query
        )

        # Build previous steps context
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

## 🔢 HANDLING MULTIPLE QUERIES (CRITICAL):

**IMPORTANT: If the user asks for multiple separate analyses/tables, generate MULTIPLE separate queries!**

### When to Generate Multiple Queries:

1. **Explicit Multiple Requests:**
   - "Show me three tables" → Generate 3 separate queries
   - "Display sales by client AND sales by product" → Generate 2 queries
   - "Give me top 10 customers, top 10 products, and top 10 partners" → Generate 3 queries
   - "Show revenue by month and also by quarter" → Generate 2 queries

2. **Multiple Dimensions/Groupings:**
   - "Break down by X and also by Y" → Generate 2 queries
   - "Compare A versus B" → Generate 2 queries

3. **Different Metrics:**
   - "Show sales and also show quantities" → Generate 2 queries (if they need different logic)

### How to Generate Multiple Queries:

**Format: Use multiple sql_db_query[] actions in a SINGLE Action block:**

```
Action: sql_db_query[SELECT ... first query ...]
sql_db_query[SELECT ... second query ...]
sql_db_query[SELECT ... third query ...]
```
### When NOT to Use Multiple Queries:

- User wants a SINGLE combined view (use UNION, JOINs, or subqueries instead)
- Queries share the same grouping/dimension
- User asks for "comparison in one table"

## 🚨 CRITICAL RULES - READ FIRST:

1. **DATES - MOST CRITICAL**: ALWAYS use f.dateid in YYYYMMDD format, NEVER use d.date
   
   🚨 **FORBIDDEN - WILL FAIL - NEVER USE THESE:**
   - ❌ WHERE d.date = '2025-11-25'        (WRONG - will get wrong results)
   - ❌ WHERE d.date = ANY format         (WRONG - column doesn't work)
   - ❌ WHERE f.created_date, close_date, ship_date, delivery_date
   - ❌ DATE(d.date) = '2025-11-25'
   - ❌ String dates with quotes like '2025-01-12'
   
   ✅ **ALWAYS USE - ONLY VALID PATTERN:**
   - WHERE f.dateid = YYYYMMDD            (INTEGER DateID in YYYYMMDD format)
   - Example: WHERE f.dateid = 20251125   (November 25, 2025)
   - Example: WHERE f.dateid = 20260127   (January 27, 2026)
   - Ranges: WHERE f.dateid BETWEEN 20251101 AND 20251130
   - Lists: WHERE f.dateid IN (20251125, 20251126, 20251127)

2. **PRODUCT NAMES**: When user asks for products:
   - ✅ ALWAYS SELECT ONLY: `itemid` (product ID)
   - `itemid` = Unique product identifier (e.g., "PROD-12345")

3. **TRANSACTION TYPES**: "shipped" or "delivered" means `transactiontypeid = 1000` (Invoice)

4. **DATA QUALITY**: Always apply positive amounts, exclude tariffs, use COUNT(DISTINCT)

## BUSINESS TERMINOLOGY & LOGIC:

### Transaction Type Interpretation (CRITICAL):
The **transactiontypename** field indicates the stage of a sale:

- "Invoice" → TransactionTypeID = 1000
- "Quotation" → TransactionTypeID = 1001
- "Sales Order" → TransactionTypeID = 1002
- "Credit Memo" → TransactionTypeID = 1004
- "na" → TransactionTypeID = -1

1. **'Quote'** → Initial proposal (quotation)
2. **'Sales Order'** → Confirmed order ,orders placed but not yet shipped 
3. **'Invoice'** → **ACTUAL SHIPMENT/DELIVERY** ← Use this for "shipped" queries,revenue
4. **'Credit Memo'** → Returns/adjustments (reversed shipments), NOT actual sales, refund

**User Query Mapping:**
- "shipped", "shipment", "delivered", "delivery" → Filter: `transactiontypename = 'Invoice'`

- "quotes", "proposals" → Filter: `transactiontypename = 'Quotation'`
- "orders" → Clarify if they mean 'Sales Order' or 'Invoice'
- "returns", "refunds" → Filter: `transactiontypename = 'Credit Memo'`


### Data Quality Rules (ALWAYS APPLY):

1. **Positive Amounts Only:**
   ```sql
   WHERE f."amount" > 0
   ```

2. **Exclude Tariff Line Items:**
   ```sql
   WHERE f."itemid" NOT IN (
       'Subtotal for Tariff Recovery Fee', 
       'Subtotal for Canadian Tariff Credit'
   )
   ```

3. **Active Records Only** (for specific tables):
   - `dim_end_user`: `WHERE eu."active_flag" = 1`
   - `dim_specifier1`: `WHERE sp."active_flag" = 1`

4. **Use COUNT(DISTINCT) for Accurate Counting:**
   ```sql
   -- ✅ CORRECT - Prevents duplicate counting
   COUNT(DISTINCT f."transactionid") as transactioncount
   COUNT(DISTINCT c."clientid") as uniqueclients
   COUNT(DISTINCT i."itemid") as uniqueproducts

   -- ❌ WRONG - May count duplicates due to JOINs
   COUNT(*) as transactioncount
   COUNT(f."transactionid") as transactioncount
   ```

5. **ALWAYS Use GROUP BY with Aggregate Functions (CRITICAL):**

   **RULE: When you SELECT any aggregate function (SUM, COUNT, AVG, MIN, MAX) along with non-aggregate columns, you MUST include GROUP BY with ALL non-aggregate columns.**

   -- ✅ CORRECT - GROUP BY includes all non-aggregate columns
   -- ✅ CORRECT - Single aggregate only (no GROUP BY needed)
   SELECT SUM(f.amount) as total_amount
   FROM fact_transaction_detail f
   WHERE f.dateid >= '20240101'

   -- ✅ CORRECT - Aggregates in subquery with GROUP BY
   SELECT
       client_totals.clientname,
       client_totals.total_amount
   FROM (
       SELECT
           c.clientname,
           SUM(f.amount) as total_amount
       FROM fact_transaction_detail f
       JOIN dim_client c ON f.clientid = c.clientid
       GROUP BY c.clientname
   ) client_totals
   WHERE client_totals.total_amount > 10000

   -- ❌ WRONG - Aggregate with non-aggregate column but NO GROUP BY
   SELECT
       c.clientname,
       SUM(f.amount) as total_amount
   FROM fact_transaction_detail f
   JOIN dim_client c ON f.clientid = c.clientid
   -- ERROR: Missing GROUP BY c.clientname

   -- ❌ WRONG - GROUP BY missing some columns
   SELECT
       c.clientname,
       p.projectname,
       SUM(f.amount) as total_amount
   FROM fact_transaction_detail f
   JOIN dim_client c ON f.clientid = c.clientid
   JOIN dim_project p ON f.projectid = p.projectid
   GROUP BY c.clientname
   -- ERROR: Missing p.projectname in GROUP BY
   ```

   **Common Aggregate Functions that REQUIRE GROUP BY:**
   - `SUM(column)` - Must GROUP BY all other SELECT columns
   - `COUNT(column)` or `COUNT(DISTINCT column)` - Must GROUP BY all other SELECT columns
   - `AVG(column)` - Must GROUP BY all other SELECT columns
   - `MIN(column)`, `MAX(column)` - Must GROUP BY all other SELECT columns
   - `STRING_AGG(column, delimiter)` - Must GROUP BY all other SELECT columns

   **When GROUP BY is NOT needed:**
   - Only selecting aggregate functions, no regular columns
   - Using window functions with OVER clause (uses PARTITION BY instead)
   - SELECT with only constants or literals

### 🚨 CRITICAL DATA QUALITY RULES (ALWAYS APPLY):

1. **Positive Amounts Only:**
   ```sql
   WHERE f.amount > 0
   ```

2. **Exclude Tariff Line Items:**
   ```sql
   WHERE f.itemid NOT IN (
       'Subtotal for Tariff Recovery Fee',
       'Subtotal for Canadian Tariff Credit'
   )
   ```

3. **Date Handling (CRITICAL - ONLY USE dateid, NEVER raw dates):**

   🚨 **THIS IS THE #1 MISTAKE - DO NOT MAKE THIS ERROR:**
   
   ❌ **FORBIDDEN - WILL FAIL:**
   ```sql
   WHERE d.date = '2025-01-12'      -- WRONG! This syntax fails
   WHERE f.created_date = '2025-01-12'
   WHERE f.ship_date = '2025-01-12'
   WHERE DATE(d.date) = '2025-01-12'
   ```

   ✅ **ALWAYS USE DateID in YYYYMMDD FORMAT (as INTEGER):**
   ```sql
   -- DateID is in YYYYMMDD format (e.g., 20250112 = January 12, 2025)
   -- IMPORTANT: YYYYMMDD means YYYY-MM-DD, NOT YYYY-DD-MM
   
   -- Pattern 1: Use DateID directly (INTEGER only, no quotes)
   WHERE f.dateid = 20250112        -- January 12, 2025 in YYYYMMDD format
   
   -- Pattern 2: DateID range
   WHERE f.dateid BETWEEN 20250101 AND 20250131  -- All of January 2025
   
   -- Pattern 3: DateID list
   WHERE f.dateid IN (20250112, 20250113, 20250114)
   
   -- Pattern 4: If you need to JOIN to dim_date for readable dates
   SELECT
       d.date,           -- NOW you can get the readable date
       SUM(f.amount) as total
   FROM fact_transaction_detail f
   JOIN dim_date d ON f.dateid = d.dateid
   WHERE f.dateid = 12345           -- Still use DateID in WHERE!
   ```

   🚨 **COLUMN NAMES THAT DO NOT EXIST (never use):**
   - ❌ close_date, closedate, closed_date
   - ❌ created_date, createddate, creation_date
   - ❌ ship_date, shipdate, shipping_date, delivery_date
   - ❌ expected_close, expected_date, forecast_date
   - ❌ Any date column with spaces or special characters

   ✅ **ONLY VALID DATE COLUMNS:**
   - `f.dateid` - Use in WHERE and JOIN (INTEGER type)
   - `f.yearid` - Use for year filtering (can be TEXT or INTEGER)
   - `d.date` - ONLY after JOINing to dim_date, for display/SELECT

4. **Use Window Functions for Aggregations with DISTINCT (PostgreSQL):**
   ```sql
   -- ✅ CORRECT - PostgreSQL syntax with window functions
   SELECT DISTINCT
       dimension_column,
       SUM(f.amount) OVER (PARTITION BY dimension_column) AS total
   FROM fact_transaction_detail f
   JOIN dimension d ON ...
   WHERE [filters above]
   ORDER BY total DESC
   

   -- ❌ WRONG - SQL Server syntax (DO NOT USE)
   SELECT DISTINCT TOP 20 ...  -- This will FAIL in PostgreSQL

   -- ❌ WRONG - May have duplicates
   SELECT
       dimension_column,
       SUM(f.amount) as total
   FROM fact_transaction_detail f
   JOIN dimension d ON ...
   GROUP BY dimension_column
   
   ```

5. **Active Records Only** (for specific tables):
   - `dim_end_user`: `WHERE eu.active_flag = 1`
   - `dim_specifier1`: `WHERE sp.active_flag = 1`

6. **In order to get categoryname or subcategoryname, you must JOIN the appropriate dimension tables**:
    for categoryname use `dim_item_category`, for subcategoryname use `dim_subcategory_item`
    to get transactions or sales by category or subcategory.
    from `fact_transaction_detail` itemid JOINs to `dim_item` skuid, which then JOINs to `dim_item_category` categoryid from subcategoryid in `dim_subcategory_item`.**

**Iteration {iteration}/{self.max_iterations}**
        
### IMPORTANT NOTE:
 The ACTUAL column names and relationships
are provided in the "ACTUAL DATABASE SCHEMA" section that appears at the TOP of this prompt.
ALWAYS refer to the ACTUAL DATABASE SCHEMA for correct column names .

### 📊 DIMENSION TABLES REFERENCE (For Join Context)

**Product Dimensions:**
- **dim_item** (connects via `fact.itemid` = `dim_item.skuid`)
  - `skuid` - Unique product identifier in dim_item (used for JOIN)
  - `itemid` - Product ID/SKU (use for display)
  - Configuration: `option_1`, `option_2`, `option_3` and their values
  - Links to: `brandpartnerid`, `subcategoryid`

  🚨 **CRITICAL - Product Rules:**
  - `itemid` = Unique product identifier (e.g., "PROD-12345")
  - Return ONLY itemid for products

  ✅ **When user asks for products:**
  ```sql
  -- SELECT ONLY itemid
  SELECT
      i.itemid,           -- Product ID
      SUM(f.amount) as total_sales
  FROM fact_transaction_detail f
  JOIN dim_item i ON f.itemid = i.skuid
  GROUP BY i.itemid
  ```
  
- **dim_item_category** (connects via `categoryid` ↔ `dim_item.categoryid` ↔ `dim_subcategory_item.subcategoryid,categoryid` ↔ `dim_item.subcategoryid`)
  - `productcategoryname`
  
- **dim_subcategory_item** (connects via `subcategoryid` ↔ `dim_item.subcategoryid`)
  - `productsubcategoryname`
  - Links to: `categoryid`

- **dim_brand_partner_item** (connects via `brandpartnerid` ↔ `dim_item.brandpartnerid`)
  - `brandpartner`

**Customer & Partner Dimensions:**
- **dim_client** (connects via `clientid` ↔ `fact.clientid`)
  - `clientname`, `last_modified`
  - Links to: `clientcategoryid` (implicitly via fact table)

- **dim_client_category** (connects via `clientcategoryid` ↔ `fact.clientcategoryid`)
  - `clientcategoryname`

- **dim_partner** (connects via `partnerid` ↔ `fact.partnerid`)
  - Partner details: `partnercode`, `partnername`, `companyname`, `keyaccount`
  - Location: `city`, `state`, `country`
  - Addresses: `billingaddress`, `defaultaddress`, `shippingaddress`
  - Links to: `specifiertypeid`, `specifiersubtypeid`, `endusertypeid`

- **dim_end_user** (connects via `partnerid`↔ `fact.enduserid`)
  - `endusername`, `active_flag`
  - Links to: `partnerid`

- **dim_end_user_type** (connects via `endusertypeid` ↔ `fact.endusertypeid`)
  - `endusertypename`

**Specifier Dimensions:**
- **dim_specifier1** (connects via `partnerid` ↔ `fact.specifier1id`)
  - `specifier1name`, `active_flag`
  - Location: `city`, `state`
  - Links to: `partnerid`

- **dim_specifier2** (connects via `specifier2id` ↔ `fact.specifier2id`)
  - `specifier2name`

- **dim_specifier_type** (connects via `specifiertypeid` ↔ `fact.specifiertypeid`)
  - `specifiertypename`

- **dim_specifier_sub_type** (connects via `specifiersubtypeid` ↔ `fact.specifiersubtypeid`)
  - `specifiersubtypename`

**Project & Sales Dimensions:**
- **dim_project** (connects via `projectid` ↔ `fact.projectid`)
  - `projectname`
  - Links to: `projectmanagerid`

- **dim_project_type** (connects via `projecttypeid` ↔ `fact.projecttypeid`)
  - `projecttypename`

- **dim_project_manager** (connects via `projectmanagerid` ↔ `fact.projectmanagerid`)
  - `projectmanagername`

- **dim_sales_rep** (connects via `salesrepid` ↔ `fact.salesrepid`)
  - `salesrepname`

- **dim_design_firm** (connects via `designfirmid` ↔ `fact.designfirmid`)
  - `designfirmname`

**Transaction Dimensions:**
- **dim_transaction_type** (connects via `transactiontypeid` ↔ `fact.transactiontypeid`)
  - `transactiontypename` - Values: 'Quote', 'Sales Order', 'Invoice', 'Credit Memo'

- **dim_transaction_status** (connects via `transactionstatusid` ↔ `fact.transactionstatusid`)
  - `transactionstatusname`

- **dim_dealer_alignment** (connects via `dealeralignmentid` ↔ `fact.dealeralignmentid`)
  - `dealeralignmentname`

- **dim_vertical_market** (connects via `verticalmarketid` ↔ `fact.verticalmarketid`)
  - `verticalmarketname`

**Time Dimension:**
- **dim_date** (connects via `dateid` ↔ `fact.dateid`)
  - `date`, `monthid`, `weekid`, `yearid`


**IMPORTANT:** Always verify column names in "ACTUAL DATABASE SCHEMA" section above before writing SQL.

### CRITICAL INSTRUCTIONS:
1. **USE THE EXACT COLUMN NAMES** from the "ACTUAL DATABASE SCHEMA" section above
2. **DO NOT GUESS** column names - they are provided in the schema
3. **USE FULLY QUALIFIED** table.column names in your SQL
4. **CHECK THE FOREIGN KEYS** section for correct join conditions
5. If you need more schema details, use: `sql_db_schema[table1, table2]`
6. **ALWAYS VALIDATE** your SQL with `sql_db_query_checker` before executing

### 🔤 FILTERING WITH VALUES (CRITICAL):

**PRIORITY 1: Use Example Values from "AVAILABLE EXAMPLE VALUES" Section (MOST IMPORTANT)**

**ALWAYS check the "💎 AVAILABLE EXAMPLE VALUES" section above FIRST!**

If example values are listed for a column:
- ✅ **Use the EXACT casing** shown in the examples
- ✅ **Use = or IN operators** (NOT ILIKE)
- ✅ **Copy the values exactly** as they appear

```sql
-- ✅ BEST - Using exact values with proper casing from AVAILABLE EXAMPLE VALUES
-- (Check the "💎 AVAILABLE EXAMPLE VALUES" section above for these!)
WHERE transactiontypename IN ('Quotation', 'Sales Order', 'Invoice')
WHERE brandpartner = 'Fritz Hansen'  -- Exact case from examples
WHERE state IN ('VA', 'IL', 'CA')
WHERE transactionstatusname = 'Pending Billing/Partially Fulfilled'

-- ❌ WRONG - Using ILIKE/LIKE when exact values are available
WHERE transactiontypename ILIKE '%quotation%'  -- ❌ FORBIDDEN!
WHERE brandpartner ILIKE '%fritz%'              -- ❌ FORBIDDEN!
WHERE transactiontypename LIKE '%Quotation%'   -- ❌ FORBIDDEN!

-- ❌ WRONG - Wrong casing (database won't match)
WHERE transactiontypename = 'quotation'  -- Should be 'Quotation'
WHERE brandpartner = 'fritz hansen'      -- Should be 'Fritz Hansen'
```

**WHY THIS MATTERS:**
- Example values show the **EXACT case** as stored in the database
- Using exact values is **faster** (no pattern matching needed)
- Using exact values is **more accurate** (no false matches)
- **ILIKE/LIKE are completely FORBIDDEN** - Use exact values or LOWER() function instead!

**PRIORITY 2: Case-Insensitive Matching (ONLY when no examples available)**

⚠️ **CRITICAL: NEVER use ILIKE or LIKE - They are PROHIBITED!**

PostgreSQL is **case-sensitive** by default. When filtering by user-specified names and NO examples are provided in "AVAILABLE EXAMPLE VALUES":

**Use LOWER() function for case-insensitive matching:**
```sql
-- ✅ CORRECT - Case insensitive with LOWER()
WHERE LOWER(bp.brandpartner) = LOWER('Steelcase')
WHERE LOWER(c.clientname) = LOWER('Acme Corporation')
WHERE LOWER(i.productname) = LOWER('Office Chair')

-- ✅ CORRECT - Partial match with LOWER() and wildcards in value
WHERE LOWER(bp.brandpartner) = 'steelcase'  -- User value lowercase
WHERE LOWER(c.clientname) LIKE LOWER('%acme%')  -- For pattern matching ONLY if absolutely needed

-- ❌ PROHIBITED - NEVER use ILIKE
WHERE bp.brandpartner ILIKE '%steelcase%'  -- ❌ FORBIDDEN!
WHERE c.clientname ILIKE 'acme%'           -- ❌ FORBIDDEN!

-- ❌ WRONG - Case sensitive, will miss matches
WHERE bp.brandpartner = 'Steelcase'
WHERE c.clientname = 'ACME%'
```

**Decision Tree (Follow This Order):**
1. **Check "💎 AVAILABLE EXAMPLE VALUES" section above** - Are example values listed for this column?
   - YES → Use those EXACT values with = or IN (with proper casing!)
   - NO → Proceed to step 2
2. **Check "📋 STEP 2: METADATA" section** - Are example values shown inline?
   - YES → Use those exact values
   - NO → Proceed to step 3
3. **No examples available - use LOWER() function:**
   - For exact match → `WHERE LOWER(column) = LOWER('value')`
   - For partial match (only if necessary) → `WHERE LOWER(column) LIKE LOWER('%value%')`
   - **NEVER EVER use ILIKE or plain LIKE**

**Common columns requiring case-insensitive handling:**
- `brandpartner`, `brandpartner` - Brand names
- `clientname` - Client/customer names
- `productname`, `skuid` - Product names
- `partnername`,  - Partner names
- `projectname` - Project names
- `categoryname`, `subcategoryname` - Category names
- `endusername`, `specifier1name`, `specifier2name` - User/specifier names
- `city`, `state`, `country` - Location names

### ReAct Pattern:
1. **Thought**: Analyze what you need to do next. Consider:
   - What tables and columns are in the ACTUAL DATABASE SCHEMA section?
   - What join conditions are shown in the Foreign Keys?
   - Do I need to call sql_db_schema for more tables?

2. **Action**: Choose ONE action from the list below:
   - `sql_db_list_tables[]` - List all available tables
   - `sql_db_schema[table1, table2]` - Get schema for specific tables
   - `sql_db_query_checker[SELECT ...]` - Validate SQL syntax
   - `sql_db_query[SELECT ...]` - Execute final SQL query

3. **Observation**: (System will provide the result)

### CRITICAL: Action Format Examples
**CORRECT formats:**
```
Action: sql_db_query[SELECT * FROM dim_client LIMIT 10]
```
OR
```
Action: sql_db_query[
SELECT
    c.clientname,
    SUM(f.amount) as total_amount
FROM fact_transaction_detail f
JOIN dim_client c ON f.clientid = c.clientid
GROUP BY c.clientname
LIMIT 10
]
```

**WRONG format (do NOT use):**
```
Action: ```sql
SELECT * FROM dim_client
```
```

### ⚠️ BEFORE WRITING SQL:
1. Scroll up and check the "🗂️ ACTUAL DATABASE SCHEMA" section
2. Use ONLY the column names shown there
3. Check the "🔗 STEP 1: RELATIONSHIPS" section for join conditions
4. DO NOT use column names from the keyword map - those are just for guidance

### EXAMPLE WORKFLOWS:

**Example 1: "show me sales by customer"** (Single Query)
Thought: I need to query the fact_transaction_detail table and join with dim_client. Looking at the ACTUAL DATABASE SCHEMA section above, I can see the exact column names: fact_transaction_detail has clientid and amount columns, and dim_client has clientid and clientname.
Action: sql_db_query[SELECT c.clientname, SUM(f.amount) as total_sales FROM fact_transaction_detail f JOIN dim_client c ON f.clientid = c.clientid WHERE f.amount > 0 GROUP BY c.clientname ORDER BY total_sales DESC]

**Example 2: "Top 20 Projects by orders"** (Single Query)
Thought: For projects by orders/amount, I need dim_project joined with fact_transaction_detail. From the ACTUAL DATABASE SCHEMA section above, I can see: dim_project has projectid and projectname columns, fact_transaction_detail has projectid, amount, transactiontypeid, dateid, and itemid columns. From the RELATIONSHIPS section, I see: dim_project.projectid = fact_transaction_detail.projectid. I'll use window functions with DISTINCT, filter by transactiontypeid = 1001 (orders), exclude tariff items, and ensure amount > 0. Using PostgreSQL syntax with LIMIT when only asked as top 20 or something **not always**.
Action: sql_db_query[SELECT DISTINCT p.projectname, SUM(f.amount) OVER (PARTITION BY p.projectname) AS totalamount, PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY f.amount) OVER (PARTITION BY p.projectname) AS medianamount FROM fact_transaction_detail f JOIN dim_project p ON f.projectid = p.projectid WHERE f.transactiontypeid = 1001 AND f.dateid BETWEEN '20230101' AND '20251231' AND f.itemid NOT IN ('Subtotal for Tariff Recovery Fee', 'Subtotal for Canadian Tariff Credit') AND f.amount > 0 ORDER BY totalamount DESC ]

**Example 3: "show me three tables: top clients, top products, and top partners"** (MULTIPLE QUERIES)
Thought: User wants THREE separate tables, so I need to generate THREE separate queries - one for clients, one for products, and one for partners.
Action: sql_db_query[SELECT c.clientname, SUM(f.amount) as total FROM fact_transaction_detail f JOIN dim_client c ON f.clientid = c.clientid WHERE f.amount > 0 AND f.itemid NOT IN ('Subtotal for Tariff Recovery Fee', 'Subtotal for Canadian Tariff Credit') GROUP BY c.clientname ORDER BY total DESC LIMIT 10]
sql_db_query[SELECT i.productname, SUM(f.amount) as total FROM fact_transaction_detail f JOIN dim_item i ON f.itemid = i.skuid WHERE f.amount > 0 AND f.itemid NOT IN ('Subtotal for Tariff Recovery Fee', 'Subtotal for Canadian Tariff Credit') GROUP BY i.productname ORDER BY total DESC LIMIT 10]
sql_db_query[SELECT p.partnername, SUM(f.amount) as total FROM fact_transaction_detail f JOIN dim_partner p ON f.partnerid = p.partnerid WHERE f.amount > 0 AND f.itemid NOT IN ('Subtotal for Tariff Recovery Fee', 'Subtotal for Canadian Tariff Credit') GROUP BY p.partnername ORDER BY total DESC LIMIT 10]

**Example 4: "display sales by category AND sales by brand"** (MULTIPLE QUERIES)
Thought: User wants two separate analyses - one by category and one by brand. I need TWO separate queries.
Action: sql_db_query[SELECT cat.productcategoryname, SUM(f.amount) as total FROM fact_transaction_detail f JOIN dim_item i ON f.itemid = i.skuid JOIN dim_subcategory_item sub ON i.subcategoryid = sub.subcategoryid JOIN dim_item_category cat ON sub.categoryid = cat.categoryid WHERE f.amount > 0 GROUP BY cat.productcategoryname ORDER BY total DESC]
sql_db_query[SELECT b.brandpartner, SUM(f.amount) as total FROM fact_transaction_detail f JOIN dim_item i ON f.itemid = i.skuid JOIN dim_brand_partner_item b ON i.brandpartnerid = b.brandpartnerid WHERE f.amount > 0 GROUP BY b.brandpartner ORDER BY total DESC]

### Response Format:
Thought: [Your reasoning - reference the ACTUAL DATABASE SCHEMA section]
Action: [One of the available actions - MUST be in format: action_name[parameters]]

### REMEMBER:
- Column names are IN the schema above - DO NOT guess
- **Database is PostgreSQL** - use `LIMIT N` at END of query, NOT `TOP N`
- **NEVER use `SELECT DISTINCT TOP 20` - this is SQL Server syntax and will FAIL**
- Always use table.column format for clarity (e.g., `f.amount`, `p.projectname`)
- Use the DIMENSION TABLES REFERENCE section for join conditions
- For "orders" queries: ALWAYS use `transactiontypeid = 1001`
- For TOP N with aggregations: Use window functions with `OVER (PARTITION BY ...)` then `LIMIT N`
- Action MUST be in format: sql_db_query[SELECT ...] NOT in markdown code blocks
- **🔢 CRITICAL: If user asks for multiple tables/analyses, put MULTIPLE sql_db_query[] in ONE Action block**

Now, proceed with your Thought and Action:
"""

        return prompt

    def process_query(self, user_query: str) -> Dict[str, Any]:

        try:
            logger.info(f"\n{'='*80}")
            logger.info(f"🔍 Processing query: {user_query}")
            logger.info(f"{'='*80}\n")

            # Extract date context from query
            date_filters = self.date_handler.extract_date_filters(user_query)
            if date_filters["has_date_filter"]:
                logger.info("\n📅 Date Filters Extracted:")
                for date_str, date_id in date_filters.get("dateids", {}).items():
                    logger.info(f"   {date_str} → DateID: {date_id}")
                logger.info("")

            # Extract RAG context with improved relationship search
            rag_context_data = self._extract_relevant_context(user_query, top_k=10)
            rag_context_str = self._format_rag_context(rag_context_data)

            # Log the relationships found
            if rag_context_data["relationships"]:
                logger.info("\n🔗 Key Relationships Found:")
                for rel in rag_context_data["relationships"][:5]:
                    logger.info(
                        f"   {rel['primary_table']}.{rel['primary_key']} = {rel['foreign_table']}.{rel['foreign_key']}"
                    )
                logger.info("")

            # ReAct loop
            thought_action_log = []
            previous_steps = []
            final_sql = None
            final_results = None
            all_sql_queries = []
            all_query_results = []

            for iteration in range(1, self.max_iterations + 1):
                logger.info(f"\n--- Iteration {iteration}/{self.max_iterations} ---")

                # Create ReAct prompt
                prompt = self._create_react_prompt(
                    user_query, rag_context_str, iteration, previous_steps
                )

                # Get LLM response
                logger.info("💭 Sending prompt to LLM...")
                response = self.llm_client.generate(
                    prompt, temperature=0.0, max_tokens=4000
                )

                logger.info(f"📝 LLM Response:\n{response[:500]}...")

                # Extract thought
                thought = self._extract_section(response, "Thought")
                if thought:
                    logger.info(f"💭 Thought: {thought[:200]}...")
                    thought_action_log.append({"type": "thought", "content": thought})
                    previous_steps.append({"type": "thought", "content": thought})

                # Extract action
                action = self._extract_section(response, "Action")
                if action:
                    logger.info(f"⚡ Action: {action[:200]}...")
                    thought_action_log.append({"type": "action", "content": action})
                    previous_steps.append({"type": "action", "content": action})

                    # Execute action and store results
                    observation = self._execute_action(action)
                    logger.info(f"👁️ Observation: {observation[:200]}...")
                    thought_action_log.append(
                        {"type": "observation", "content": observation}
                    )
                    previous_steps.append(
                        {"type": "observation", "content": observation}
                    )

                    # Check if we have SQL queries
                    if (
                        "sql_db_query[" in action.lower()
                        and "row" in observation.lower()
                    ):
                        # Extract all SQL queries from this action
                        queries = self._extract_multiple_sql_queries(action)
                        all_sql_queries.extend(queries)

                        # Parse observation to extract all query results
                        if "Executed" in observation and "quer" in observation:
                            # Multiple queries executed
                            query_blocks = observation.split("=" * 60)
                            for block in query_blocks[1:]:  # Skip first block (header)
                                if "Query" in block and "of" in block:
                                    query_result = {"raw_text": block.strip()}
                                    # Extract row count if present
                                    rows_match = re.search(r"Rows:\s*(\d+)", block)
                                    if rows_match:
                                        query_result["row_count"] = int(
                                            rows_match.group(1)
                                        )
                                    all_query_results.append(query_result)

                        final_sql = self._extract_sql_from_action(action)
                        final_results = observation
                        logger.info("✅ Query executed successfully!")
                        break
                else:
                    logger.warning("No action found in response")
                    break

            # Return result with multiple query support
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

            logger.info(f"\n✅ Query processing complete")
            logger.info(f"Success: {result['success']}")
            logger.info(f"Iterations: {iteration}")
            logger.info(f"Total SQL queries: {len(all_sql_queries)}")

            return result

        except Exception as e:
            logger.error(f"❌ Error processing query: {str(e)}")
            logger.error(traceback.format_exc())
            return {"query": user_query, "error": str(e), "success": False}

    def _extract_section(self, text: str, section_name: str) -> Optional[str]:
        pattern = f"{section_name}:(.+?)(?:Action:|Observation:|Final Answer:|$)"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None

    def _extract_multiple_sql_queries(self, action: str) -> List[str]:
        """Extract multiple SQL queries from action string"""
        queries = []

        # Try to find multiple sql_db_query[] blocks
        # This pattern handles nested brackets better
        pattern = r"sql_db_query\[((?:[^\[\]]|\[(?:[^\[\]]|\[[^\[\]]*\])*\])*)\]"
        matches = re.finditer(pattern, action, re.IGNORECASE | re.DOTALL)

        for match in matches:
            sql = match.group(1).strip()
            sql = self._clean_sql_query(sql)
            if sql and sql.upper().startswith(
                ("SELECT", "WITH", "INSERT", "UPDATE", "DELETE")
            ):
                queries.append(sql)

        # If we found queries via sql_db_query[] blocks, return them
        if queries:
            logger.info(
                f"✅ Extracted {len(queries)} queries from sql_db_query[] blocks"
            )
            return queries

        # Fallback: Try to find multiple queries separated by newlines and sql_db_query
        # This handles cases where LLM puts each query on a new line
        if "sql_db_query" in action.lower():
            lines = action.split("\n")
            for line in lines:
                if "sql_db_query[" in line.lower():
                    # Extract from this line
                    match = re.search(r"sql_db_query\[(.*)", line, re.IGNORECASE)
                    if match:
                        rest = match.group(1)
                        # Find the closing bracket
                        bracket_count = 1
                        pos = 0
                        for i, char in enumerate(rest):
                            if char == "[":
                                bracket_count += 1
                            elif char == "]":
                                bracket_count -= 1
                                if bracket_count == 0:
                                    pos = i
                                    break
                        if pos > 0:
                            sql = rest[:pos].strip()
                            sql = self._clean_sql_query(sql)
                            if sql and sql.upper().startswith(
                                ("SELECT", "WITH", "INSERT", "UPDATE", "DELETE")
                            ):
                                queries.append(sql)

        if queries:
            logger.info(f"✅ Extracted {len(queries)} queries from multi-line format")
            return queries

        # If no sql_db_query blocks found, try other extraction methods
        sql = self._extract_sql_from_action(action)
        if sql:
            # Check if there are multiple SELECT statements
            # Split by semicolon or multiple SELECT keywords
            if ";" in sql:
                # Split by semicolon
                for query in sql.split(";"):
                    query = query.strip()
                    if query and query.upper().startswith(
                        ("SELECT", "WITH", "INSERT", "UPDATE", "DELETE")
                    ):
                        queries.append(query)
            else:
                # Single query
                queries.append(sql)

        if queries:
            logger.info(f"✅ Extracted {len(queries)} queries (fallback method)")
        else:
            logger.warning("⚠️ No queries extracted")

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
                        # Format the schemas for better readability
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
                                        f"  - {fk['column']} → {fk['references_table']}.{fk['references_column']}"
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

            # Check for SQL query execution (both explicit and implicit)
            if (
                "sql_db_query" in action_lower
                or ("```sql" in action_lower)
                or ("select " in action_lower and "from " in action_lower)
            ):
                # Extract all SQL queries
                sql_queries = self._extract_multiple_sql_queries(action)

                if not sql_queries:
                    return "No valid SQL queries found in action"

                # Execute all queries and collect results
                all_results = []
                total_execution_time = 0

                for idx, sql in enumerate(sql_queries, 1):
                    logger.info(f"\n📊 Executing Query {idx}/{len(sql_queries)}")
                    logger.info(f"SQL: {sql[:200]}...")

                    # Validate SQL clauses before execution
                    validation = self._validate_sql_clauses(sql)

                    if not validation["valid"]:
                        error_msg = f"Query {idx} validation failed:\n"
                        for error in validation["errors"]:
                            error_msg += f"  - ERROR: {error}\n"
                        for warning in validation["warnings"]:
                            error_msg += f"  - WARNING: {warning}\n"
                        all_results.append(
                            {
                                "query_number": idx,
                                "sql": sql,
                                "success": False,
                                "error": error_msg,
                            }
                        )
                        continue

                    # Log warnings but proceed with execution
                    if validation["warnings"]:
                        logger.warning(
                            f"SQL validation warnings: {validation['warnings']}"
                        )

                    result = self.db_tools.sql_db_query(sql)
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

                # Format response showing all query results
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
                            f"✅ Success | Rows: {result.get('row_count', 0)} | Time: {result.get('execution_time', 0):.2f}s"
                        )
                        if result.get("preview"):
                            response_parts.append(f"\nPreview:\n{result['preview']}")
                        elif result.get("message"):
                            response_parts.append(f"\n{result['message']}")
                    else:
                        response_parts.append(
                            f"❌ Failed: {result.get('error', 'Unknown error')}"
                        )

                return "\n".join(response_parts)

            return "Action not recognized or failed to execute. Please use the proper format: sql_db_query[SELECT ...] or wrap SQL in ```sql code blocks```"

        except Exception as e:
            return f"Error executing action: {str(e)}"

    def _extract_tables_from_action(self, action: str) -> List[str]:
        """Extract table names from action string"""
        match = re.search(r"sql_db_schema\[(.*?)\]", action, re.IGNORECASE)
        if match:
            tables_str = match.group(1)
            return [t.strip().strip("\"'") for t in tables_str.split(",")]
        return []

    def _extract_sql_from_action(self, action: str) -> Optional[str]:
        sql = None

        # Try format: sql_db_query[...] - handles nested brackets and multi-line
        match = re.search(r"sql_db_query\[(.+)\]", action, re.IGNORECASE | re.DOTALL)
        if match:
            sql = match.group(1).strip()

        # Try sql_db_query_checker[...] format
        if not sql:
            match = re.search(
                r"sql_db_query_checker\[(.+)\]", action, re.IGNORECASE | re.DOTALL
            )
            if match:
                sql = match.group(1).strip()

        # Try markdown code block: ```sql ... ```
        if not sql:
            match = re.search(
                r"```sql\s*\n?(.*?)\n?\s*```", action, re.IGNORECASE | re.DOTALL
            )
            if match:
                sql = match.group(1).strip()

        # Try generic code block: ``` ... ```
        if not sql:
            match = re.search(
                r"```\s*\n?((?:SELECT|INSERT|UPDATE|DELETE|WITH).*?)\n?\s*```",
                action,
                re.IGNORECASE | re.DOTALL,
            )
            if match:
                sql = match.group(1).strip()

        # Try plain SQL statements (SELECT, INSERT, UPDATE, DELETE, WITH)
        if not sql:
            # WITH (CTE) clause - must check first as it precedes SELECT
            match = re.search(
                r"\b(WITH\s+.+?\bSELECT\b.+?)(?:;|\]|$)",
                action,
                re.IGNORECASE | re.DOTALL,
            )
            if match:
                sql = match.group(1).strip()

        if not sql:
            # SELECT statement with all possible clauses
            match = re.search(
                r"\b(SELECT\s+.+?)(?:;|\]|```|$)", action, re.IGNORECASE | re.DOTALL
            )
            if match:
                sql = match.group(1).strip()

        if not sql:
            # INSERT statement
            match = re.search(
                r"\b(INSERT\s+INTO\s+.+?)(?:;|\]|```|$)",
                action,
                re.IGNORECASE | re.DOTALL,
            )
            if match:
                sql = match.group(1).strip()

        if not sql:
            # UPDATE statement
            match = re.search(
                r"\b(UPDATE\s+.+?\s+SET\s+.+?)(?:;|\]|```|$)",
                action,
                re.IGNORECASE | re.DOTALL,
            )
            if match:
                sql = match.group(1).strip()

        if not sql:
            # DELETE statement
            match = re.search(
                r"\b(DELETE\s+FROM\s+.+?)(?:;|\]|```|$)",
                action,
                re.IGNORECASE | re.DOTALL,
            )
            if match:
                sql = match.group(1).strip()

        if sql:
            # Clean up the SQL
            sql = self._clean_sql_query(sql)

        return sql

    def _clean_sql_query(self, sql: str) -> str:
        if not sql:
            return sql

        # Remove trailing semicolons and brackets
        sql = sql.rstrip(";").rstrip("]").strip()

        # Remove any markdown artifacts
        sql = re.sub(r"^```\w*\s*", "", sql)
        sql = re.sub(r"\s*```$", "", sql)

        # Normalize whitespace while preserving structure
        # Replace multiple spaces/newlines with single space, but keep SQL readable
        sql = re.sub(r"\s+", " ", sql).strip()

        # Apply case-insensitive fixes for string comparisons
        sql = self._make_string_comparisons_case_insensitive(sql)

        # Validate basic SQL structure using sqlparse
        try:
            parsed = sqlparse.parse(sql)
            if parsed and len(parsed) > 0:
                # Get the statement type
                stmt = parsed[0]
                stmt_type = stmt.get_type()

                # Format for better readability if it's a valid statement
                if stmt_type in ("SELECT", "INSERT", "UPDATE", "DELETE", "UNKNOWN"):
                    # Use sqlparse to clean up the SQL
                    sql = sqlparse.format(
                        sql, reindent=False, keyword_case="upper", strip_whitespace=True
                    )
        except Exception:
            # If parsing fails, return as-is
            pass

        return sql

    def _make_string_comparisons_case_insensitive(self, sql: str) -> str:
        """
        DO NOT modify SQL for case insensitivity.
        We expect the LLM to use exact values from metadata examples.
        This function is kept for backward compatibility but does nothing.
        """
        # Return SQL as-is - no ILIKE conversion
        # The LLM should use exact values from metadata examples
        return sql

    def _validate_sql_clauses(self, sql: str) -> Dict[str, Any]:

        result = {
            "valid": True,
            "statement_type": None,
            "clauses": {},
            "errors": [],
            "warnings": [],
        }

        try:
            parsed = sqlparse.parse(sql)
            if not parsed or len(parsed) == 0:
                result["valid"] = False
                result["errors"].append("Could not parse SQL statement")
                return result

            stmt = parsed[0]
            result["statement_type"] = stmt.get_type()

            sql_upper = sql.upper()

            # Check for various SQL clauses
            clause_patterns = {
                "SELECT": r"\bSELECT\b",
                "DISTINCT": r"\bDISTINCT\b",
                "FROM": r"\bFROM\b",
                "WHERE": r"\bWHERE\b",
                "JOIN": r"\b(INNER\s+)?JOIN\b",
                "LEFT_JOIN": r"\bLEFT\s+(OUTER\s+)?JOIN\b",
                "RIGHT_JOIN": r"\bRIGHT\s+(OUTER\s+)?JOIN\b",
                "FULL_JOIN": r"\bFULL\s+(OUTER\s+)?JOIN\b",
                "CROSS_JOIN": r"\bCROSS\s+JOIN\b",
                "ON": r"\bON\b",
                "AND": r"\bAND\b",
                "OR": r"\bOR\b",
                "NOT": r"\bNOT\b",
                "IN": r"\bIN\s*\(",
                "NOT_IN": r"\bNOT\s+IN\s*\(",
                "EXISTS": r"\bEXISTS\s*\(",
                "NOT_EXISTS": r"\bNOT\s+EXISTS\s*\(",
                "BETWEEN": r"\bBETWEEN\b",
                "LIKE": r"\bLIKE\b",
                "ILIKE": r"\bILIKE\b",  # PostgreSQL case-insensitive LIKE
                "IS_NULL": r"\bIS\s+NULL\b",
                "IS_NOT_NULL": r"\bIS\s+NOT\s+NULL\b",
                "GROUP_BY": r"\bGROUP\s+BY\b",
                "HAVING": r"\bHAVING\b",
                "ORDER_BY": r"\bORDER\s+BY\b",
                "ASC": r"\bASC\b",
                "DESC": r"\bDESC\b",
                "LIMIT": r"\bLIMIT\b",
                "OFFSET": r"\bOFFSET\b",
                "UNION": r"\bUNION\b",
                "UNION_ALL": r"\bUNION\s+ALL\b",
                "INTERSECT": r"\bINTERSECT\b",
                "EXCEPT": r"\bEXCEPT\b",
                "WITH": r"\bWITH\b",  # CTE
                "AS": r"\bAS\b",
                "CASE": r"\bCASE\b",
                "WHEN": r"\bWHEN\b",
                "THEN": r"\bTHEN\b",
                "ELSE": r"\bELSE\b",
                "END": r"\bEND\b",
                "CAST": r"\bCAST\s*\(",
                "COALESCE": r"\bCOALESCE\s*\(",
                "NULLIF": r"\bNULLIF\s*\(",
                "OVER": r"\bOVER\s*\(",  # Window functions
                "PARTITION_BY": r"\bPARTITION\s+BY\b",
                "ROW_NUMBER": r"\bROW_NUMBER\s*\(",
                "RANK": r"\bRANK\s*\(",
                "DENSE_RANK": r"\bDENSE_RANK\s*\(",
                "LAG": r"\bLAG\s*\(",
                "LEAD": r"\bLEAD\s*\(",
                "FIRST_VALUE": r"\bFIRST_VALUE\s*\(",
                "LAST_VALUE": r"\bLAST_VALUE\s*\(",
                "SUM": r"\bSUM\s*\(",
                "COUNT": r"\bCOUNT\s*\(",
                "AVG": r"\bAVG\s*\(",
                "MIN": r"\bMIN\s*\(",
                "MAX": r"\bMAX\s*\(",
                "PERCENTILE_CONT": r"\bPERCENTILE_CONT\s*\(",
                "WITHIN_GROUP": r"\bWITHIN\s+GROUP\b",
                "FILTER": r"\bFILTER\s*\(",  # PostgreSQL aggregate filter
                "LATERAL": r"\bLATERAL\b",  # PostgreSQL lateral join
                "ANY": r"\bANY\s*\(",
                "ALL": r"\bALL\s*\(",
                "SOME": r"\bSOME\s*\(",
            }

            for clause_name, pattern in clause_patterns.items():
                if re.search(pattern, sql_upper):
                    result["clauses"][clause_name] = True

            # Validation checks

            # Check for SELECT without FROM (only valid for constants)
            if result["clauses"].get("SELECT") and not result["clauses"].get("FROM"):
                if not re.search(r"SELECT\s+\d+|SELECT\s+\'", sql_upper):
                    result["warnings"].append("SELECT without FROM clause")

            # Check for JOIN without ON
            has_join = any(
                result["clauses"].get(j)
                for j in ["JOIN", "LEFT_JOIN", "RIGHT_JOIN", "FULL_JOIN"]
            )
            if (
                has_join
                and not result["clauses"].get("ON")
                and not result["clauses"].get("CROSS_JOIN")
            ):
                result["errors"].append("JOIN clause without ON condition")
                result["valid"] = False

            # Check for GROUP BY when using aggregates without window functions
            has_aggregate = any(
                result["clauses"].get(a) for a in ["SUM", "COUNT", "AVG", "MIN", "MAX"]
            )
            has_window = result["clauses"].get("OVER")

            if (
                has_aggregate
                and not has_window
                and not result["clauses"].get("GROUP_BY")
            ):
                # Extract SELECT clause to analyze columns
                select_match = re.search(
                    r"SELECT\s+(DISTINCT\s+)?(.*?)\s+FROM",
                    sql_upper,
                    re.DOTALL | re.IGNORECASE,
                )
                if select_match:
                    select_part = select_match.group(2).strip()

                    # Check if SELECT contains both aggregate functions and non-aggregate columns
                    # Remove aggregate function calls to see what's left
                    cleaned_select = re.sub(
                        r"\b(SUM|COUNT|AVG|MIN|MAX|STRING_AGG|ARRAY_AGG)\s*\([^)]+\)",
                        "",
                        select_part,
                        flags=re.IGNORECASE,
                    )
                    cleaned_select = re.sub(
                        r"\bDISTINCT\s+", "", cleaned_select, flags=re.IGNORECASE
                    )
                    cleaned_select = re.sub(
                        r"\s+AS\s+\w+", "", cleaned_select, flags=re.IGNORECASE
                    )  # Remove aliases
                    cleaned_select = cleaned_select.strip()

                    # If there's still content after removing aggregates, we likely have non-aggregate columns
                    # Also check for multiple columns (comma separated)
                    has_non_aggregate_columns = bool(
                        cleaned_select and cleaned_select not in [",", "", "*"]
                    )
                    has_multiple_columns = "," in select_part

                    # If we have aggregates AND non-aggregate columns, GROUP BY is required
                    if has_non_aggregate_columns and has_multiple_columns:
                        result["errors"].append(
                            "❌ CRITICAL: Aggregate functions (SUM, COUNT, AVG, MIN, MAX) used with non-aggregate columns. "
                            "You MUST include a GROUP BY clause with all non-aggregate columns from SELECT. "
                            "Example: SELECT column1, SUM(column2) FROM table GROUP BY column1"
                        )
                        result["valid"] = False
                    elif has_non_aggregate_columns:
                        # Single column case - might still need GROUP BY
                        result["warnings"].append(
                            "⚠️ Aggregate function detected without GROUP BY. "
                            "If you're selecting non-aggregate columns, add GROUP BY clause."
                        )

            # Check for HAVING without GROUP BY
            if result["clauses"].get("HAVING") and not result["clauses"].get(
                "GROUP_BY"
            ):
                result["warnings"].append("HAVING clause without GROUP BY")

            # Check for ORDER BY in subqueries (PostgreSQL allows this but may not be meaningful)
            if result["clauses"].get("ORDER_BY") and sql_upper.count("SELECT") > 1:
                result["warnings"].append(
                    "ORDER BY in subquery may be ignored unless used with LIMIT"
                )

            # Check for TOP (SQL Server syntax - invalid in PostgreSQL)
            if re.search(r"\bTOP\s+\d+", sql_upper):
                result["errors"].append(
                    "TOP is SQL Server syntax. Use LIMIT for PostgreSQL"
                )
                result["valid"] = False

            # Check for ILIKE or LIKE usage (should use exact values from metadata examples)
            if result["clauses"].get("ILIKE") or result["clauses"].get("LIKE"):
                result["errors"].append(
                    "❌ CRITICAL: Do NOT use ILIKE or LIKE. "
                    "Check the '💎 AVAILABLE EXAMPLE VALUES' section and use EXACT values with = or IN. "
                    "If you don't have example values, use LOWER(column) = LOWER('value') for case-insensitive matching."
                )
                result["valid"] = False

            # Check for balanced parentheses
            if sql.count("(") != sql.count(")"):
                result["errors"].append("Unbalanced parentheses")
                result["valid"] = False

        except Exception as e:
            result["valid"] = False
            result["errors"].append(f"SQL parsing error: {str(e)}")

        return result


# For backward compatibility
RAGEnhancedReActAgent = EnhancedRAGReActAgent
