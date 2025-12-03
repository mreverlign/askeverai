"""
SQLite database module for storing user queries, results, and feedback.
"""
import sqlite3
from datetime import datetime
from typing import Optional, Dict, List, Any
import json
import os


class UserDatabase:
    """Manages user data, queries, and feedback in SQLite."""

    def __init__(self, db_path: str = "askeverai_users.db"):
        """Initialize database connection and create tables if needed."""
        self.db_path = db_path
        self.conn = None
        self.initialize_database()

    def initialize_database(self):
        """Create database tables if they don't exist."""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        cursor = self.conn.cursor()

        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Queries table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS queries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                question TEXT NOT NULL,
                generated_sql TEXT,
                executed_sql TEXT,
                results TEXT,
                result_count INTEGER,
                iterations INTEGER,
                tables_used TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')

        # Feedback table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                rating INTEGER CHECK(rating >= 1 AND rating <= 5),
                feedback_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (query_id) REFERENCES queries (id),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')

        # Create indices for performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_queries_user_id ON queries(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_queries_created_at ON queries(created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_feedback_query_id ON feedback(query_id)')

        self.conn.commit()

    def add_user(self, username: str) -> int:
        """Add a new user or return existing user ID."""
        cursor = self.conn.cursor()

        # Check if user exists
        cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
        result = cursor.fetchone()

        if result:
            user_id = result[0]
            # Update last active time
            cursor.execute(
                'UPDATE users SET last_active = ? WHERE id = ?',
                (datetime.now(), user_id)
            )
            self.conn.commit()
            return user_id
        else:
            # Insert new user
            cursor.execute(
                'INSERT INTO users (username) VALUES (?)',
                (username,)
            )
            self.conn.commit()
            return cursor.lastrowid

    def save_query(
        self,
        username: str,
        question: str,
        generated_sql: Optional[str] = None,
        executed_sql: Optional[str] = None,
        results: Optional[Any] = None,
        result_count: Optional[int] = None,
        iterations: Optional[int] = None,
        tables_used: Optional[List[str]] = None
    ) -> int:
        """Save a query and its results to the database."""
        user_id = self.add_user(username)
        cursor = self.conn.cursor()

        # Convert results to JSON string if it's a dataframe or dict
        results_json = None
        if results is not None:
            try:
                if hasattr(results, 'to_json'):  # pandas DataFrame
                    results_json = results.to_json(orient='records', date_format='iso')
                else:
                    results_json = json.dumps(results)
            except Exception as e:
                results_json = str(results)

        # Convert tables_used list to JSON string
        tables_json = json.dumps(tables_used) if tables_used else None

        cursor.execute('''
            INSERT INTO queries
            (user_id, username, question, generated_sql, executed_sql, results,
             result_count, iterations, tables_used)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id, username, question, generated_sql, executed_sql,
            results_json, result_count, iterations, tables_json
        ))

        self.conn.commit()
        return cursor.lastrowid

    def save_feedback(
        self,
        query_id: int,
        username: str,
        rating: int,
        feedback_text: Optional[str] = None
    ) -> int:
        """Save user feedback for a query."""
        user_id = self.add_user(username)
        cursor = self.conn.cursor()

        cursor.execute('''
            INSERT INTO feedback
            (query_id, user_id, username, rating, feedback_text)
            VALUES (?, ?, ?, ?, ?)
        ''', (query_id, user_id, username, rating, feedback_text))

        self.conn.commit()
        return cursor.lastrowid

    def get_user_history(self, username: str, limit: int = 10) -> List[Dict]:
        """Get query history for a user."""
        cursor = self.conn.cursor()

        cursor.execute('''
            SELECT q.id, q.question, q.generated_sql, q.executed_sql,
                   q.result_count, q.created_at, f.rating, f.feedback_text
            FROM queries q
            LEFT JOIN feedback f ON q.id = f.query_id
            WHERE q.username = ?
            ORDER BY q.created_at DESC
            LIMIT ?
        ''', (username, limit))

        columns = ['id', 'question', 'generated_sql', 'executed_sql',
                   'result_count', 'created_at', 'rating', 'feedback_text']

        results = []
        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))

        return results

    def get_query_by_id(self, query_id: int) -> Optional[Dict]:
        """Get a specific query by ID."""
        cursor = self.conn.cursor()

        cursor.execute('''
            SELECT q.id, q.user_id, q.username, q.question, q.generated_sql,
                   q.executed_sql, q.results, q.result_count, q.iterations,
                   q.tables_used, q.created_at
            FROM queries q
            WHERE q.id = ?
        ''', (query_id,))

        row = cursor.fetchone()
        if not row:
            return None

        columns = ['id', 'user_id', 'username', 'question', 'generated_sql',
                   'executed_sql', 'results', 'result_count', 'iterations',
                   'tables_used', 'created_at']

        return dict(zip(columns, row))

    def get_all_users(self) -> List[Dict]:
        """Get all users."""
        cursor = self.conn.cursor()

        cursor.execute('''
            SELECT username, created_at, last_active,
                   (SELECT COUNT(*) FROM queries WHERE username = users.username) as query_count
            FROM users
            ORDER BY last_active DESC
        ''')

        columns = ['username', 'created_at', 'last_active', 'query_count']

        results = []
        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))

        return results

    def get_statistics(self) -> Dict:
        """Get overall statistics."""
        cursor = self.conn.cursor()

        # Total users
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]

        # Total queries
        cursor.execute('SELECT COUNT(*) FROM queries')
        total_queries = cursor.fetchone()[0]

        # Total feedback
        cursor.execute('SELECT COUNT(*) FROM feedback')
        total_feedback = cursor.fetchone()[0]

        # Average rating
        cursor.execute('SELECT AVG(rating) FROM feedback')
        avg_rating = cursor.fetchone()[0] or 0

        return {
            'total_users': total_users,
            'total_queries': total_queries,
            'total_feedback': total_feedback,
            'average_rating': round(avg_rating, 2)
        }

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
