import datetime
import os
import time
import pathlib
import re
import shlex
import hashlib
import tempfile
import json
import base64
import logging

import flask
import MySQLdb.cursors
from flask_session import Session
from jinja2 import pass_eval_context
from markupsafe import Markup, escape
from pymemcache.client.base import Client as MemcacheClient

UPLOAD_LIMIT = 10 * 1024 * 1024  # 10mb
POSTS_PER_PAGE = 20


_config = None


def config():
    global _config
    if _config is None:
        _config = {
            "db": {
                "host": os.environ.get("ISUCONP_DB_HOST", "localhost"),
                "port": int(os.environ.get("ISUCONP_DB_PORT", "3306")),
                "user": os.environ.get("ISUCONP_DB_USER", "root"),
                "db": os.environ.get("ISUCONP_DB_NAME", "isuconp"),
            },
            "memcache": {
                "address": os.environ.get(
                    "ISUCONP_MEMCACHED_ADDRESS", "127.0.0.1:11211"
                ),
            },
            'otel': {
                'endpoint': os.getenv('OTEL_ENDPOINT', '18.183.232.7:4317'),
                'insecure': True,
                'export_interval_millis': int(os.getenv('OTEL_EXPORT_INTERVAL_MS', '5000')),
            },
        }
        password = os.environ.get("ISUCONP_DB_PASSWORD")
        if password:
            _config["db"]["passwd"] = password
    return _config


_db = None


def db():
    global _db
    if _db is None:
        conf = config()["db"].copy()
        conf["charset"] = "utf8mb4"
        conf["cursorclass"] = MySQLdb.cursors.DictCursor
        conf["autocommit"] = True
        _db = MySQLdb.connect(**conf)
    return _db


def db_initialize():
    cur = db().cursor()
    sqls = [
        "DELETE FROM users WHERE id > 1000",
        "DELETE FROM posts WHERE id > 10000",
        "DELETE FROM comments WHERE id > 100000",
        "UPDATE users SET del_flg = 0",
        "UPDATE users SET del_flg = 1 WHERE id % 50 = 0",
    ]
    for q in sqls:
        cur.execute(q)


_mcclient = None


def memcache():
    global _mcclient
    if _mcclient is None:
        conf = config()["memcache"]
        _mcclient = MemcacheClient(
            conf["address"], 
            no_delay=True, 
            default_noreply=False,
        )
    return _mcclient


from opentelemetry import trace, metrics
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.mysql import MySQLInstrumentor

def otel_setup(app):
    resource = Resource.create({"service.name": "isuconp"})
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=config()['otel']['endpoint'],
                insecure=config()['otel']['insecure'],
            )
        )
    )
    trace.set_tracer_provider(tracer_provider)

    metric_exporter = OTLPMetricExporter(
        endpoint=config()['otel']['endpoint'],
        insecure=config()['otel']['insecure'],
    )
    reader = PeriodicExportingMetricReader(
        metric_exporter,
        export_interval_millis=config()['otel']['export_interval_millis']
    )
    meter_provider = MeterProvider(metric_readers=[reader], resource=resource)
    metrics.set_meter_provider(meter_provider)

    FlaskInstrumentor().instrument_app(app)
    MySQLInstrumentor().instrument()

def log_setup(app):
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    fmt = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    handler.setFormatter(fmt)
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.DEBUG)

def try_login(account_name, password):
    cur = db().cursor()
    cur.execute(
        "SELECT * FROM users WHERE account_name = %s AND del_flg = 0", (account_name,)
    )
    user = cur.fetchone()

    if user and calculate_passhash(user["account_name"], password) == user["passhash"]:
        return user
    return None


def validate_user(account_name: str, password: str):
    if not re.match(r"[0-9a-zA-Z]{3,}", account_name):
        return False
    if not re.match(r"[0-9a-zA-Z_]{6,}", password):
        return False
    return True


def digest(src: str):
    src_bytes = src.encode('utf-8')
    hased_str = hashlib.sha512(src_bytes).hexdigest()
    return hased_str.strip()


def calculate_salt(account_name: str):
    return digest(account_name)


def calculate_passhash(account_name: str, password: str):
    return digest("%s:%s" % (password, calculate_salt(account_name)))


