# Database Schema Documentation

## Overview

**Database Type**: SQLite
**Database File**: `askeverai_users.db`
**Location**: Project root directory
**Auto-created**: Yes (on first run)

## Entity Relationship Diagram

```
┌─────────────────────────────┐
│         users               │
├─────────────────────────────┤
│ id (PK)                     │
│ username (UNIQUE)           │
│ created_at                  │
│ last_active                 │
└──────────┬──────────────────┘
           │
           │ 1:N
           │
           ├───────────────────────────────────┐
           │                                   │
           ▼                                   ▼
┌─────────────────────────────┐    ┌─────────────────────────────┐
│         queries             │    │        feedback             │
├─────────────────────────────┤    ├─────────────────────────────┤
│ id (PK)                     │    │ id (PK)                     │
│ user_id (FK) ────────────┐  │    │ query_id (FK) ──────────┐   │
│ username                 │  │    │ user_id (FK) ───────────┼─┐ │
│ question                 │  │    │ username                │ │ │
│ generated_sql            │  │    │ rating (1-5)            │ │ │
│ executed_sql             │  │    │ feedback_text           │ │ │
│ results (JSON)           │  │    │ created_at              │ │ │
│ result_count             │  │    └────────┬────────────────┘ │ │
│ iterations               │  │             │                  │ │
│ tables_used (JSON)       │  │             │ N:1              │ │
│ created_at               │  │             │                  │ │
└────────┬─────────────────┘  │             │                  │ │
         │                    │             └──────────────────┘ │
         │                    │                                  │
         └────────────────────┴──────────────────────────────────┘
```

## Table Details

### 1. users

Stores user account information and activity timestamps.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY, AUTOINCREMENT | Unique user identifier |
| `username` | TEXT | UNIQUE, NOT NULL | User's chosen username |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Account creation time |
| `last_active` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Last login/activity time |

**Indices**:
- `idx_users_username` on `username`

**Sample Data**:
```sql
id | username   | created_at          | last_active
---+------------+---------------------+---------------------
1  | john_doe   | 2025-12-03 10:00:00 | 2025-12-03 14:30:00
2  | jane_smith | 2025-12-03 11:00:00 | 2025-12-03 13:45:00
```

---

### 2. queries

Stores all user queries, generated SQL, and execution results.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY, AUTOINCREMENT | Unique query identifier |
| `user_id` | INTEGER | FOREIGN KEY (users.id), NOT NULL | User who ran the query |
| `username` | TEXT | NOT NULL | Username (denormalized for speed) |
| `question` | TEXT | NOT NULL | Natural language question |
| `generated_sql` | TEXT | NULL | AI-generated SQL query |
| `executed_sql` | TEXT | NULL | Final SQL executed (may differ if edited) |
| `results` | TEXT | NULL | Query results as JSON string |
| `result_count` | INTEGER | NULL | Number of rows returned |
| `iterations` | INTEGER | NULL | Number of AI agent iterations |
| `tables_used` | TEXT | NULL | JSON array of table names |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Query execution time |

**Indices**:
- `idx_queries_user_id` on `user_id`
- `idx_queries_created_at` on `created_at`

**Sample Data**:
```sql
id | user_id | username | question                          | result_count | created_at
---+---------+----------+-----------------------------------+--------------+--------------------
1  | 1       | john_doe | Show me total sales by category   | 4            | 2025-12-03 14:32:15
2  | 1       | john_doe | Top 10 products by revenue        | 10           | 2025-12-03 14:35:20
3  | 2       | jane_smith| List all transactions            | 150          | 2025-12-03 13:45:10
```

**JSON Fields**:

*results* - Array of result rows:
```json
[
  {"category_name": "Enterprise", "total_sales": 5243891.23},
  {"category_name": "Small Business", "total_sales": 3128456.78}
]
```

*tables_used* - Array of table names:
```json
["fact_transaction_detail", "dim_client_category"]
```

---

### 3. feedback

Stores user ratings and feedback for specific queries.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY, AUTOINCREMENT | Unique feedback identifier |
| `query_id` | INTEGER | FOREIGN KEY (queries.id), NOT NULL | Query being rated |
| `user_id` | INTEGER | FOREIGN KEY (users.id), NOT NULL | User providing feedback |
| `username` | TEXT | NOT NULL | Username (denormalized for speed) |
| `rating` | INTEGER | CHECK(rating >= 1 AND rating <= 5) | Star rating (1-5) |
| `feedback_text` | TEXT | NULL | Optional text feedback |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Feedback submission time |

**Indices**:
- `idx_feedback_query_id` on `query_id`

**Sample Data**:
```sql
id | query_id | user_id | username   | rating | feedback_text              | created_at
---+----------+---------+------------+--------+----------------------------+--------------------
1  | 1        | 1       | john_doe   | 5      | Excellent results!         | 2025-12-03 14:32:45
2  | 2        | 1       | john_doe   | 4      | Good but could be faster   | 2025-12-03 14:35:50
3  | 3        | 2       | jane_smith | 3      | NULL                       | 2025-12-03 13:45:30
```

---

## Relationships

### users ↔ queries (1:N)
- One user can have many queries
- Each query belongs to one user
- Foreign key: `queries.user_id` → `users.id`

### users ↔ feedback (1:N)
- One user can provide many feedback entries
- Each feedback belongs to one user
- Foreign key: `feedback.user_id` → `users.id`

### queries ↔ feedback (1:N)
- One query can have multiple feedback entries (though UI prevents duplicates in session)
- Each feedback entry relates to one query
- Foreign key: `feedback.query_id` → `queries.id`

