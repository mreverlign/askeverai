import streamlit as st
import pandas as pd
from llm_client import LLMClient
from database_tools import DatabaseTools
from rag_metadata_embedder_focused import FocusedColumnEmbedder as MetadataEmbedder
from rag_enhanced_agent import RAGEnhancedReActAgent
from config import Config
from pathlib import Path
import logging
from user_database import UserDatabase
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Filter out WebSocket closed errors
class WebSocketErrorFilter(logging.Filter):
    def filter(self, record):
        message = str(record.getMessage())
        return not ('WebSocketClosedError' in message or
                   'Stream is closed' in message)

logging.getLogger('tornado.application').addFilter(WebSocketErrorFilter())
logging.getLogger('asyncio').addFilter(WebSocketErrorFilter())
logging.getLogger('tornado.general').addFilter(WebSocketErrorFilter())

# Page config
st.set_page_config(
    page_title="AskEver AI",
    page_icon="💬",
    layout="centered"
)

# Modern Marketing UI CSS - Inspired by Notion, Linear, Vercel
st.markdown("""
<style>
    /* Import Modern Font */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    /* Global Reset */
    * {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
    }

    /* Clean White Background */
    .main {
        background: #ffffff;
        padding: 2rem 1rem;
    }

    /* Hide Streamlit Elements */
    #MainMenu, footer, header {visibility: hidden;}

    /* Elegant Header */
    .app-header {
        text-align: center;
        padding: 3rem 1rem 2rem;
        margin-bottom: 2rem;
    }

    .app-title {
        font-size: 3rem;
        font-weight: 700;
        background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #ec4899 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        margin-bottom: 1rem;
        letter-spacing: -0.03em;
        line-height: 1.2;
    }

    .app-subtitle {
        font-size: 1.125rem;
        color: #64748b;
        font-weight: 500;
        max-width: 600px;
        margin: 0 auto;
    }

    /* Top Bar - User & Logout */
    .top-bar {
        position: fixed;
        top: 0;
        right: 0;
        left: 0;
        background: white;
        padding: 1rem 2rem;
        display: flex;
        justify-content: flex-end;
        align-items: center;
        gap: 1rem;
        border-bottom: 1px solid #f1f5f9;
        z-index: 1000;
    }

    .user-badge {
        background: #f1f5f9;
        color: #475569;
        padding: 0.5rem 1rem;
        border-radius: 100px;
        font-size: 0.875rem;
        font-weight: 600;
        border: 1px solid #e2e8f0;
    }

    .logout-btn {
        background: white;
        color: #64748b;
        padding: 0.5rem 1rem;
        border-radius: 100px;
        font-size: 0.875rem;
        font-weight: 600;
        border: 1px solid #e2e8f0;
        cursor: pointer;
        transition: all 0.2s;
    }

    .logout-btn:hover {
        background: #f8fafc;
        border-color: #cbd5e1;
    }

    /* Query Bubble - Gradient Style */
    .message-bubble {
        background: white;
        padding: 1rem 1.5rem;
        border-radius: 16px;
        margin: 1.5rem 0;
        border: 1px solid #f1f5f9;
    }

    .user-query {
        background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
        color: white !important;
        font-size: 1.125rem;
        font-weight: 500;
        border: none;
        box-shadow: 0 4px 20px rgba(99, 102, 241, 0.25);
    }

    /* Ensure All Text is Visible */
    .stMarkdown {
        color: #0f172a !important;
    }

    .stMarkdown p, .stMarkdown div, .stMarkdown span {
        color: #0f172a !important;
    }

    .stMarkdown strong, .stMarkdown b {
        color: #0f172a !important;
        font-weight: 700 !important;
    }

    .section-header {
        font-size: 0.8125rem;
        font-weight: 700;
        color: #64748b !important;
        margin: 1.5rem 0 0.75rem 0;
        text-transform: uppercase;
        letter-spacing: 0.1em;
    }

    /* Beautiful Code Blocks */
    .stCodeBlock {
        background: #0f172a !important;
        border: 1px solid #1e293b !important;
        border-radius: 12px !important;
        margin: 1rem 0 !important;
        overflow: hidden;
    }

    .stCodeBlock code {
        color: #e2e8f0 !important;
        font-family: 'SF Mono', 'Monaco', 'Menlo', monospace !important;
        font-size: 0.875rem !important;
        line-height: 1.7 !important;
    }

    /* Modern Input Field */
    .stTextInput input {
        border-radius: 12px;
        border: 2px solid #e2e8f0;
        padding: 1rem 1.25rem;
        font-size: 1rem;
        background: white;
        color: #0f172a !important;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    }

    .stTextInput input::placeholder {
        color: #94a3b8;
    }

    .stTextInput input:focus {
        border-color: #6366f1;
        box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.1);
        outline: none;
    }

    /* Gradient Buttons */
    .stButton > button {
        border-radius: 12px;
        padding: 1rem 2rem;
        font-weight: 600;
        background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
        color: white !important;
        border: none;
        width: 100%;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        box-shadow: 0 4px 16px rgba(99, 102, 241, 0.3);
        font-size: 0.9375rem;
    }

    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 24px rgba(99, 102, 241, 0.4);
    }

    /* Logout button override - make it match user badge */
    .logout-button-container .stButton > button {
        background: #f1f5f9 !important;
        color: #475569 !important;
        padding: 0.5rem 1rem !important;
        border-radius: 100px !important;
        font-size: 0.875rem !important;
        font-weight: 600 !important;
        border: 1px solid #e2e8f0 !important;
        box-shadow: none !important;
        height: auto !important;
        white-space: nowrap !important;
        width: auto !important;
        min-width: auto !important;
    }

    .logout-button-container .stButton > button:hover {
        background: #e2e8f0 !important;
        transform: none !important;
        box-shadow: none !important;
    }

    /* Beautiful Stats Badges */
    .stats-badge {
        display: inline-block;
        background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
        color: #475569;
        padding: 0.5rem 1rem;
        border-radius: 100px;
        font-size: 0.875rem;
        font-weight: 600;
        margin-right: 0.75rem;
        margin-bottom: 0.5rem;
        border: 1px solid #e2e8f0;
    }

    /* Elegant Divider */
    .divider {
        height: 1px;
        background: linear-gradient(to right, transparent, #e2e8f0 20%, #e2e8f0 80%, transparent);
        margin: 2.5rem 0;
    }

    /* Beautiful Login Screen */
    .login-container {
        max-width: 420px;
        margin: 6rem auto;
        text-align: center;
    }

    .login-title {
        font-size: 2.5rem;
        font-weight: 700;
        background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #ec4899 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.75rem;
        letter-spacing: -0.03em;
    }

    .login-subtitle {
        color: #64748b;
        margin-bottom: 2.5rem;
        font-size: 1.0625rem;
    }

    /* Minimal Feedback Section */
    .feedback-section {
        background: #f8fafc;
        padding: 1.5rem;
        border-radius: 12px;
        margin-top: 1.5rem;
        border: 1px solid #f1f5f9;
    }

    /* Download Button - Success Style */
    .stDownloadButton > button {
        background: linear-gradient(135deg, #10b981 0%, #06b6d4 100%);
        color: white !important;
        border-radius: 12px;
        padding: 0.75rem 1.5rem;
        font-size: 0.875rem;
        font-weight: 600;
        border: none;
        box-shadow: 0 4px 16px rgba(16, 185, 129, 0.3);
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    }

    .stDownloadButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 6px 20px rgba(16, 185, 129, 0.4);
    }

    /* Clean Data Tables */
    .dataframe {
        border: 1px solid #f1f5f9 !important;
        border-radius: 12px !important;
        overflow: hidden;
        font-size: 0.875rem;
        color: #0f172a !important;
    }

    .dataframe th {
        background: #f8fafc !important;
        color: #475569 !important;
        font-weight: 600 !important;
        padding: 0.75rem !important;
    }

    .dataframe td {
        padding: 0.75rem !important;
        color: #0f172a !important;
    }

    /* Beautiful Alert Boxes */
    .stInfo {
        background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
        border-left: 3px solid #3b82f6;
        border-radius: 12px;
        color: #1e40af !important;
        padding: 1rem 1.25rem;
    }

    .stSuccess {
        background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
        border-left: 3px solid #10b981;
        border-radius: 12px;
        color: #065f46 !important;
        padding: 1rem 1.25rem;
    }

    .stError {
        background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
        border-left: 3px solid #ef4444;
        border-radius: 12px;
        color: #991b1b !important;
        padding: 1rem 1.25rem;
    }

    /* Minimal Expander */
    .streamlit-expanderHeader {
        background: #f8fafc;
        border: 1px solid #f1f5f9;
        border-radius: 12px;
        font-weight: 600;
        color: #475569 !important;
        padding: 0.875rem 1rem;
        transition: all 0.2s;
    }

    .streamlit-expanderHeader:hover {
        background: #f1f5f9;
    }

    /* Loading Spinner */
    .stSpinner > div {
        border-top-color: #6366f1 !important;
    }

    /* Logout Button - Secondary Style */
    .stButton > button[kind="secondary"] {
        background: #f8fafc;
        color: #475569 !important;
        border: 1px solid #e2e8f0;
        box-shadow: none;
    }

    .stButton > button[kind="secondary"]:hover {
        background: #f1f5f9;
        box-shadow: none;
    }

    /* Sidebar Styling */
    [data-testid="stSidebar"] {
        background: #fafafa;
        border-right: 1px solid #f1f5f9;
    }

    [data-testid="stSidebar"] .stMarkdown {
        color: #0f172a !important;
    }

    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {
        color: #0f172a !important;
        font-weight: 700;
    }

    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] div,
    [data-testid="stSidebar"] span {
        color: #0f172a !important;
    }

    /* Expander text in sidebar */
    [data-testid="stSidebar"] .streamlit-expanderHeader {
        color: #0f172a !important;
        background: white;
    }

    [data-testid="stSidebar"] .streamlit-expanderContent {
        background: white;
        border: 1px solid #f1f5f9;
        border-radius: 0 0 12px 12px;
    }

    /* Caption text */
    .caption, [data-testid="stCaptionContainer"], .stCaption {
        color: #64748b !important;
        font-size: 0.8125rem !important;
    }

    /* Recent queries heading */
    .sidebar-heading {
        font-size: 0.875rem;
        font-weight: 700;
        color: #0f172a !important;
        margin: 1.5rem 0 1rem 0;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
</style>
""", unsafe_allow_html=True)