def get_session_user():
    user = flask.session.get("user")
    if user:
        # # セッションにキャッシュされたユーザー情報があるかチェック
        # cached_user = flask.session.get("user_data")
        # if cached_user:
        #     return cached_user
            
        # キャッシュがない場合のみDBアクセス
        cur = db().cursor()
        cur.execute("SELECT * FROM `users` WHERE `id` = %s", (user["id"],))
        user_data = cur.fetchone()
        
        ## セッションにキャッシュ
        #if user_data:
        #    flask.session["user_data"] = user_data
        #
        return user_data
    return None


def make_posts(results, all_comments=False):
    if not results:
        return []
    
    posts = []
    cursor = db().cursor()
    
    # 投稿IDとユーザーIDを事前に収集
    post_ids = [post["id"] for post in results]
    user_ids = list(set(post["user_id"] for post in results))
    
    # ユーザー情報を一括取得
    cursor.execute("SELECT * FROM `users` WHERE `id` IN %s", (user_ids,))
    users_dict = {user["id"]: user for user in cursor.fetchall()}
    
    # コメント数を一括取得
    cursor.execute(
        "SELECT post_id, COUNT(*) as count FROM comments WHERE post_id IN %s GROUP BY post_id",
        (post_ids,)
    )
    comment_counts = {row["post_id"]: row["count"] for row in cursor.fetchall()}
    
    # コメント情報を一括取得
    if all_comments:
        cursor.execute(
            "SELECT * FROM comments WHERE post_id IN %s ORDER BY post_id, created_at DESC",
            (post_ids,)
        )
    else:
        # 各投稿の最新3件のコメントを取得（ROW_NUMBER()を使用）
        cursor.execute("""
            SELECT * FROM (
                SELECT c.*,
                       ROW_NUMBER() OVER (PARTITION BY post_id ORDER BY created_at DESC) as rn
                FROM comments c
                WHERE post_id IN %s
            ) ranked
            WHERE rn <= 3
            ORDER BY post_id, created_at DESC
        """, (post_ids,))
    
    # コメントをpost_id別に分類し、ユーザーIDを収集
    comments_by_post = {}
    comment_user_ids = set()
    for comment in cursor.fetchall():
        post_id = comment["post_id"]
        if post_id not in comments_by_post:
            comments_by_post[post_id] = []
        comments_by_post[post_id].append(comment)
        comment_user_ids.add(comment["user_id"])
    
    # コメントユーザー情報を一括取得
    if comment_user_ids:
        cursor.execute("SELECT * FROM `users` WHERE `id` IN %s", (list(comment_user_ids),))
        comment_users_dict = {user["id"]: user for user in cursor.fetchall()}
    else:
        comment_users_dict = {}
    
    # データを組み立て
    for post in results:
        post["comment_count"] = comment_counts.get(post["id"], 0)
        post["user"] = users_dict.get(post["user_id"])
        
        if not post["user"]:
            continue
            
        comments = comments_by_post.get(post["id"], [])
        for comment in comments:
            comment["user"] = comment_users_dict.get(comment["user_id"])
        
        if not all_comments:
            comments.reverse()
        post["comments"] = comments
        
        if not post["user"]["del_flg"]:
            posts.append(post)
        
        if len(posts) >= POSTS_PER_PAGE:
            break
    
    return posts


# app setup
static_path = pathlib.Path(__file__).resolve().parent.parent / "public"
app = flask.Flask(__name__, static_folder=str(static_path), static_url_path="")
# app.debug = True

otel_setup(app)
log_setup(app)

# Flask-Session
app.config["SESSION_TYPE"] = "memcached"
app.config["SESSION_MEMCACHED"] = memcache()
Session(app)


@app.template_global()
def image_url(post):
    ext = ""
    mime = post["mime"]
    if mime == "image/jpeg":
        ext = ".jpg"
    elif mime == "image/png":
        ext = ".png"
    elif mime == "image/gif":
        ext = ".gif"

    return "/image/%s%s" % (post["id"], ext)


# http://flask.pocoo.org/snippets/28/
_paragraph_re = re.compile(r"(?:\r\n|\r|\n){2,}")


@app.template_filter()
@pass_eval_context
def nl2br(eval_ctx, value):
    result = "\n\n".join(
        "<p>%s</p>" % p.replace("\n", "<br>\n")
        for p in _paragraph_re.split(escape(value))
    )
    if eval_ctx.autoescape:
        result = Markup(result)
    return result


# endpoints