---

## SQL Queries Examples

### Get User Statistics
```sql
SELECT
    u.username,
    COUNT(DISTINCT q.id) as total_queries,
    COUNT(DISTINCT f.id) as total_feedback,
    AVG(f.rating) as avg_rating
FROM users u
LEFT JOIN queries q ON u.id = q.user_id
LEFT JOIN feedback f ON u.id = f.user_id
GROUP BY u.id, u.username;
```

### Get Recent Queries with Feedback
```sql
SELECT
    q.id,
    q.question,
    q.result_count,
    q.created_at,
    f.rating,
    f.feedback_text
FROM queries q
LEFT JOIN feedback f ON q.id = f.query_id
WHERE q.username = 'john_doe'
ORDER BY q.created_at DESC
LIMIT 10;
```

### Get Queries Without Feedback
```sql
SELECT
    q.id,
    q.username,
    q.question,
    q.created_at
FROM queries q
LEFT JOIN feedback f ON q.id = f.query_id
WHERE f.id IS NULL
ORDER BY q.created_at DESC;
```

### Get Average Rating by User
```sql
SELECT
    u.username,
    COUNT(f.id) as feedback_count,
    AVG(f.rating) as avg_rating,
    MIN(f.rating) as min_rating,
    MAX(f.rating) as max_rating
FROM users u
JOIN feedback f ON u.id = f.user_id
GROUP BY u.id, u.username
ORDER BY avg_rating DESC;
```

### Get Most Active Users
```sql
SELECT
    username,
    COUNT(*) as query_count
FROM queries
GROUP BY username
ORDER BY query_count DESC
LIMIT 10;
```

### Get Queries by Rating
```sql
SELECT
    f.rating,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM feedback), 2) as percentage
FROM feedback f
GROUP BY f.rating
ORDER BY f.rating DESC;
```

---

## Data Types

### JSON Fields

**queries.results**:
- Stores pandas DataFrame as JSON
- Format: `[{col1: val1, col2: val2}, ...]`
- Used for potential result re-display or analysis

**queries.tables_used**:
- Stores list of PostgreSQL tables accessed
- Format: `["table1", "table2"]`
- Used for query complexity analysis

---

## Database Operations

### Create Database
```python
from user_database import UserDatabase
db = UserDatabase()  # Auto-creates tables
```

### Add User
```python
user_id = db.add_user("john_doe")
```

### Save Query
```python
query_id = db.save_query(
    username="john_doe",
    question="Show me total sales",
    generated_sql="SELECT ...",
    executed_sql="SELECT ...",
    results=dataframe,
    result_count=10,
    iterations=3,
    tables_used=["fact_transaction_detail"]
)
```

### Save Feedback
```python
feedback_id = db.save_feedback(
    query_id=42,
    username="john_doe",
    rating=5,
    feedback_text="Excellent!"
)
```

### Get User History
```python
history = db.get_user_history("john_doe", limit=10)
```

---

## Performance Considerations

### Indices
- All foreign keys are indexed
- Username indexed for quick lookups
- created_at indexed for time-based queries

### Query Optimization
- Username denormalized in queries and feedback tables
- Avoids JOIN for common queries
- Trade-off: slight data redundancy for speed

### Database Size
- SQLite efficient for thousands of queries
- JSON storage compact but not searchable
- Consider archiving old queries if database grows large

---

## Backup & Maintenance

### Backup Database
```bash
# Simple file copy
cp askeverai_users.db askeverai_users_backup_$(date +%Y%m%d).db

# Or use SQLite dump
sqlite3 askeverai_users.db .dump > backup.sql
```

### Restore Database
```bash
# From file copy
cp askeverai_users_backup_20251203.db askeverai_users.db

# From SQL dump
sqlite3 new_database.db < backup.sql
```

### Vacuum Database
```bash
sqlite3 askeverai_users.db "VACUUM;"
```

### Check Database Integrity
```bash
sqlite3 askeverai_users.db "PRAGMA integrity_check;"
```

---

## Security Notes

1. **No Sensitive Data**: No passwords or sensitive authentication data stored
2. **Local Storage**: Database never transmitted over network
3. **Git Ignored**: `.gitignore` excludes `*.db` files
4. **File Permissions**: Standard file permissions apply
5. **SQL Injection**: Parameterized queries prevent injection

---

## Migration Notes

### Future Schema Changes

If you need to add columns:
```sql
ALTER TABLE queries ADD COLUMN new_column TEXT;
```

If you need to add tables:
```python
# Update UserDatabase.initialize_database()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS new_table (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ...
    )
''')
```

### Version Tracking
Consider adding a schema version table:
```sql
CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO schema_version (version) VALUES (1);
```

---

## Troubleshooting

### Database Locked Error
```python
# Increase timeout
conn = sqlite3.connect('askeverai_users.db', timeout=30)
```

### Corruption
```bash
# Check integrity
sqlite3 askeverai_users.db "PRAGMA integrity_check;"

# If corrupt, try recovery
sqlite3 askeverai_users.db ".recover" | sqlite3 recovered.db
```

### Size Issues
```sql
-- Check database size
SELECT page_count * page_size as size_bytes
FROM pragma_page_count(), pragma_page_size();

-- Check table sizes
SELECT
    name,
    SUM(pgsize) as size_bytes
FROM dbstat
GROUP BY name
ORDER BY size_bytes DESC;
```

---

**Schema Version**: 1.0
**Last Updated**: December 3, 2025
**Compatibility**: SQLite 3.0+
