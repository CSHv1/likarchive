import os
from flask import Flask, jsonify
from dotenv import load_dotenv
from db import get_connection, init_db

load_dotenv()

app = Flask(__name__)
DB_PATH = os.getenv("DB_PATH", "linkedin_likes.db")


@app.route("/")
def index():
    conn = get_connection(DB_PATH)
    total = conn.execute("SELECT COUNT(*) FROM liked_posts").fetchone()[0]
    conn.close()
    return jsonify({"status": "ok", "posts": total})


if __name__ == "__main__":
    init_db(DB_PATH)
    app.run(debug=True, port=5000)
