# tableデータ
+-------------------+
| Tables_in_isuconp |
+-------------------+
| comments          |
| posts             |
| users             |
+-------------------+

## comments
### columns
+------------+-----------+------+-----+-------------------+-------------------+
| Field      | Type      | Null | Key | Default           | Extra             |
+------------+-----------+------+-----+-------------------+-------------------+
| id         | int       | NO   | PRI | NULL              | auto_increment    |
| post_id    | int       | NO   | MUL | NULL              |                   |
| user_id    | int       | NO   |     | NULL              |                   |
| comment    | text      | NO   |     | NULL              |                   |
| created_at | timestamp | NO   |     | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
+------------+-----------+------+-----+-------------------+-------------------+

### index
+----------+------------+---------------------------------+--------------+-------------+-----------+-------------+----------+--------+------+------------+---------+---------------+---------+------------+
| Table    | Non_unique | Key_name                        | Seq_in_index | Column_name | Collation | Cardinality | Sub_part | Packed | Null | Index_type | Comment | Index_comment | Visible | Expression |
+----------+------------+---------------------------------+--------------+-------------+-----------+-------------+----------+--------+------+------------+---------+---------------+---------+------------+
| comments |          0 | PRIMARY                         |            1 | id          | A         |       98910 |     NULL |   NULL |      | BTREE      |         |               | YES     | NULL       |
| comments |          1 | idx_comments_post_id_created_at |            1 | post_id     | A         |       10022 |     NULL |   NULL |      | BTREE      |         |               | YES     | NULL       |
| comments |          1 | idx_comments_post_id_created_at |            2 | created_at  | D         |       99079 |     NULL |   NULL |      | BTREE      |         |               | YES     | NULL       |
| comments |          1 | idx_comments_post_id            |            1 | post_id     | A         |       10164 |     NULL |   NULL |      | BTREE      |         |               | YES     | NULL       |
| comments |          1 | idx_comments_user_id            |            1 | user_id     | A         |         999 |     NULL |   NULL |      | BTREE      |         |               | YES     | NULL       |
+----------+------------+---------------------------------+--------------+-------------+-----------+-------------+----------+--------+------+------------+---------+---------------+---------+------------+

## posts
### columns
+------------+-------------+------+-----+-------------------+-------------------+
| Field      | Type        | Null | Key | Default           | Extra             |
+------------+-------------+------+-----+-------------------+-------------------+
| id         | int         | NO   | PRI | NULL              | auto_increment    |
| user_id    | int         | NO   |     | NULL              |                   |
| mime       | varchar(64) | NO   |     | NULL              |                   |
| imgdata    | mediumblob  | NO   |     | NULL              |                   |
| body       | text        | NO   |     | NULL              |                   |
| created_at | timestamp   | NO   | MUL | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
+------------+-------------+------+-----+-------------------+-------------------+

### index
+-------+------------+------------------------------+--------------+-------------+-----------+-------------+----------+--------+------+------------+---------+---------------+---------+------------+
| Table | Non_unique | Key_name                     | Seq_in_index | Column_name | Collation | Cardinality | Sub_part | Packed | Null | Index_type | Comment | Index_comment | Visible | Expression |
+-------+------------+------------------------------+--------------+-------------+-----------+-------------+----------+--------+------+------------+---------+---------------+---------+------------+
| posts |          0 | PRIMARY                      |            1 | id          | A         |       10150 |     NULL |   NULL |      | BTREE      |         |               | YES     | NULL       |
| posts |          1 | idx_posts_created_at         |            1 | created_at  | D         |       10062 |     NULL |   NULL |      | BTREE      |         |               | YES     | NULL       |
| posts |          1 | idx_posts_user_id_created_at |            1 | user_id     | A         |        1000 |     NULL |   NULL |      | BTREE      |         |               | YES     | NULL       |
| posts |          1 | idx_posts_user_id_created_at |            2 | created_at  | D         |       10088 |     NULL |   NULL |      | BTREE      |         |               | YES     | NULL       |
+-------+------------+------------------------------+--------------+-------------+-----------+-------------+----------+--------+------+------------+---------+---------------+---------+------------+

## users
### columns
+--------------+--------------+------+-----+-------------------+-------------------+
| Field        | Type         | Null | Key | Default           | Extra             |
+--------------+--------------+------+-----+-------------------+-------------------+
| id           | int          | NO   | PRI | NULL              | auto_increment    |
| account_name | varchar(64)  | NO   | UNI | NULL              |                   |
| passhash     | varchar(128) | NO   |     | NULL              |                   |
| authority    | tinyint(1)   | NO   |     | 0                 |                   |
| del_flg      | tinyint(1)   | NO   | MUL | 0                 |                   |
| created_at   | timestamp    | NO   |     | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
+--------------+--------------+------+-----+-------------------+-------------------+

### index
+-------+------------+--------------------------------+--------------+--------------+-----------+-------------+----------+--------+------+------------+---------+---------------+---------+------------+
| Table | Non_unique | Key_name                       | Seq_in_index | Column_name  | Collation | Cardinality | Sub_part | Packed | Null | Index_type | Comment | Index_comment | Visible | Expression |
+-------+------------+--------------------------------+--------------+--------------+-----------+-------------+----------+--------+------+------------+---------+---------------+---------+------------+
| users |          0 | PRIMARY                        |            1 | id           | A         |        1157 |     NULL |   NULL |      | BTREE      |         |               | YES     | NULL       |
| users |          0 | account_name                   |            1 | account_name | A         |        1157 |     NULL |   NULL |      | BTREE      |         |               | YES     | NULL       |
| users |          1 | idx_users_del_flg              |            1 | del_flg      | A         |           2 |     NULL |   NULL |      | BTREE      |         |               | YES     | NULL       |
| users |          1 | idx_users_account_name_del_flg |            1 | account_name | A         |        1157 |     NULL |   NULL |      | BTREE      |         |               | YES     | NULL       |
| users |          1 | idx_users_account_name_del_flg |            2 | del_flg      | A         |        1157 |     NULL |   NULL |      | BTREE      |         |               | YES     | NULL       |
+-------+------------+--------------------------------+--------------+--------------+-----------+-------------+----------+--------+------+------------+---------+---------------+---------+------------+
