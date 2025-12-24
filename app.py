from flask import Flask, jsonify, request
from db import get_connection
import requests

app = Flask(__name__)

NAVER_CLIENT_ID = "INpjyW6mDSdoZKftWeW2"
NAVER_CLIENT_SECRET = "iALzgp3jaK"


# =========================
# 로그인
# =========================
@app.route("/login", methods=["POST"])
def login():
    data = request.json
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT user_id, role, created_at FROM users WHERE user_id=%s AND password=%s",
        (data["id"], data["password"])
    )
    user = cursor.fetchone()

    cursor.close(); conn.close()

    if user:
        user["created_at"] = user["created_at"].strftime("%Y-%m-%d")
        return jsonify(user)

    return jsonify({"result": "fail"}), 401


# =========================
# 회원가입
# =========================
@app.route("/signup", methods=["POST"])
def signup():
    data = request.json
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT user_id FROM users WHERE user_id=%s", (data["id"],))
    if cursor.fetchone():
        cursor.close(); conn.close()
        return jsonify({"result": "fail", "message": "duplicate"}), 409

    cursor.execute(
        "INSERT INTO users (user_id, password, name) VALUES (%s,%s,'사용자')",
        (data["id"], data["password"])
    )
    conn.commit()

    cursor.close(); conn.close()
    return jsonify({"result": "success"})


# =========================
# 내 정보
# =========================
@app.route("/me", methods=["POST"])
def me():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT user_id, role, created_at FROM users WHERE user_id=%s",
        (request.json["user_id"],)
    )
    user = cursor.fetchone()

    cursor.close(); conn.close()

    if not user:
        return jsonify({"result": "fail"}), 404

    user["created_at"] = user["created_at"].strftime("%Y-%m-%d")
    return jsonify(user)


# =========================
# 도서 목록 (DB)
# =========================
@app.route("/books", methods=["GET"])
def books():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM books ORDER BY id")
    books = cursor.fetchall()

    for b in books:
        b["created_at"] = b["created_at"].strftime("%Y-%m-%d")

    cursor.close(); conn.close()
    return jsonify({"result": "success", "books": books})


from mysql.connector import Error

# =========================
# 관리자 도서 등록
# =========================
@app.route("/books", methods=["POST"])
def add_book():
    data = request.json
    print("ADD BOOK:", data)
    print("ADD BOOK user_id:", data.get("user_id"))

    conn = get_connection()
    cursor = conn.cursor()

    # 관리자 권한 확인
    cursor.execute(
        "SELECT role FROM users WHERE user_id=%s",
        (data["user_id"],)
    )
    role = cursor.fetchone()

    # ✅ 대소문자/공백 무시하고 ADMIN 판정
    if (not role) or (str(role[0]).strip().upper() != "ADMIN"):
        cursor.close();
        conn.close()
        return jsonify({"result": "fail", "message": "forbidden"}), 403

    try:
        cursor.execute(
            "INSERT INTO books (title, author, publisher) VALUES (%s,%s,%s)",
            (data["title"], data["author"], data.get("publisher"))
        )
        conn.commit()
        return jsonify({"result": "success"})

    except Error as e:
        conn.rollback()

        # 🔥 도서명 UNIQUE 중복
        if e.errno == 1062:
            return jsonify({
                "result": "duplicate",
                "message": "이미 등록된 도서명입니다."
            }), 409

        return jsonify({
            "result": "fail",
            "message": str(e)
        }), 400

    finally:
        cursor.close()
        conn.close()



# =========================
# 대여
# =========================
@app.route("/rent", methods=["POST"])
def rent():
    data = request.json
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM rentals WHERE book_id=%s AND returned_at IS NULL",
        (data["book_id"],)
    )
    if cursor.fetchone():
        cursor.close(); conn.close()
        return jsonify({"result": "fail"}), 409

    cursor.execute("UPDATE books SET is_rented=1 WHERE id=%s", (data["book_id"],))
    cursor.execute(
        "INSERT INTO rentals (user_id, book_id) VALUES (%s,%s)",
        (data["user_id"], data["book_id"])
    )

    conn.commit()
    cursor.close(); conn.close()
    return jsonify({"result": "success"})


# =========================
# 반납
# =========================
@app.route("/return", methods=["POST"])
def return_book():
    rental_id = request.json["rental_id"]

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT book_id FROM rentals WHERE id=%s AND returned_at IS NULL",
        (rental_id,)
    )
    row = cursor.fetchone()

    if not row:
        cursor.close(); conn.close()
        return jsonify({"result": "fail"}), 404

    book_id = row[0]

    cursor.execute("UPDATE rentals SET returned_at=NOW() WHERE id=%s", (rental_id,))
    cursor.execute("UPDATE books SET is_rented=0 WHERE id=%s", (book_id,))

    conn.commit()
    cursor.close(); conn.close()
    return jsonify({"result": "success"})


