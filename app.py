from flask import Flask, jsonify, request
from db import get_connection


app = Flask(__name__)

@app.route("/test-db")
def test_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT user_id, role FROM users")
    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(rows)

@app.route("/login", methods=["POST"])
def login():
    data = request.json

    user_id = data.get("id")
    password = data.get("password")

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    sql = "SELECT * FROM users WHERE user_id=%s AND password=%s"
    cursor.execute(sql, (user_id, password))
    user = cursor.fetchone()

    cursor.close()
    conn.close()

    if user:
        return jsonify({
            "result": "success",
            "user_id": user["user_id"],
            "role": user["role"]
        })
    else:
        return jsonify({"result": "fail"}), 401

@app.route("/signup", methods=["POST"])
def signup():
    data = request.json

    user_id = data.get("id")
    password = data.get("password")

    if not user_id or not password:
        return jsonify({"result": "fail", "message": "필수값 누락"}), 400

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # 1️⃣ 아이디 중복 체크
    cursor.execute("SELECT id FROM users WHERE user_id=%s", (user_id,))
    exists = cursor.fetchone()

    if exists:
        cursor.close()
        conn.close()
        return jsonify({"result": "fail", "message": "이미 존재하는 아이디"}), 409

    # 2️⃣ 회원가입 처리
    cursor.execute(
        "INSERT INTO users (user_id, password) VALUES (%s, %s)",
        (user_id, password)
    )
    conn.commit()

    cursor.close()
    conn.close()

    return jsonify({"result": "success"})

@app.route("/me", methods=["POST"])
def me():
    data = request.json
    user_id = data.get("id")

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT user_id, role, created_at
        FROM users
        WHERE user_id=%s
    """, (user_id,))
    user = cursor.fetchone()

    cursor.close()
    conn.close()

    if not user:
        return jsonify({"result": "fail"}), 404

    user["created_at"] = user["created_at"].strftime("%Y-%m-%d")

    return jsonify({"result": "success", "user": user})

@app.route("/change-password", methods=["POST"])
def change_password():
    data = request.json
    user_id = data.get("id")
    new_pw = data.get("password")

    if not new_pw:
        return jsonify({"result": "fail"}), 400

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE users SET password=%s WHERE user_id=%s",
        (new_pw, user_id)
    )
    conn.commit()

    cursor.close()
    conn.close()

    return jsonify({"result": "success"})

@app.route("/books", methods=["GET"])
def get_books():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT id, title, author, publisher, is_rented, created_at
        FROM books
        ORDER BY id
    """)
    books = cursor.fetchall()

    cursor.close()
    conn.close()

    # 날짜 포맷 통일 (YYYY-MM-DD)
    for b in books:
        if b.get("created_at"):
            b["created_at"] = b["created_at"].strftime("%Y-%m-%d")

    return jsonify({"result": "success", "books": books})


@app.route("/return", methods=["POST"])
def return_book():
    rental_id = request.json.get("rental_id")

    conn = get_connection()
    cursor = conn.cursor()

    # book_id 가져오기
    cursor.execute(
        "SELECT book_id FROM rentals WHERE id=%s AND returned_at IS NULL",
        (rental_id,)
    )
    row = cursor.fetchone()
    if not row:
        cursor.close(); conn.close()
        return jsonify({"result": "fail"}), 400

    book_id = row[0]

    # rentals 반납 처리
    cursor.execute(
        "UPDATE rentals SET returned_at = NOW() WHERE id=%s",
        (rental_id,)
    )

    # books 상태 복구
    cursor.execute(
        "UPDATE books SET is_rented = 0 WHERE id=%s",
        (book_id,)
    )

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"result": "success"})


@app.route("/rent", methods=["POST"])
def rent_book():
    data = request.json
    book_id = data.get("book_id")
    user_id = data.get("user_id")

    conn = get_connection()
    cursor = conn.cursor()

    # 1️⃣ 이미 대여 중인지 rentals 기준으로 체크
    cursor.execute("""
        SELECT id FROM rentals
        WHERE book_id = %s AND returned_at IS NULL
    """, (book_id,))
    if cursor.fetchone():
        cursor.close()
        conn.close()
        return jsonify({"result": "fail", "message": "already rented"}), 409

    # 2️⃣ books 상태 변경
    cursor.execute(
        "UPDATE books SET is_rented = 1 WHERE id = %s",
        (book_id,)
    )

    # 3️⃣ rentals 기록 추가
    cursor.execute("""
        INSERT INTO rentals (user_id, book_id)
        VALUES (%s, %s)
    """, (user_id, book_id))

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"result": "success"})



@app.route("/my-rentals", methods=["POST"])
def my_rentals():
    user_id = request.json.get("user_id")

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT r.id, b.title, b.author, r.rented_at, r.returned_at
        FROM rentals r
        JOIN books b ON r.book_id = b.id
        WHERE r.user_id = %s
          AND r.returned_at IS NULL
        ORDER BY r.rented_at DESC
    """, (user_id,))

    rows = cursor.fetchall()

    for r in rows:
        r["rented_at"] = r["rented_at"].strftime("%Y-%m-%d")
        if r["returned_at"]:
            r["returned_at"] = r["returned_at"].strftime("%Y-%m-%d")

    cursor.close(); conn.close()
    return jsonify({"result": "success", "rentals": rows})






if __name__ == "__main__":
    app.run(debug=True)