@app.route("/initialize")
def get_initialize():
    db_initialize()
    
    # 既存の画像保存ディレクトリの中身を削除
    upload_image_dir = "/home/isucon/upload_images"
    # ディレクトリ内のファイルを削除（画像ファイルのみ想定）
    for filename in os.listdir(upload_image_dir):
        file_path = os.path.join(upload_image_dir, filename)
        os.remove(file_path)
    app.logger.info(f"Cleared contents of upload image directory: {upload_image_dir}")
    
    # publicディレクトリも念のため作成
    public_image_dir = pathlib.Path(__file__).resolve().parent.parent / "public" / "images"
    public_image_dir.mkdir(exist_ok=True)
    
    return ""


@app.route("/login")
def get_login():
    if get_session_user():
        return flask.redirect("/")
    return flask.render_template("login.html", me=None)


@app.route("/login", methods=["POST"])
def post_login():
    if get_session_user():
        return flask.redirect("/")

    user = try_login(flask.request.form["account_name"], flask.request.form["password"])
    
    # ログイン処理を意図的に遅延させてCPUリソース競合を回避
    time.sleep(0.2)  # 200ms遅延
    
    if user:
        flask.session["user"] = {"id": user["id"]}
        flask.session["user_data"] = user  # ユーザー情報をキャッシュ
        flask.session["csrf_token"] = os.urandom(8).hex()
        return flask.redirect("/")

    flask.flash("アカウント名かパスワードが間違っています")
    return flask.redirect("/login")


@app.route("/register")
def get_register():
    if get_session_user():
        return flask.redirect("/")
    return flask.render_template("register.html", me=None)


@app.route("/register", methods=["POST"])
def post_register():
    if get_session_user():
        return flask.redirect("/")

    account_name = flask.request.form["account_name"]
    password = flask.request.form["password"]
    if not validate_user(account_name, password):
        flask.flash(
            "アカウント名は3文字以上、パスワードは6文字以上である必要があります"
        )
        return flask.redirect("/register")

    cursor = db().cursor()
    cursor.execute("SELECT 1 FROM users WHERE `account_name` = %s", (account_name,))
    user = cursor.fetchone()
    if user:
        flask.flash("アカウント名がすでに使われています")
        return flask.redirect("/register")

    query = "INSERT INTO `users` (`account_name`, `passhash`) VALUES (%s, %s)"
    cursor.execute(query, (account_name, calculate_passhash(account_name, password)))

    flask.session["user"] = {"id": cursor.lastrowid}
    flask.session["csrf_token"] = os.urandom(8).hex()
    return flask.redirect("/")


@app.route("/logout")
def get_logout():
    flask.session.clear()
    return flask.redirect("/")


@app.route("/")
def get_index():
    me = get_session_user()

    cursor = db().cursor()
    cursor.execute(
        "SELECT `id`, `user_id`, `body`, `created_at`, `mime` FROM `posts` ORDER BY `created_at` DESC LIMIT %s",
        (POSTS_PER_PAGE,)
    )
    posts = make_posts(cursor.fetchall())

    return flask.render_template("index.html", posts=posts, me=me)


@app.route("/@<account_name>")
def get_user_list(account_name):
    cursor = db().cursor()

    cursor.execute(
        "SELECT * FROM `users` WHERE `account_name` = %s AND `del_flg` = 0",
        (account_name,),
    )
    user = cursor.fetchone()
    if user is None:
        flask.abort(404)

    cursor.execute(
        "SELECT `id`, `user_id`, `body`, `mime`, `created_at` FROM `posts` WHERE `user_id` = %s ORDER BY `created_at` DESC LIMIT %s",
        (user["id"], POSTS_PER_PAGE)
    )
    posts = make_posts(cursor.fetchall())

    # 統計情報を効率的に取得
    cursor.execute("""
        SELECT 
            COUNT(DISTINCT c.id) as comment_count,
            COUNT(DISTINCT p.id) as post_count,
            COUNT(DISTINCT c2.id) as commented_count
        FROM users u
        LEFT JOIN comments c ON u.id = c.user_id
        LEFT JOIN posts p ON u.id = p.user_id
        LEFT JOIN comments c2 ON p.id = c2.post_id
        WHERE u.id = %s
    """, (user["id"],))
    
    stats = cursor.fetchone()
    comment_count = stats["comment_count"] or 0
    post_count = stats["post_count"] or 0
    commented_count = stats["commented_count"] or 0

    me = get_session_user()

    return flask.render_template(
        "user.html",
        posts=posts,
        user=user,
        post_count=post_count,
        comment_count=comment_count,
        commented_count=commented_count,
        me=me,
    )