def format_sql_for_display(sql):
    """Format SQL for better readability (PostgreSQL style)"""
    if not sql:
        return sql

    formatted = sql.strip()

    # Format keywords with proper spacing
    keywords = [
        'SELECT', 'FROM', 'WHERE', 'JOIN', 'LEFT JOIN', 'RIGHT JOIN',
        'INNER JOIN', 'GROUP BY', 'ORDER BY', 'HAVING', 'LIMIT', 'OFFSET',
        'AND', 'OR', 'AS', 'ON', 'IN', 'NOT', 'NULL', 'IS', 'UNION'
    ]

    for keyword in keywords:
        formatted = formatted.replace(f' {keyword} ', f'\n{keyword} ')
        formatted = formatted.replace(f' {keyword.lower()} ', f'\n{keyword} ')

    # Clean up extra spaces and empty lines
    lines = [line.strip() for line in formatted.split('\n') if line.strip()]
    formatted = '\n'.join(lines)

    return formatted


@st.cache_resource
def initialize_system():
    """Initialize all system components"""
    try:
        llm_client = LLMClient()
        db_tools = DatabaseTools(Config.DB_CONFIG)
        db_tools.connect()
        embedder = MetadataEmbedder()

        indices_dir = "./rag_indices_focused"
        if Path(indices_dir).exists():
            embedder.load_indices(indices_dir)
        else:
            embedder.load_and_embed_metadata("HighTower_Metadata(Metadata) (1).csv")
            embedder.load_and_embed_relationships("HighTower_Metadata(Relationships).csv")
            embedder.load_and_embed_datamodel("HighTower_Metadata(HighTower_Data_Model) (2).csv")
            embedder.save_indices(indices_dir)

        agent = RAGEnhancedReActAgent(llm_client, db_tools, embedder)
        user_db = UserDatabase()

        return {
            'agent': agent,
            'db_tools': db_tools,
            'user_db': user_db,
            'status': 'success'
        }

    except Exception as e:
        logger.error(f"Error initializing system: {e}")
        return {'status': 'error', 'error': str(e)}


