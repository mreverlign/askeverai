import sys
import time
import re
import logging
from pathlib import Path
from decimal import Decimal
from datetime import datetime, date
from typing import Optional, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from llm_client import LLMClient
from src.tools.database_tools import DatabaseTools
from src.embedders.structured_embedder import (
    StructuredMetadataEmbedder as MetadataEmbedder,
)
from src.agents.rag_agent import EnhancedRAGReActAgent as RAGEnhancedReActAgent
from src.config.config import Config
from user_database import UserDatabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AskEver AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

system = {}


def initialize_system():
    try:
        llm_client = LLMClient()
        db_tools = DatabaseTools(Config.OLAP_DB_CONFIG, Config.OLTP_DB_CONFIG)
        if not db_tools.connect():
            # connect() returns True when the required OLAP connection works,
            # including the supported OLAP-only mode when OLTP is unavailable.
            raise RuntimeError("Could not connect to the required OLAP database.")
        embedder = MetadataEmbedder()

        indices_dir = "./data/indices/rag_indices"
        if Path(indices_dir).exists():
            logger.info("Loading indices...")
            embedder.load_indices(indices_dir)
        else:
            raise Exception(
                "No RAG indices found. Run scripts/setup_embeddings.py first."
            )

        agent = RAGEnhancedReActAgent(llm_client, db_tools, embedder)
        user_db = UserDatabase()

        return {
            "agent": agent,
            "db_tools": db_tools,
            "user_db": user_db,
            "llm_client": llm_client,
            "status": "success",
        }
    except Exception as e:
        logger.error(f"Error initializing system: {e}")
        return {"status": "error", "error": str(e)}


@app.on_event("startup")
async def startup_event():
    global system
    system = initialize_system()
    if system["status"] != "success":
        logger.error(f"System initialization failed: {system.get('error')}")


class LoginRequest(BaseModel):
    username: str


class ConversationItem(BaseModel):
    query: str
    answer: Optional[str] = None
    sql: Optional[str] = None


class QueryRequest(BaseModel):
    query: str
    username: str = "api_user"
    conversation_history: List[ConversationItem] = []


class FeedbackRequest(BaseModel):
    query_id: int
    username: str
    rating: int
    feedback_text: Optional[str] = None


def serialize_value(val):
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="replace")
    return val


def serialize_row(row: dict) -> dict:
    return {k: serialize_value(v) for k, v in row.items()}


def format_sql_for_display(sql):
    if not sql:
        return sql

    formatted = sql.strip()

    keywords = [
        "SELECT",
        "FROM",
        "WHERE",
        "JOIN",
        "LEFT JOIN",
        "RIGHT JOIN",
        "INNER JOIN",
        "GROUP BY",
        "ORDER BY",
        "HAVING",
        "LIMIT",
        "OFFSET",
        "AND",
        "OR",
        "AS",
        "ON",
        "IN",
        "NOT",
        "NULL",
        "IS",
        "UNION",
    ]

    for keyword in keywords:
        formatted = formatted.replace(f" {keyword} ", f"\n{keyword} ")
        formatted = formatted.replace(f" {keyword.lower()} ", f"\n{keyword} ")

    lines = [line.strip() for line in formatted.split("\n") if line.strip()]
    formatted = "\n".join(lines)

    return formatted


def detect_why_question(query):
    why_keywords = [
        "why",
        "reason",
        "explain",
        "cause",
        "drop",
        "decrease",
        "increase",
        "decline",
        "happen",
        "fell",
        "rose",
        "grew",
        "shrank",
        "spike",
        "surge",
        "changed",
    ]
    return any(kw in query.lower() for kw in why_keywords)