# =========================
# 내 대여 목록
# =========================
@app.route("/my-rentals", methods=["POST"])
def my_rentals():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT r.id, b.title, b.author, r.rented_at
        FROM rentals r
        JOIN books b ON r.book_id=b.id
        WHERE r.user_id=%s AND r.returned_at IS NULL
    """, (request.json["user_id"],))

    rows = cursor.fetchall()
    for r in rows:
        r["rented_at"] = r["rented_at"].strftime("%Y-%m-%d")

    cursor.close(); conn.close()
    return jsonify({"result": "success", "rentals": rows})


# =========================
# 🔹 신작 도서 (출간일 기준)
# =========================
@app.route("/book-new")
def book_new():
    url = "https://openapi.naver.com/v1/search/book.json"

    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }

    res = requests.get(
        url,
        headers=headers,
        params={
            "query": "책",
            "display": 10,
            "sort": "date"   # 출간일 기준
        }
    )

    items = res.json().get("items", [])

    books = [{
        "title": b["title"].replace("<b>", "").replace("</b>", ""),
        "author": b["author"],
        "publisher": b["publisher"]
    } for b in items]

    return jsonify({"result": "success", "books": books})


# =========================
# 🔹 도서 검색 (키워드)
# =========================
@app.route("/book-search")
def book_search():
    keyword = request.args.get("q", "")

    if not keyword:
        return jsonify({"result": "fail"}), 400

    url = "https://openapi.naver.com/v1/search/book.json"

    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }

    res = requests.get(
        url,
        headers=headers,
        params={
            "query": keyword,
            "display": 10
        }
    )

    items = res.json().get("items", [])

    books = [{
        "title": b["title"].replace("<b>", "").replace("</b>", ""),
        "author": b["author"],
        "publisher": b["publisher"]
    } for b in items]

    return jsonify({"result": "success", "books": books})


# =========================
# 관리자 - 회원 목록 조회
# =========================
@app.route("/users", methods=["GET"])
def get_users():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT user_id, role, created_at
        FROM users
        ORDER BY created_at DESC
    """)
    users = cursor.fetchall()

    for u in users:
        u["created_at"] = u["created_at"].strftime("%Y-%m-%d")

    cursor.close(); conn.close()
    return jsonify({"result": "success", "users": users})


# =========================
# 관리자 - 회원 삭제
# =========================
@app.route("/users/<user_id>", methods=["DELETE"])
def delete_user(user_id):
    if user_id == "admin":
        return jsonify({"result": "fail"}), 400

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM rentals WHERE user_id=%s AND returned_at IS NULL",
        (user_id,)
    )
    if cursor.fetchone():
        cursor.close(); conn.close()
        return jsonify({"result": "fail"}), 400

    cursor.execute("DELETE FROM users WHERE user_id=%s", (user_id,))
    conn.commit()

    cursor.close(); conn.close()
    return jsonify({"result": "success"})


# =========================
# 비밀번호 변경
# =========================
@app.route("/change-password", methods=["POST"])
def change_password():
    data = request.json
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT password FROM users WHERE user_id=%s",
        (data["user_id"],)
    )
    row = cursor.fetchone()

    if not row or row[0] != data["old_password"]:
        cursor.close(); conn.close()
        return jsonify({"result": "fail"}), 401

    cursor.execute(
        "UPDATE users SET password=%s WHERE user_id=%s",
        (data["new_password"], data["user_id"])
    )
    conn.commit()

    cursor.close(); conn.close()
    return jsonify({"result": "success"})

# =========================
# 관리자 - 도서 삭제
# =========================
@app.route("/books/<int:book_id>", methods=["DELETE"])
def delete_book(book_id):
    data = request.json
    conn = get_connection()
    cursor = conn.cursor()

    print("DELETE BOOK:", book_id, data)  # 🔥 디버그

    cursor.execute(
        "SELECT role FROM users WHERE user_id=%s",
        (data["user_id"],)
    )
    role = cursor.fetchone()

    # ✅ 대소문자/공백 무시하고 ADMIN 판정
    if (not role) or (str(role[0]).strip().upper() != "ADMIN"):
        cursor.close();
        conn.close()
        return jsonify({"result": "fail", "message": "forbidden"}), 403

    cursor.execute("DELETE FROM books WHERE id=%s", (book_id,))
    conn.commit()

    cursor.close(); conn.close()
    return jsonify({"result": "success"})




if __name__ == "__main__":
    app.run(debug=True)