def show_login():
    """Display login screen"""
    st.markdown("""
    <div class="login-container">
        <div class="login-title">AskEver AI</div>
        <div class="login-subtitle">Your intelligent data assistant</div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        username = st.text_input(
            "Enter your name:",
            placeholder="Your name",
            max_chars=50,
            label_visibility="collapsed"
        )
        if st.button("Get Started", type="primary", use_container_width=True):
            if username and username.strip():
                st.session_state['username'] = username.strip()
                st.session_state['chat_history'] = []
                st.rerun()
            else:
                st.error("Please enter your name")


def show_feedback(query_id, username, user_db):
    """Display feedback form"""
    st.markdown('<div class="feedback-section">', unsafe_allow_html=True)
    st.markdown('<p class="section-header">Rate this response:</p>', unsafe_allow_html=True)

    feedback_key = f"feedback_submitted_{query_id}"

    if not st.session_state.get(feedback_key, False):
        with st.form(f"feedback_form_{query_id}"):
            rating = st.radio(
                "Rating:",
                options=[1, 2, 3, 4, 5],
                format_func=lambda x: "⭐" * x,
                horizontal=True,
                label_visibility="collapsed"
            )

            feedback_text = st.text_area(
                "Comments (optional):",
                placeholder="Tell us what worked well or what could be improved...",
                height=80,
                label_visibility="collapsed"
            )

            submit = st.form_submit_button("Submit Feedback", type="primary")

            if submit:
                try:
                    user_db.save_feedback(
                        query_id=query_id,
                        username=username,
                        rating=rating,
                        feedback_text=feedback_text.strip() if feedback_text.strip() else None
                    )
                    st.session_state[feedback_key] = True
                    st.success(f"Thank you for your feedback! (Rating: {'⭐' * rating})")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error saving feedback: {str(e)}")
                    logger.error(f"Feedback error: {e}")
    else:
        st.success("Feedback submitted")

    st.markdown('</div>', unsafe_allow_html=True)


def main():
    # Check for username
    if 'username' not in st.session_state or not st.session_state.get('username'):
        show_login()
        st.stop()

    username = st.session_state['username']

    # Initialize session state
    if 'chat_history' not in st.session_state:
        st.session_state['chat_history'] = []

    if 'last_processed_query' not in st.session_state:
        st.session_state['last_processed_query'] = ''

    # Top bar with username
    col1, col2, col3 = st.columns([1, 5, 1])

    with col3:
        st.markdown(f'<div class="user-badge">{username}</div>', unsafe_allow_html=True)

    # Header
    st.markdown("""
    <div class="app-header">
        <div class="app-title">AskEver AI</div>
        <div class="app-subtitle">Ask questions about your data in natural language</div>
    </div>
    """, unsafe_allow_html=True)

    # Initialize system
    if 'system' not in st.session_state:
        with st.spinner("Initializing..."):
            system = initialize_system()
            if system['status'] == 'error':
                st.error(f"Error: {system['error']}")
                st.stop()
            st.session_state['system'] = system

    system = st.session_state['system']
    user_db = system['user_db']

    # Sidebar with recent queries
    with st.sidebar:
        st.markdown('<p class="sidebar-heading">Recent Queries</p>', unsafe_allow_html=True)
        try:
            history = user_db.get_user_history(username, limit=10)
            if history:
                for h in history:
                    with st.expander(f"{h['question'][:50]}...", expanded=False):
                        st.markdown(f"**Date:** {h['created_at']}")
                        if h.get('rating'):
                            st.markdown(f"**Rating:** {'⭐' * h['rating']}")
                        if h.get('generated_sql'):
                            st.code(h['generated_sql'], language='sql')
            else:
                st.info("No recent queries yet")
        except Exception as e:
            logger.error(f"Error loading history: {e}")
            st.info("Unable to load recent queries")

    # Display chat history (only once per query)
    for idx, msg in enumerate(st.session_state['chat_history']):
        # User query
        st.markdown(f'<div class="message-bubble user-query">{msg["query"]}</div>', unsafe_allow_html=True)

        # SQL query (only if it exists and is not empty)
        if msg.get('sql') and msg['sql'].strip():
            st.markdown('<p class="section-header">Generated SQL (PostgreSQL):</p>', unsafe_allow_html=True)
            formatted_sql = format_sql_for_display(msg['sql'])
            st.code(formatted_sql, language='postgresql')

        # Results (only if data exists)
        if msg.get('data') is not None and not msg['data'].empty:
            st.markdown('<p class="section-header">Results:</p>', unsafe_allow_html=True)
            df = msg['data']

            # Stats
            st.markdown(
                f'<span class="stats-badge">{len(df):,} rows</span>'
                f'<span class="stats-badge">{len(df.columns)} columns</span>',
                unsafe_allow_html=True
            )

            # Data table
            if len(df) > 100:
                st.info(f"Showing first 100 of {len(df):,} rows")
                st.dataframe(df.head(100), use_container_width=True, hide_index=True)
            else:
                st.dataframe(df, use_container_width=True, hide_index=True)

            # Download button
            csv = df.to_csv(index=False)
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name=f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                key=f"download_{idx}"
            )

            # Feedback form (only for the latest message with results)
            if idx == len(st.session_state['chat_history']) - 1 and msg.get('query_id'):
                show_feedback(msg['query_id'], username, user_db)

        # Error
        if msg.get('error'):
            st.error(f"Error: {msg['error']}")

        # Divider
        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # Empty state
    if not st.session_state['chat_history']:
        st.markdown("""
        <div style='text-align: center; padding: 3rem 0; color: #64748b;'>
            <p style='font-size: 1.25rem; font-weight: 600; margin-bottom: 1rem; color: #0f172a;'>Welcome! Start by asking a question</p>
            <p style='font-size: 1rem;'>Try: "Show me total sales by category" or "What are the top 10 products?"</p>
        </div>
        """, unsafe_allow_html=True)

    # Input area
    st.markdown("---")

    query = st.text_input(
        "Your question:",
        placeholder="Type your question here...",
        key="user_input",
        label_visibility="collapsed"
    )

    col1, col2 = st.columns([3, 1])

    with col1:
        send = st.button("Ask", type="primary")

    with col2:
        if st.button("Clear"):
            st.session_state['chat_history'] = []
            st.session_state['last_processed_query'] = ''
            st.rerun()

    # Process query (only once)
    if send and query:
        # Check if this exact query was just processed
        last_query = st.session_state.get('last_processed_query', '')

        if last_query != query:
            st.session_state['last_processed_query'] = query

            with st.spinner("Thinking..."):
                try:
                    # Generate SQL
                    result = system['agent'].process_query(query)

                    if result.get('success') and result.get('sql'):
                        # Execute SQL
                        exec_result = system['db_tools'].sql_db_query(result['sql'])

                        if exec_result.get('success'):
                            df = pd.DataFrame(exec_result['data']) if exec_result.get('data') else pd.DataFrame()

                            # Save to database
                            query_id = None
                            try:
                                query_id = user_db.save_query(
                                    username=username,
                                    question=query,
                                    generated_sql=result['sql'],
                                    executed_sql=result['sql'],
                                    results=df if not df.empty else None,
                                    result_count=len(df),
                                    iterations=result.get('iterations', 0),
                                    tables_used=result.get('relevant_tables', [])
                                )
                            except Exception as e:
                                logger.error(f"Error saving query: {e}")

                            # Add to history (only once)
                            st.session_state['chat_history'].append({
                                'query': query,
                                'sql': result['sql'],
                                'data': df,
                                'query_id': query_id
                            })
                        else:
                            st.session_state['chat_history'].append({
                                'query': query,
                                'sql': result.get('sql'),
                                'error': exec_result.get('error', 'Query execution failed')
                            })
                    else:
                        st.session_state['chat_history'].append({
                            'query': query,
                            'error': result.get('error', 'Could not generate SQL')
                        })

                except Exception as e:
                    logger.error(f"Error: {e}")
                    st.session_state['chat_history'].append({
                        'query': query,
                        'error': str(e)
                    })

            st.rerun()


if __name__ == "__main__":
    main()