def generate_answer(
    llm_client,
    question,
    sql,
    data,
    conversation_history=None,
    is_why=False,
    truncated=False,
    row_limit=None,
):
    try:
        if not data:
            return "The query returned no results. Try broadening your search criteria or adjusting the filters."

        df = pd.DataFrame(data[:50])
        data_preview = df.to_string(index=False)
        returned_rows = len(data)
        if truncated:
            result_summary = (
                f"at least {returned_rows} rows; the database response was capped "
                f"at {row_limit or returned_rows}, showing up to 50"
            )
        else:
            result_summary = f"{returned_rows} total rows, showing up to 50"

        has_memo = (
            any("memo" in col.lower() for col in data[0].keys()) if data else False
        )

        conv_section = ""
        if conversation_history:
            conv_section = "Previous conversation:\n"
            for item in conversation_history[-3:]:
                conv_section += f"  User: {item.get('query', '')}\n"
                if item.get("answer"):
                    conv_section += f"  Assistant: {item['answer']}\n"
            conv_section += "\n"

        prompt = f"""You are a professional data analyst. Based on the SQL query results below, provide a clear, direct answer to the user's question.

{conv_section}User Question: {question}

SQL Query: {sql}

Query Results ({result_summary}):
{data_preview}

Instructions:
- Answer the question directly in natural English
- Include specific numbers, totals, and key findings from the data
- Format currency/large numbers with commas (e.g., $1,234,567)
- Highlight the most important insight first
- If there are notable patterns, trends, or outliers, mention them briefly
- Keep it concise: 2-4 sentences for simple queries, a short paragraph for complex ones
- Do NOT mention SQL, databases, or technical details
- Do NOT say "based on the data" or "the query shows" - just state the findings directly"""

        if truncated:
            prompt += """
- The returned rows are a capped sample, not the complete result set
- Do not claim a complete ranking, exhaustive count, or overall total unless the SQL itself aggregated it into the returned rows"""

        if is_why and has_memo:
            prompt += """
- The user is asking WHY something happened
- The memo column contains explanations, notes, and reasons for transactions
- Analyze the memo content and provide a polished, professional summary of the key reasons
- Group similar reasons together and present the most common/impactful ones first
- Do NOT show raw memo text - synthesize and present the insights professionally"""

        prompt += "\n\nAnswer:"

        response = llm_client.generate(prompt, temperature=0.0, max_tokens=800)
        if response and not response.startswith("Error:"):
            return response.strip()
        return _fallback_answer(question, data, returned_rows)

    except Exception as e:
        logger.error(f"Answer generation failed: {e}")
        return _fallback_answer(question, data, len(data))


def _fallback_answer(question, data, total_rows):
    if not data:
        return "No results found for your query."

    columns = list(data[0].keys())
    numeric_cols = [
        c for c in columns if isinstance(data[0].get(c), (int, float, Decimal))
    ]

    parts = [f"Found {total_rows:,} result(s)."]

    if numeric_cols and total_rows > 1:
        for col in numeric_cols[:2]:
            values = [row.get(col) for row in data if row.get(col) is not None]
            if values:
                total = sum(float(v) for v in values)
                parts.append(f"Total {col}: {total:,.2f}")

    return " ".join(parts)


def build_trajectory(thought_process, answer_text=""):
    trajectory = []
    i = 0
    while i < len(thought_process):
        step = thought_process[i]

        if step["type"] == "thought":
            trajectory.append(
                {
                    "type": "thought",
                    "content": step["content"],
                }
            )

        elif step["type"] == "action":
            action_content = step["content"]
            tool_name = "sql_query"
            tool_input = action_content

            match = re.match(r"(\w+)\[(.+)\]", action_content, re.DOTALL)
            if match:
                tool_name = match.group(1)
                tool_input = match.group(2)

            output = None
            if (
                i + 1 < len(thought_process)
                and thought_process[i + 1]["type"] == "observation"
            ):
                obs_content = thought_process[i + 1]["content"]
                is_failure = obs_content.lower().startswith(
                    "failed"
                ) or obs_content.lower().startswith("error")

                if is_failure:
                    output = {"success": False, "error": obs_content[:500]}
                else:
                    output = {"success": True, "message": obs_content[:500]}
                i += 1

            trajectory.append(
                {
                    "type": "action",
                    "tool": tool_name,
                    "input": tool_input,
                    "output": output,
                    "content": action_content,
                }
            )

        elif step["type"] == "observation":
            pass

        i += 1

    if answer_text:
        trajectory.append(
            {
                "type": "answer",
                "content": answer_text,
            }
        )

    return trajectory


@app.get("/health")
async def health_check():
    return {
        "status": "ok" if system.get("status") == "success" else "error",
        "detail": system.get("error") if system.get("status") != "success" else None,
    }


@app.post("/login")
async def login(request: LoginRequest):
    if system.get("status") != "success":
        raise HTTPException(status_code=503, detail="System not initialized")

    username = request.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")

    user_db = system["user_db"]
    user_id = user_db.add_user(username)
    return {"user_id": user_id, "username": username}


@app.get("/history/{username}")
async def get_history(username: str):
    if system.get("status") != "success":
        raise HTTPException(status_code=503, detail="System not initialized")

    user_db = system["user_db"]
    history = user_db.get_user_history(username, limit=10)
    return {"history": history}


@app.post("/feedback")
async def submit_feedback(request: FeedbackRequest):
    if system.get("status") != "success":
        raise HTTPException(status_code=503, detail="System not initialized")

    user_db = system["user_db"]
    feedback_id = user_db.save_feedback(
        query_id=request.query_id,
        username=request.username,
        rating=request.rating,
        feedback_text=request.feedback_text,
    )
    return {"success": True, "feedback_id": feedback_id}


@app.get("/schema")
async def get_schema():
    if system.get("status") != "success":
        raise HTTPException(status_code=503, detail="System not initialized")

    db_tools = system["db_tools"]
    tables_result = db_tools.sql_db_list_tables()

    if not tables_result["success"]:
        raise HTTPException(status_code=500, detail="Failed to fetch tables")

    tables = tables_result["tables"]
    schema_result = db_tools.sql_db_schema(tables)

    details = {}
    if schema_result["success"]:
        for table_name, info in schema_result["schemas"].items():
            details[table_name] = {
                "row_count": info["row_count"],
                "columns": [{"name": col["name"]} for col in info["columns"]],
            }

    return {"tables": tables, "details": details}


