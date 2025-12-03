import streamlit as st
import pandas as pd
from llm_client import LLMClient
from database_tools import DatabaseTools
from rag_metadata_embedder_focused import FocusedColumnEmbedder as MetadataEmbedder
from rag_enhanced_agent import RAGEnhancedReActAgent
from config import Config
import plotly.express as px
import plotly.graph_objects as go
import json
from pathlib import Path
import logging
from user_database import UserDatabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Filter out WebSocket closed errors
class WebSocketErrorFilter(logging.Filter):
    def filter(self, record):
        message = str(record.getMessage())
        return not ('WebSocketClosedError' in message or
                   'Stream is closed' in message)

# Apply filter to tornado and asyncio loggers
logging.getLogger('tornado.application').addFilter(WebSocketErrorFilter())
logging.getLogger('asyncio').addFilter(WebSocketErrorFilter())
logging.getLogger('tornado.general').addFilter(WebSocketErrorFilter())

# Page config
st.set_page_config(
    page_title="RAG-Enhanced NLQ System",
    page_icon="🤖",
    layout="wide"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        padding: 1rem 0;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    .success-box {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        border-radius: 0.5rem;
        padding: 1rem;
        margin: 1rem 0;
    }
    .info-box {
        background-color: #d1ecf1;
        border: 1px solid #bee5eb;
        border-radius: 0.5rem;
        padding: 1rem;
        margin: 1rem 0;
    }
    .warning-box {
        background-color: #fff3cd;
        border: 1px solid #ffeeba;
        border-radius: 0.5rem;
        padding: 1rem;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def initialize_system():
    """
    Initialize all system components
    """
    try:
        # Initialize LLM client
        llm_client = LLMClient()

        # Initialize database tools with config
        db_tools = DatabaseTools(Config.DB_CONFIG)
        db_tools.connect()

        # Initialize embedder
        embedder = MetadataEmbedder()

        # Try to load existing indices
        indices_dir = "./rag_indices_focused"
        if Path(indices_dir).exists():
            logger.info("Loading existing focused RAG indices...")
            embedder.load_indices(indices_dir)
        else:
            logger.info("Creating new focused RAG indices...")
            # Load CSVs with correct filenames
            embedder.load_and_embed_metadata("HighTower_Metadata(Metadata) (1).csv")
            embedder.load_and_embed_relationships("HighTower_Metadata(Relationships).csv")
            embedder.load_and_embed_datamodel("HighTower_Metadata(HighTower_Data_Model) (2).csv")
            embedder.save_indices(indices_dir)

        # Initialize RAG-enhanced agent
        agent = RAGEnhancedReActAgent(llm_client, db_tools, embedder)

        # Initialize user database
        user_db = UserDatabase()

        return {
            'agent': agent,
            'llm_client': llm_client,
            'db_tools': db_tools,
            'embedder': embedder,
            'user_db': user_db,
            'status': 'success'
        }

    except Exception as e:
        logger.error(f"Error initializing system: {e}")
        return {
            'status': 'error',
            'error': str(e)
        }


def get_username():
    """Display username entry dialog and return username"""
    if 'username' not in st.session_state or not st.session_state['username']:
        st.markdown('<div class="main-header">🤖 Welcome to RAG-Enhanced NLQ System</div>', unsafe_allow_html=True)
        st.markdown('<div class="sub-header">Please enter your username to continue</div>', unsafe_allow_html=True)

        with st.form("username_form"):
            username = st.text_input(
                "Username:",
                placeholder="Enter your username",
                max_chars=50,
                help="This will be used to track your queries and feedback"
            )
            submit = st.form_submit_button("Continue", type="primary")

            if submit:
                if username and username.strip():
                    st.session_state['username'] = username.strip()
                    st.rerun()
                else:
                    st.error("Please enter a valid username")

        st.stop()

    return st.session_state['username']


def display_header():
    """Display application header"""
    st.markdown('<div class="main-header">🤖 RAG-Enhanced NLQ System</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">AI-Powered Natural Language Queries with Semantic Search</div>',
        unsafe_allow_html=True
    )

    # Display current user
    if 'username' in st.session_state and st.session_state['username']:
        _, col2, col3 = st.columns([4, 1, 1])
        with col2:
            st.info(f"👤 User: {st.session_state['username']}")
        with col3:
            if st.button("🚪 Logout"):
                st.session_state.clear()
                st.rerun()


def display_rag_context(rag_context):
    """
    Display RAG context in sidebar
    """
    with st.sidebar:
        st.subheader("🔍 Semantic Search Context")
        
        if rag_context.get('relevant_tables'):
            with st.expander("📊 Relevant Tables", expanded=True):
                for table in rag_context['relevant_tables']:
                    st.markdown(f"- `{table}`")
        
        if rag_context.get('metadata_results'):
            with st.expander("📋 Top Metadata Matches"):
                for i, result in enumerate(rag_context['metadata_results'][:5], 1):
                    st.markdown(f"**{i}. {result['table_name']}.{result['column_name']}**")
                    st.caption(f"Score: {result['score']:.3f}")
                    if result.get('description'):
                        st.caption(f"_{result['description'][:100]}..._")
                    st.markdown("---")
        
        if rag_context.get('relationships'):
            with st.expander("🔗 Relevant Relationships"):
                for rel in rag_context['relationships'][:5]:
                    st.markdown(f"**{rel['from']} → {rel['to']}**")
                    st.caption(f"Join: `{rel['join_condition']}`")
                    # Handle different score field names
                    if 'score' in rel:
                        st.caption(f"Score: {rel['score']:.3f}")
                    elif 'hybrid_score' in rel:
                        st.caption(f"Score: {rel['hybrid_score']:.3f}")
                    else:
                        st.caption("Score: N/A")
                    st.markdown("---")


def display_thought_process(thought_log):
    st.subheader("🧠 Agent Reasoning Process")
    
    for i, entry in enumerate(thought_log, 1):
        entry_type = entry['type']
        content = entry['content']
        
        if entry_type == 'thought':
            with st.expander(f"💭 Thought {i}", expanded=False):
                st.info(content)
        elif entry_type == 'action':
            with st.expander(f"⚡ Action {i}", expanded=False):
                st.code(content, language='python')
        elif entry_type == 'observation':
            with st.expander(f"👁️ Observation {i}", expanded=False):
                st.success(content)


def create_visualization(df, query):
    if df is None or df.empty:
        return None

    try:
        # Determine visualization type
        numeric_cols = df.select_dtypes(include=['float64', 'int64']).columns.tolist()
        categorical_cols = df.select_dtypes(include=['object']).columns.tolist()

        if len(numeric_cols) >= 1 and len(categorical_cols) >= 1:
            # Bar chart
            fig = px.bar(
                df.head(20),
                x=categorical_cols[0],
                y=numeric_cols[0],
                title=f"{numeric_cols[0]} by {categorical_cols[0]}",
                color=numeric_cols[0],
                color_continuous_scale='Blues'
            )
            fig.update_layout(xaxis_tickangle=-45)
            return fig

        elif len(numeric_cols) >= 2:
            # Scatter plot
            fig = px.scatter(
                df.head(100),
                x=numeric_cols[0],
                y=numeric_cols[1],
                title=f"{numeric_cols[0]} vs {numeric_cols[1]}",
                color=numeric_cols[1] if len(numeric_cols) > 1 else None
            )
            return fig

        elif len(numeric_cols) == 1 and len(categorical_cols) >= 1:
            # Pie chart for aggregated data
            if len(df) <= 20:
                fig = px.pie(
                    df,
                    names=categorical_cols[0],
                    values=numeric_cols[0],
                    title=f"Distribution of {numeric_cols[0]}"
                )
                return fig

    except Exception as e:
        logger.error(f"Error creating visualization: {e}")

    return None


def display_feedback_form(user_db, query_id, username):
    """Display rating and feedback form after results"""
    st.markdown("---")
    st.subheader("📝 Rate This Query")

    with st.form(f"feedback_form_{query_id}"):
        st.write("How would you rate the quality of this query result?")

        # Rating using star emojis
        rating = st.radio(
            "Rating:",
            options=[1, 2, 3, 4, 5],
            format_func=lambda x: "⭐" * x,
            horizontal=True,
            help="1 = Poor, 5 = Excellent"
        )

        # Feedback text
        feedback_text = st.text_area(
            "Additional Feedback (Optional):",
            placeholder="Tell us what worked well or what could be improved...",
            height=100
        )

        # Submit button
        submit_feedback = st.form_submit_button("Submit Feedback", type="primary")

        if submit_feedback:
            try:
                # Save feedback to database
                feedback_id = user_db.save_feedback(
                    query_id=query_id,
                    username=username,
                    rating=rating,
                    feedback_text=feedback_text if feedback_text.strip() else None
                )

                st.success(f"✅ Thank you for your feedback! (Rating: {'⭐' * rating})")

                # Mark feedback as submitted in session state
                st.session_state[f'feedback_submitted_{query_id}'] = True

            except Exception as e:
                st.error(f"❌ Error saving feedback: {str(e)}")
                logger.error(f"Feedback save error: {e}")

    # Show if feedback already submitted
    if st.session_state.get(f'feedback_submitted_{query_id}', False):
        st.info("✅ Feedback already submitted for this query")


def main():
    # Get username first (will show login screen if not set)
    username = get_username()

    display_header()

    # Initialize system
    with st.spinner("🔄 Initializing RAG-Enhanced NLQ System..."):
        system = initialize_system()

    if system['status'] == 'error':
        st.error(f"❌ System initialization failed: {system['error']}")
        st.stop()

    st.success("✅ System initialized successfully!")

    # Get user database
    user_db = system['user_db']
    
    # Sidebar configuration
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        show_rag_context = st.checkbox("Show RAG Context", value=True)
        show_thought_process = st.checkbox("Show Reasoning Process", value=True)
        auto_visualize = st.checkbox("Auto-generate Visualizations", value=True)
        
        st.markdown("---")
        
        st.subheader("📊 System Info")
        st.metric("Model", Config.OPENAI_MODEL.split('/')[-1][:30])
        st.metric("Database", Config.DB_CONFIG['database'])
        st.metric("Max Iterations", Config.MAX_AGENT_ITERATIONS)
        
        st.markdown("---")

        # User Statistics
        st.subheader("📈 Your Statistics")
        try:
            user_history = user_db.get_user_history(username, limit=5)
            st.metric("Total Queries", len(user_db.get_user_history(username, limit=1000)))

            if user_history:
                with st.expander("📜 Recent Queries", expanded=False):
                    for i, hist in enumerate(user_history[:5], 1):
                        st.markdown(f"**{i}. {hist['question'][:50]}...**")
                        st.caption(f"Date: {hist['created_at']}")
                        if hist['rating']:
                            st.caption(f"Rating: {'⭐' * hist['rating']}")
                        st.markdown("---")
        except Exception as e:
            logger.error(f"Error loading user statistics: {e}")

        st.markdown("---")

        st.subheader("💡 Example Queries")
        example_queries = [
            "Show me total sales by client category",
            "What are the top 10 selling products by revenue?",
            "List all transactions with their customer names",
            "Which sales representatives have the highest revenue?",
            "Show me sales trends by month for last year",
            "What is the average transaction amount by vertical market?",
            "Find all projects with their associated clients",
            "Show product categories with most sales volume"
        ]

        for example in example_queries:
            if st.button(example, key=f"ex_{hash(example)}"):
                st.session_state['query_input'] = example
    
    # Main query interface
    st.header("📝 Natural Language Query")
    
    # Query input
    query = st.text_area(
        "Enter your question:",
        value=st.session_state.get('query_input', ''),
        height=100,
        placeholder="e.g., Show me total sales by customer category..."
    )
    
    col1, col2, col3 = st.columns([1, 1, 4])
    
    with col1:
        execute_button = st.button("🚀 Execute Query", type="primary")
    
    with col2:
        clear_button = st.button("🗑️ Clear")
    
    if clear_button:
        st.session_state['query_input'] = ''
        st.rerun()
    
    # Execute query - Generate SQL and Auto-Execute
    if execute_button and query:
        with st.spinner("🔄 Processing your query and executing SQL..."):
            try:
                # Process query with RAG-enhanced agent
                result = system['agent'].process_query(query)

                # Store result in session state
                if result.get('success') and result.get('sql'):
                    st.session_state['query_result'] = result
                    st.session_state['edited_sql'] = result['sql']
                    st.session_state['last_query'] = query

                    # AUTO-EXECUTE: Execute queries immediately
                    try:
                        # Check if we have multiple queries
                        has_multiple = result.get('multiple_queries', False) and len(result.get('all_sql_queries', [])) > 1

                        if has_multiple:
                            # Execute multiple queries
                            all_queries = result.get('all_sql_queries', [])
                            all_exec_results = []
                            total_time = 0

                            for idx, sql_query in enumerate(all_queries, 1):
                                logger.info(f"Auto-executing query {idx}/{len(all_queries)}")
                                exec_result = system['db_tools'].sql_db_query(sql_query)
                                exec_result['query_number'] = idx
                                exec_result['sql'] = sql_query
                                total_time += exec_result.get('execution_time', 0)
                                all_exec_results.append(exec_result)

                            # Store multiple results
                            st.session_state['sql_executed'] = True
                            st.session_state['multiple_execution'] = True
                            st.session_state['execution_results'] = all_exec_results
                            st.session_state['total_execution_time'] = total_time
                            st.session_state['all_sql_queries'] = all_queries

                            # Save first successful query to database
                            for exec_result in all_exec_results:
                                if exec_result.get('success'):
                                    try:
                                        query_id = user_db.save_query(
                                            username=username,
                                            question=query,
                                            generated_sql=result.get('sql', ''),
                                            executed_sql=exec_result['sql'],
                                            results=pd.DataFrame(exec_result.get('data', [])) if exec_result.get('data') else None,
                                            result_count=exec_result.get('row_count', 0),
                                            iterations=result.get('iterations', 0),
                                            tables_used=result.get('relevant_tables', [])
                                        )
                                        st.session_state['current_query_id'] = query_id
                                        break
                                    except Exception as db_error:
                                        logger.error(f"Error saving query to database: {db_error}")
                        else:
                            # Execute single query
                            exec_result = system['db_tools'].sql_db_query(result['sql'])

                            # Store execution result
                            st.session_state['sql_executed'] = True
                            st.session_state['multiple_execution'] = False
                            st.session_state['execution_result'] = exec_result

                            # Save query to database
                            if exec_result.get('success'):
                                try:
                                    query_id = user_db.save_query(
                                        username=username,
                                        question=query,
                                        generated_sql=result.get('sql', ''),
                                        executed_sql=result['sql'],
                                        results=pd.DataFrame(exec_result.get('data', [])) if exec_result.get('data') else None,
                                        result_count=exec_result.get('row_count', 0),
                                        iterations=result.get('iterations', 0),
                                        tables_used=result.get('relevant_tables', [])
                                    )
                                    st.session_state['current_query_id'] = query_id
                                except Exception as db_error:
                                    logger.error(f"Error saving query to database: {db_error}")

                    except Exception as exec_error:
                        st.error(f"❌ Error executing generated SQL: {str(exec_error)}")
                        st.session_state['sql_executed'] = False
                        st.session_state['execution_result'] = None

                elif result.get('success'):
                    st.warning("⚠️ Query processed but no SQL was generated")
                else:
                    st.error(f"❌ Query failed: {result.get('error', 'Unknown error')}")

            except Exception as e:
                st.error(f"❌ Error processing query: {str(e)}")
                logger.error(f"Query processing error: {e}", exc_info=True)

    # Display results and SQL editor if we have a generated query
    if 'query_result' in st.session_state and st.session_state.get('query_result'):
        result = st.session_state['query_result']

        st.markdown('<div class="success-box">✅ SQL Generated & Executed!</div>', unsafe_allow_html=True)

        # Display execution results FIRST (if available)
        if st.session_state.get('sql_executed'):
            st.markdown("---")

            # Check if multiple queries were executed
            if st.session_state.get('multiple_execution'):
                # Display multiple query results
                all_exec_results = st.session_state.get('execution_results', [])
                total_time = st.session_state.get('total_execution_time', 0)

                st.success(f"✅ All queries executed! Total time: {total_time:.2f}s")
                st.subheader(f"📊 Results from {len(all_exec_results)} Queries")

                # Display each query result in a separate section
                for exec_result in all_exec_results:
                    query_num = exec_result.get('query_number', 1)
                    with st.expander(f"📋 Query {query_num} Results", expanded=True):
                        # Show SQL
                        st.code(exec_result.get('sql', ''), language='sql')

                        if exec_result.get('success'):
                            st.success(f"✅ Executed in {exec_result.get('execution_time', 0):.2f}s")

                            if exec_result.get('data'):
                                df = pd.DataFrame(exec_result['data'])
                                total_rows = exec_result['row_count']
                                st.info(f"📈 Returned {total_rows:,} row(s)")

                                # Add pagination for large datasets
                                if total_rows > 1000:
                                    st.warning(f"⚠️ Large dataset ({total_rows:,} rows). Showing paginated results.")

                                    # Use timestamp to ensure unique keys between auto-exec and re-exec
                                    import time
                                    unique_id = int(time.time() * 1000) % 10000

                                    rows_per_page = st.selectbox(
                                        "Rows per page:",
                                        options=[100, 500, 1000, 5000],
                                        index=1,
                                        key=f'rows_per_page_{query_num}_{unique_id}'
                                    )

                                    total_pages = (total_rows - 1) // rows_per_page + 1
                                    page = st.number_input(
                                        f"Page (1-{total_pages}):",
                                        min_value=1,
                                        max_value=total_pages,
                                        value=1,
                                        key=f'page_{query_num}_{unique_id}'
                                    )

                                    start_idx = (page - 1) * rows_per_page
                                    end_idx = min(start_idx + rows_per_page, total_rows)

                                    st.dataframe(
                                        df.iloc[start_idx:end_idx],
                                        use_container_width=True
                                    )
                                    st.caption(f"Showing rows {start_idx + 1:,} to {end_idx:,} of {total_rows:,}")

                                    csv = df.to_csv(index=False)
                                    st.download_button(
                                        label=f"📥 Download Query {query_num} (CSV)",
                                        data=csv,
                                        file_name=f"query_{query_num}_results.csv",
                                        mime="text/csv",
                                        key=f'download_{query_num}_{unique_id}'
                                    )
                                else:
                                    st.dataframe(df, use_container_width=True)

                                    csv = df.to_csv(index=False)
                                    import time
                                    unique_id = int(time.time() * 1000) % 10000
                                    st.download_button(
                                        label=f"📥 Download Query {query_num} (CSV)",
                                        data=csv,
                                        file_name=f"query_{query_num}_results.csv",
                                        mime="text/csv",
                                        key=f'download_else_{query_num}_{unique_id}'
                                    )

                                # Auto-visualization
                                if auto_visualize and len(df) > 0:
                                    fig = create_visualization(df, f"Query {query_num}")
                                    if fig:
                                        st.plotly_chart(fig, use_container_width=True)
                            else:
                                st.info("Query executed successfully but returned no rows")
                        else:
                            st.error(f"❌ Query failed: {exec_result.get('error', 'Unknown error')}")

            elif st.session_state.get('execution_result'):
                # Single query result
                exec_result = st.session_state['execution_result']

                if exec_result.get('success'):
                    st.success(f"✅ Query executed successfully in {exec_result.get('execution_time', 0)}s!")

                    # Display results
                    st.subheader("📊 Query Results")

                    if exec_result.get('data'):
                        df = pd.DataFrame(exec_result['data'])

                        # Display row count
                        total_rows = exec_result['row_count']
                        st.info(f"📈 Returned {total_rows} row(s)")

                        # Add pagination for large datasets
                        if total_rows > 1000:
                            st.warning(f"⚠️ Large dataset detected ({total_rows:,} rows). Showing paginated results for better performance.")

                            # Pagination controls
                            rows_per_page = st.selectbox(
                                "Rows per page:",
                                options=[100, 500, 1000, 5000],
                                index=1
                            )

                            total_pages = (total_rows - 1) // rows_per_page + 1
                            page = st.number_input(
                                f"Page (1-{total_pages}):",
                                min_value=1,
                                max_value=total_pages,
                                value=1
                            )

                            # Calculate slice
                            start_idx = (page - 1) * rows_per_page
                            end_idx = min(start_idx + rows_per_page, total_rows)

                            # Display paginated data
                            st.dataframe(
                                df.iloc[start_idx:end_idx],
                                use_container_width=True
                            )
                            st.caption(f"Showing rows {start_idx + 1:,} to {end_idx:,} of {total_rows:,}")

                            # Download full dataset option
                            csv = df.to_csv(index=False)
                            st.download_button(
                                label="📥 Download Full Dataset (CSV)",
                                data=csv,
                                file_name="query_results.csv",
                                mime="text/csv"
                            )
                        else:
                            # Display full dataset for smaller results
                            st.dataframe(df, use_container_width=True)

                        # Auto-visualization
                        if auto_visualize and len(df) > 0:
                            fig = create_visualization(df, st.session_state.get('last_query', ''))
                            if fig:
                                st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("Query executed successfully but returned no rows")
                else:
                    st.error(f"❌ Query execution failed: {exec_result.get('error', 'Unknown error')}")

            st.markdown("---")

        # Display RAG context
        if show_rag_context and result.get('rag_context'):
            display_rag_context(result['rag_context'])

        # Display thought process
        if show_thought_process and result.get('thought_process'):
            display_thought_process(result['thought_process'])

        # SQL EDIT & RE-EXECUTE SECTION
        st.subheader("✏️ Edit & Re-execute SQL")

        # Check if there are multiple queries
        has_multiple_queries = result.get('multiple_queries', False)
        all_sql_queries = result.get('all_sql_queries', [result.get('sql')])

        if has_multiple_queries and len(all_sql_queries) > 1:
            st.info(f"💡 {len(all_sql_queries)} queries were generated and executed. You can edit and re-execute them below.")

            # Display all queries in expandable sections
            for idx, sql_query in enumerate(all_sql_queries, 1):
                with st.expander(f"📋 Query {idx} of {len(all_sql_queries)}", expanded=(idx == 1)):
                    st.code(sql_query, language='sql')
        else:
            st.info("💡 The generated SQL was executed. You can edit and re-execute it below if needed.")

        # Editable SQL text area
        edited_sql = st.text_area(
            "Edit SQL Query:" if not has_multiple_queries else f"Edit Combined SQL ({len(all_sql_queries)} queries):",
            value=st.session_state.get('edited_sql', result['sql']),
            height=200,
            key='sql_editor',
            help="Edit the SQL query if something is missing, then click Re-execute"
        )

        # Update session state
        st.session_state['edited_sql'] = edited_sql
        st.session_state['all_sql_queries'] = all_sql_queries

        # Buttons for SQL execution
        col1, col2, col3 = st.columns([1, 1, 3])

        with col1:
            execute_sql_button = st.button("🔄 Re-execute SQL", type="primary", key='execute_sql')

        with col2:
            reset_sql_button = st.button("↩️ Reset to Original", key='reset_sql')

        with col3:
            clear_all_button = st.button("🗑️ Clear All", key='clear_all')

        if reset_sql_button:
            st.session_state['edited_sql'] = result['sql']
            st.rerun()

        if clear_all_button:
            # Clear all session state
            for key in ['query_result', 'edited_sql', 'last_query', 'sql_executed', 'execution_result']:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()

        # Execute the edited SQL
        if execute_sql_button:
            with st.spinner("⚙️ Executing SQL..."):
                try:
                    # Check if we have multiple queries to execute
                    has_multiple = st.session_state.get('all_sql_queries') and len(st.session_state.get('all_sql_queries', [])) > 1

                    if has_multiple:
                        # Execute multiple queries
                        all_queries = st.session_state.get('all_sql_queries', [])
                        all_exec_results = []
                        total_time = 0

                        for idx, sql_query in enumerate(all_queries, 1):
                            logger.info(f"Executing query {idx}/{len(all_queries)}")
                            exec_result = system['db_tools'].sql_db_query(sql_query)
                            exec_result['query_number'] = idx
                            exec_result['sql'] = sql_query
                            total_time += exec_result.get('execution_time', 0)
                            all_exec_results.append(exec_result)

                        # Store multiple results
                        st.session_state['sql_executed'] = True
                        st.session_state['multiple_execution'] = True
                        st.session_state['execution_results'] = all_exec_results
                        st.session_state['total_execution_time'] = total_time

                        # Save first successful query to database
                        for exec_result in all_exec_results:
                            if exec_result.get('success'):
                                try:
                                    query_id = user_db.save_query(
                                        username=username,
                                        question=st.session_state.get('last_query', ''),
                                        generated_sql=result.get('sql', ''),
                                        executed_sql=exec_result['sql'],
                                        results=pd.DataFrame(exec_result.get('data', [])) if exec_result.get('data') else None,
                                        result_count=exec_result.get('row_count', 0),
                                        iterations=result.get('iterations', 0),
                                        tables_used=result.get('relevant_tables', [])
                                    )
                                    st.session_state['current_query_id'] = query_id
                                    break
                                except Exception as db_error:
                                    logger.error(f"Error saving query to database: {db_error}")
                    else:
                        # Execute single query (original behavior)
                        exec_result = system['db_tools'].sql_db_query(edited_sql)

                        # Store execution result in session state
                        st.session_state['sql_executed'] = True
                        st.session_state['multiple_execution'] = False
                        st.session_state['execution_result'] = exec_result

                        # Save query to database
                        if exec_result.get('success'):
                            try:
                                query_id = user_db.save_query(
                                    username=username,
                                    question=st.session_state.get('last_query', ''),
                                    generated_sql=result.get('sql', ''),
                                    executed_sql=edited_sql,
                                    results=pd.DataFrame(exec_result.get('data', [])) if exec_result.get('data') else None,
                                    result_count=exec_result.get('row_count', 0),
                                    iterations=result.get('iterations', 0),
                                    tables_used=result.get('relevant_tables', [])
                                )
                                st.session_state['current_query_id'] = query_id
                            except Exception as db_error:
                                logger.error(f"Error saving query to database: {db_error}")

                except Exception as exec_error:
                    st.session_state['sql_executed'] = True
                    st.session_state['multiple_execution'] = False
                    st.session_state['execution_result'] = {
                        'success': False,
                        'error': str(exec_error)
                    }

        # Display execution results if available
        if st.session_state.get('sql_executed'):
            # Check if multiple queries were executed
            if st.session_state.get('multiple_execution'):
                # Display multiple query results
                all_exec_results = st.session_state.get('execution_results', [])
                total_time = st.session_state.get('total_execution_time', 0)

                st.success(f"✅ All queries executed! Total time: {total_time:.2f}s")
                st.subheader(f"📊 Results from {len(all_exec_results)} Queries")

                # Display each query result in a separate section
                for exec_result in all_exec_results:
                    query_num = exec_result.get('query_number', 1)
                    with st.expander(f"📋 Query {query_num} Results", expanded=True):
                        # Show SQL
                        st.code(exec_result.get('sql', ''), language='sql')

                        if exec_result.get('success'):
                            st.success(f"✅ Executed in {exec_result.get('execution_time', 0):.2f}s")

                            if exec_result.get('data'):
                                df = pd.DataFrame(exec_result['data'])
                                total_rows = exec_result['row_count']
                                st.info(f"📈 Returned {total_rows:,} row(s)")

                                # Add pagination for large datasets
                                if total_rows > 1000:
                                    st.warning(f"⚠️ Large dataset ({total_rows:,} rows). Showing paginated results.")

                                    # Use timestamp to ensure unique keys between auto-exec and re-exec
                                    import time
                                    unique_id = int(time.time() * 1000) % 10000

                                    rows_per_page = st.selectbox(
                                        "Rows per page:",
                                        options=[100, 500, 1000, 5000],
                                        index=1,
                                        key=f'rows_per_page_{query_num}_{unique_id}'
                                    )

                                    total_pages = (total_rows - 1) // rows_per_page + 1
                                    page = st.number_input(
                                        f"Page (1-{total_pages}):",
                                        min_value=1,
                                        max_value=total_pages,
                                        value=1,
                                        key=f'page_{query_num}_{unique_id}'
                                    )

                                    start_idx = (page - 1) * rows_per_page
                                    end_idx = min(start_idx + rows_per_page, total_rows)

                                    st.dataframe(
                                        df.iloc[start_idx:end_idx],
                                        use_container_width=True
                                    )
                                    st.caption(f"Showing rows {start_idx + 1:,} to {end_idx:,} of {total_rows:,}")

                                    csv = df.to_csv(index=False)
                                    st.download_button(
                                        label=f"📥 Download Query {query_num} (CSV)",
                                        data=csv,
                                        file_name=f"query_{query_num}_results.csv",
                                        mime="text/csv",
                                        key=f'download_{query_num}_{unique_id}'
                                    )
                                else:
                                    st.dataframe(df, use_container_width=True)

                                    csv = df.to_csv(index=False)
                                    import time
                                    unique_id = int(time.time() * 1000) % 10000
                                    st.download_button(
                                        label=f"📥 Download Query {query_num} (CSV)",
                                        data=csv,
                                        file_name=f"query_{query_num}_results.csv",
                                        mime="text/csv",
                                        key=f'download_else_{query_num}_{unique_id}'
                                    )

                                # Auto-visualization
                                if auto_visualize and len(df) > 0:
                                    fig = create_visualization(df, f"Query {query_num}")
                                    if fig:
                                        st.plotly_chart(fig, use_container_width=True)
                            else:
                                st.info("Query executed successfully but returned no rows")
                        else:
                            st.error(f"❌ Query failed: {exec_result.get('error', 'Unknown error')}")

            elif st.session_state.get('execution_result'):
                # Single query result (re-execution or original)
                exec_result = st.session_state['execution_result']

                if exec_result.get('success'):
                    st.success(f"✅ Query executed successfully in {exec_result.get('execution_time', 0)}s!")

                    # Display results
                    st.subheader("📊 Query Results")

                    if exec_result.get('data'):
                        df = pd.DataFrame(exec_result['data'])

                        # Display row count
                        total_rows = exec_result['row_count']
                        st.info(f"📈 Returned {total_rows} row(s)")

                        # Add pagination for large datasets
                        if total_rows > 1000:
                            st.warning(f"⚠️ Large dataset detected ({total_rows:,} rows). Showing paginated results for better performance.")

                            # Pagination controls with unique keys for re-execution
                            rows_per_page = st.selectbox(
                                "Rows per page:",
                                options=[100, 500, 1000, 5000],
                                index=1,
                                key='reexec_rows_per_page_single'
                            )

                            total_pages = (total_rows - 1) // rows_per_page + 1
                            page = st.number_input(
                                f"Page (1-{total_pages}):",
                                min_value=1,
                                max_value=total_pages,
                                value=1,
                                key='reexec_page_single'
                            )

                            # Calculate slice
                            start_idx = (page - 1) * rows_per_page
                            end_idx = min(start_idx + rows_per_page, total_rows)

                            # Display paginated data
                            st.dataframe(
                                df.iloc[start_idx:end_idx],
                                use_container_width=True
                            )
                            st.caption(f"Showing rows {start_idx + 1:,} to {end_idx:,} of {total_rows:,}")

                            # Download full dataset option
                            csv = df.to_csv(index=False)
                            st.download_button(
                                label="📥 Download Full Dataset (CSV)",
                                data=csv,
                                file_name="query_results.csv",
                                mime="text/csv",
                                key='reexec_download_single'
                            )
                        else:
                            # Display full dataset for smaller results
                            st.dataframe(df, use_container_width=True)

                        # Auto-visualization
                        if auto_visualize and len(df) > 0:
                            fig = create_visualization(df, st.session_state.get('last_query', ''))
                        if fig:
                            st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("Query executed successfully but returned no rows")

                # Display metadata
                with st.expander("ℹ️ Query Metadata"):
                    st.json({
                        "iterations": result.get('iterations', 0),
                        "relevant_tables": result.get('relevant_tables', []),
                        "execution_time": exec_result.get('execution_time', 'N/A'),
                        "row_count": exec_result.get('row_count', 0)
                    })

                # Display feedback form if query was saved
                if 'current_query_id' in st.session_state and st.session_state['current_query_id']:
                    display_feedback_form(user_db, st.session_state['current_query_id'], username)

            else:
                st.error(f"❌ SQL Execution failed: {exec_result.get('error', 'Unknown error')}")
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: #666;'>
        🤖 RAG-Enhanced NLQ System | Powered by Multilingual MPNet Embeddings & ReAct Pattern
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()