def _parse_iso8601(s):
    # http://bugs.python.org/issue15873
    # Ignore timezone
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})[ tT](\d{2}):(\d{2}):(\d{2}).*", s)
    if not m:
        raise ValueError("Invlaid iso8601 format: %r" % (s,))
    return datetime.datetime(*map(int, m.groups()))


@app.route("/posts")
def get_posts():
    cursor = db().cursor()
    max_created_at = flask.request.args["max_created_at"] or None
    if max_created_at:
        max_created_at = _parse_iso8601(max_created_at)
        cursor.execute(
            "SELECT `id`, `user_id`, `body`, `mime`, `created_at` FROM `posts` WHERE `created_at` <= %s ORDER BY `created_at` DESC LIMIT %s",
            (max_created_at, POSTS_PER_PAGE,),
        )
    else:
        cursor.execute(
            "SELECT `id`, `user_id`, `body`, `mime`, `created_at` FROM `posts` ORDER BY `created_at` DESC LIMIT %s",
            (POSTS_PER_PAGE,)
        )
    results = cursor.fetchall()
    posts = make_posts(results)
    return flask.render_template("posts.html", posts=posts)


@app.route("/posts/<id>")
def get_posts_id(id):
    cursor = db().cursor()

    cursor.execute("SELECT * FROM `posts` WHERE `id` = %s LIMIT %s", (id, POSTS_PER_PAGE))
    posts = make_posts(cursor.fetchall(), all_comments=True)
    if not posts:
        flask.abort(404)

    me = get_session_user()
    return flask.render_template("post.html", post=posts[0], me=me)


@app.route("/", methods=["POST"])
def post_index():
    me = get_session_user()
    if not me:
        return flask.redirect("/login")

    if flask.request.form["csrf_token"] != flask.session["csrf_token"]:
        flask.abort(422)

    file = flask.request.files.get("file")
    if not file:
        flask.flash("画像が必要です")
        return flask.redirect("/")

    # 投稿のContent-Typeからファイルのタイプを決定する
    mime = file.mimetype
    if mime not in ("image/jpeg", "image/png", "image/gif"):
        flask.flash("投稿できる画像形式はjpgとpngとgifだけです")
        return flask.redirect("/")

    with tempfile.TemporaryFile() as tempf:
        file.save(tempf)
        tempf.flush()

        if tempf.tell() > UPLOAD_LIMIT:
            flask.flash("ファイルサイズが大きすぎます")
            return flask.redirect("/")

        tempf.seek(0)
        imgdata = tempf.read()

    app.logger.debug("%s", me)
    query = "INSERT INTO `posts` (`user_id`, `mime`, `imgdata`, `body`) VALUES (%s,%s,%s,%s)"
    cursor = db().cursor()
    cursor.execute(query, (me["id"], mime, imgdata, flask.request.form.get("body")))
    pid = cursor.lastrowid
    
    # 画像をローカルファイルシステムにも保存
    try:
        # 画像保存ディレクトリを作成
        image_dir = "/home/isucon/upload_images"
        os.makedirs(image_dir, exist_ok=True)
        
        # ファイル拡張子を決定
        ext = ""
        if mime == "image/jpeg":
            ext = ".jpg"
        elif mime == "image/png":
            ext = ".png"
        elif mime == "image/gif":
            ext = ".gif"
        
        if ext:  # 有効な拡張子の場合のみ保存
            # ファイルパスを作成
            image_path = os.path.join(image_dir, f"{pid}{ext}")
            
            # 画像ファイルを保存
            with open(image_path, 'wb') as f:
                f.write(imgdata)
            
            app.logger.info(f"Saved image to filesystem: {image_path}")
        
    except Exception as e:
        app.logger.error(f"Error saving image to filesystem: {str(e)}")
        # ファイルシステムへの保存が失敗してもアップロード自体は成功させる
    
    return flask.redirect("/posts/%d" % pid)