@app.get("/examples")
async def get_examples():
    return {
        "examples": [
            "Show me total sales by client",
            "What are the top 10 products by revenue?",
            "Show me sales by transaction type",
            "What is the total revenue by sales rep?",
            "Show me monthly sales trends",
            "List all clients with their total order amounts",
            "What are the top 5 partners by sales volume?",
            "Show me sales by item category",
            "What is the average order value by client category?",
            "Show me the total quantity sold by product",
        ]
    }


@app.post("/query")
async def run_query(request: QueryRequest):
    if system.get("status") != "success":
        raise HTTPException(status_code=503, detail="System not initialized")

    start_time = time.time()
    agent = system["agent"]
    db_tools = system["db_tools"]
    user_db = system["user_db"]
    llm_client = system["llm_client"]

    is_why = detect_why_question(request.query)

    conv_history_dicts = (
        [item.model_dump() for item in request.conversation_history]
        if request.conversation_history
        else None
    )

    try:
        result = agent.process_query(
            request.query,
            conversation_history=conv_history_dicts,
        )

        if not result.get("success") or not result.get("sql"):
            total_time = round(time.time() - start_time, 2)
            error_msg = result.get("error", "Could not generate SQL for this query.")
            return {
                "answer": error_msg,
                "data": [],
                "metadata": {
                    "total_time": total_time,
                    "iterations": result.get("iterations", 0),
                    "row_count": 0,
                },
                "trajectory": build_trajectory(
                    result.get("thought_process", []),
                    error_msg,
                ),
                "sql_queries": result.get("all_sql_queries", []),
                "formatted_sql": [
                    format_sql_for_display(q) for q in result.get("all_sql_queries", [])
                ],
                "query_id": None,
                "db_source": None,
                "fallback_used": False,
                "recommended_db": agent.recommended_db,
                "relevant_tables": result.get("relevant_tables", []),
            }

        # The ReAct query action has already executed and validated this SQL.
        # Reuse that structured result instead of running the database query a
        # second time.
        action_results = result.get("all_query_results", [])
        if action_results and action_results[0].get("success"):
            exec_result = action_results[0]
        else:
            exec_result = db_tools.sql_db_query(
                result["sql"], target_db=agent.recommended_db
            )
        total_time_before_answer = time.time() - start_time

        data = []
        if exec_result.get("success") and exec_result.get("data"):
            data = [serialize_row(row) for row in exec_result["data"]]

        row_count = len(data)
        db_source = exec_result.get("db_source", "OLAP")
        fallback_used = exec_result.get("fallback_used", False)

        if exec_result.get("success") and data:
            answer = generate_answer(
                llm_client,
                request.query,
                result["sql"],
                data,
                conversation_history=conv_history_dicts,
                is_why=is_why,
                truncated=exec_result.get("truncated", False),
                row_limit=exec_result.get("row_limit"),
            )
        elif not exec_result.get("success"):
            answer = (
                f"Query execution failed: {exec_result.get('error', 'Unknown error')}"
            )
        else:
            answer = "The query returned no results. Try broadening your search criteria or adjusting the filters."

        total_time = round(time.time() - start_time, 2)

        query_id = None
        try:
            query_id = user_db.save_query(
                username=request.username,
                question=request.query,
                generated_sql=result["sql"],
                executed_sql=result["sql"],
                results=pd.DataFrame(data) if data else None,
                result_count=row_count,
                iterations=result.get("iterations", 0),
                tables_used=result.get("relevant_tables", []),
            )
        except Exception as e:
            logger.error(f"Error saving query: {e}")

        sql_queries = result.get("all_sql_queries", [])
        if not sql_queries and result.get("sql"):
            sql_queries = [result["sql"]]

        return {
            "answer": answer,
            "data": data,
            "metadata": {
                "total_time": total_time,
                "iterations": result.get("iterations", 0),
                # Backward-compatible count of rows actually returned. It is
                # not necessarily the total matching row count when capped.
                "row_count": row_count,
                "returned_row_count": row_count,
                "truncated": exec_result.get("truncated", False),
                "row_limit": exec_result.get("row_limit"),
                "result_complete": not exec_result.get("truncated", False),
            },
            "trajectory": build_trajectory(
                result.get("thought_process", []),
                answer,
            ),
            "sql_queries": sql_queries,
            "formatted_sql": [format_sql_for_display(q) for q in sql_queries],
            "query_id": query_id,
            "db_source": db_source,
            "fallback_used": fallback_used,
            "recommended_db": agent.recommended_db,
            "relevant_tables": result.get("relevant_tables", []),
        }

    except Exception as e:
        logger.error(f"Query error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
