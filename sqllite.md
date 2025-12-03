# Open interactive SQLite shell
sqlite3 askeverai_users.db

# View database statistics
sqlite3 askeverai_users.db "SELECT 
    (SELECT COUNT(*) FROM users) as users,
    (SELECT COUNT(*) FROM queries) as queries,
    (SELECT COUNT(*) FROM feedback) as feedback,
    (SELECT AVG(rating) FROM feedback) as avg_rating;"

# View full query details (including SQL and results)
sqlite3 askeverai_users.db -header -column "SELECT * FROM queries;"

# View user activity history
sqlite3 askeverai_users.db -header -column "
SELECT u.username, COUNT(q.id) as query_count, 
       AVG(f.rating) as avg_rating
FROM users u
LEFT JOIN queries q ON u.id = q.user_id
LEFT JOIN feedback f ON u.id = f.user_id
GROUP BY u.username;"

# Export to CSV
sqlite3 askeverai_users.db -csv -header "SELECT * FROM queries;" > queries_export.csv