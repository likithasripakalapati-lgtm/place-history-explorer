import sqlite3
from pathlib import Path


# =========================================================
# DATABASE CONFIGURATION
# =========================================================

DATABASE_FILE = Path("place_history.db")


# =========================================================
# GET DATABASE CONNECTION
# =========================================================

def get_connection():
    connection = sqlite3.connect(
        DATABASE_FILE,
        check_same_thread=False,
    )

    connection.row_factory = sqlite3.Row

    return connection


# =========================================================
# INITIALIZE DATABASE
# =========================================================

def initialize_database():
    connection = get_connection()

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS visited_places (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            location TEXT NOT NULL,
            visit_date TEXT NOT NULL,
            photo BLOB NOT NULL,
            history TEXT NOT NULL
        )
        """
    )

    connection.commit()
    connection.close()


# =========================================================
# SAVE VISITED PLACE
# =========================================================

def save_visited_place(
    user_email,
    location,
    visit_date,
    photo,
    history,
):
    connection = get_connection()

    connection.execute(
        """
        INSERT INTO visited_places (
            user_email,
            location,
            visit_date,
            photo,
            history
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            user_email,
            location,
            visit_date,
            photo,
            history,
        ),
    )

    connection.commit()
    connection.close()


# =========================================================
# GET SAVED PLACES FOR ONE USER
# =========================================================

def get_visited_places(user_email):
    connection = get_connection()

    rows = connection.execute(
        """
        SELECT
            id,
            location,
            visit_date,
            photo,
            history
        FROM visited_places
        WHERE user_email = ?
        ORDER BY id DESC
        """,
        (user_email,),
    ).fetchall()

    connection.close()

    return rows