@app.route("/admin/export-images", methods=["POST"])
def export_images():
    """全ての画像をDBから取得してファイルシステムに保存するAPI"""

    try:
        # 画像保存ディレクトリを作成
        image_dir = "/tmp/images"
        os.makedirs(image_dir, exist_ok=True)
        
        cursor = db().cursor()
        cursor.execute("SELECT `id`, `mime`, `imgdata` FROM `posts` ORDER BY `id`")
        posts = cursor.fetchall()
        
        exported_count = 0
        for post in posts:
            post_id = post["id"]
            mime = post["mime"]
            imgdata = post["imgdata"]
            
            # ファイル拡張子を決定
            ext = ""
            if mime == "image/jpeg":
                ext = ".jpg"
            elif mime == "image/png":
                ext = ".png"
            elif mime == "image/gif":
                ext = ".gif"
            else:
                continue
                
            # ファイルパスを作成
            image_path = image_dir + "/" + f"{post_id}{ext}"
            
            # 既にファイルが存在する場合はスキップ
            if os.path.exists(image_path):
                continue
                
            # 画像ファイルを保存
            with open(image_path, 'wb') as f:
                f.write(imgdata)
            exported_count += 1
        
        app.logger.info(f"Exported {exported_count} images to filesystem")
        flask.flash(f"{exported_count}個の画像をファイルシステムに保存しました")
        
    except Exception as e:
        app.logger.error(f"Error exporting images: {str(e)}")
        flask.flash("画像の保存中にエラーが発生しました")
    
    return flask.redirect("/admin/banned")


@app.route("/image/<id>.<ext>")
def get_image(id, ext):
    if not id:
        return ""
    try:
        id = int(id)
        if id == 0:
            return ""
    except (ValueError, TypeError):
        flask.abort(404)

    # Memcacheでキャッシュ確認
    # cache_key = f"image:{id}"
    # cached_image = memcache().get(cache_key)
    # 
    # if cached_image and isinstance(cached_image, dict):
    #     # base64デコードして画像データを復元
    #     imgdata = base64.b64decode(cached_image["imgdata"])
    #     return flask.Response(imgdata, mimetype=cached_image["mime"])

    cursor = db().cursor()
    cursor.execute("SELECT `mime`, `imgdata` FROM `posts` WHERE `id` = %s", (id,))
    post = cursor.fetchone()
    
    if not post:
        flask.abort(404)

    mime = post["mime"]
    if (
        ext == "jpg" and mime == "image/jpeg"
        or ext == "png" and mime == "image/png"
        or ext == "gif" and mime == "image/gif"
    ):
        # # 画像データをbase64エンコードしてMemcacheにキャッシュ（1時間）
        # cache_data = {
        #     "imgdata": base64.b64encode(post["imgdata"]).decode('utf-8'),
        #     "mime": mime
        # }
        # memcache().set(cache_key, cache_data, expire=3600)
        
        return flask.Response(post["imgdata"], mimetype=mime)

    flask.abort(404)


@app.route("/comment", methods=["POST"])
def post_comment():
    me = get_session_user()
    if not me:
        return flask.redirect("/login")

    if flask.request.form["csrf_token"] != flask.session["csrf_token"]:
        flask.abort(422)

    post_id = flask.request.form["post_id"]
    if not re.match(r"[0-9]+", post_id):
        return "post_idは整数のみです"
    post_id = int(post_id)

    query = (
        "INSERT INTO `comments` (`post_id`, `user_id`, `comment`) VALUES (%s, %s, %s)"
    )
    cursor = db().cursor()
    cursor.execute(query, (post_id, me["id"], flask.request.form["comment"]))

    return flask.redirect("/posts/%d" % post_id)


@app.route("/admin/banned")
def get_banned():
    me = get_session_user()
    if not me:
        flask.redirect("/login")

    if me["authority"] == 0:
        flask.abort(403)

    cursor = db().cursor()
    cursor.execute(
        "SELECT * FROM `users` WHERE `authority` = 0 AND `del_flg` = 0 ORDER BY `created_at` DESC"
    )
    users = cursor.fetchall()

    flask.render_template("banned.html", users=users, me=me)


@app.route("/admin/banned", methods=["POST"])
def post_banned():
    me = get_session_user()
    if not me:
        flask.redirect("/login")

    if me["authority"] == 0:
        flask.abort(403)

    if flask.request.form["csrf_token"] != flask.session["csrf_token"]:
        flask.abort(422)

    cursor = db().cursor()
    query = "UPDATE `users` SET `del_flg` = %s WHERE `id` = %s"
    for id in flask.request.form.getlist("uid", type=int):
        cursor.execute(query, (1, id))

    return flask.redirect("/admin/banned")
