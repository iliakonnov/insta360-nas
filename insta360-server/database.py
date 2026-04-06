import sqlite3
import logging
import random
import os

logger = logging.getLogger('insta360-db')

ADJECTIVES = [
    "happy", "sad", "fast", "slow", "red", "blue", "green", "yellow", "brave", "clever",
    "calm", "eager", "fierce", "gentle", "jolly", "kind", "lively", "proud", "silly", "wise",
    "bold", "cool", "deep", "epic", "fair", "good", "huge", "neat", "pure", "rich"
]

NOUNS = [
    "hippo", "lion", "tiger", "bear", "wolf", "fox", "eagle", "hawk", "owl", "dove",
    "cat", "dog", "mouse", "rat", "cow", "pig", "sheep", "goat", "horse", "deer",
    "fish", "shark", "whale", "frog", "toad", "snake", "lizard", "bug", "ant", "bee"
]

from dataclasses import dataclass
from typing import Optional

@dataclass
class User:
    id: str
    name: str
    is_admin: bool
    authorized: bool

@dataclass
class UserDirectory:
    directory: str
    access_granted: bool
    is_exported: bool

class Database:
    def __init__(self, db_path: str = "insta360.db"):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._get_conn() as conn:
            c = conn.cursor()

            # Users table
            c.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    is_admin BOOLEAN NOT NULL DEFAULT 0,
                    authorized BOOLEAN NOT NULL DEFAULT 0
                )
            ''')

            # User directories (access control)
            c.execute('''
                CREATE TABLE IF NOT EXISTS user_directories (
                    user_id TEXT,
                    directory TEXT,
                    access_granted BOOLEAN NOT NULL DEFAULT 0,
                    is_exported BOOLEAN NOT NULL DEFAULT 1,
                    PRIMARY KEY (user_id, directory),
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''')

            # Hidden files
            c.execute('''
                CREATE TABLE IF NOT EXISTS hidden_files (
                    user_id TEXT,
                    file_uri TEXT,
                    deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, file_uri),
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''')

            conn.commit()

    def _generate_unique_name(self, cursor: sqlite3.Cursor) -> str:
        while True:
            name = f"{random.choice(ADJECTIVES)}-{random.choice(NOUNS)}"
            cursor.execute("SELECT 1 FROM users WHERE name = ?", (name,))
            if not cursor.fetchone():
                return name

    def get_or_create_user(self, user_id: str) -> User:
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT id, name, is_admin, authorized FROM users WHERE id = ?", (user_id,))
            row = c.fetchone()

            if row:
                return User(id=row[0], name=row[1], is_admin=bool(row[2]), authorized=bool(row[3]))

            # Check if this is the first user
            c.execute("SELECT COUNT(*) FROM users")
            count = c.fetchone()[0]
            is_admin = (count == 0)
            # Admin is automatically authorized
            authorized = is_admin

            name = self._generate_unique_name(c)

            c.execute(
                "INSERT INTO users (id, name, is_admin, authorized) VALUES (?, ?, ?, ?)",
                (user_id, name, is_admin, authorized)
            )
            conn.commit()

            logger.info(f"Created new user: {user_id} ({name}), Admin: {is_admin}")

            return User(id=user_id, name=name, is_admin=is_admin, authorized=authorized)

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT id, name, is_admin, authorized FROM users WHERE id = ?", (user_id,))
            row = c.fetchone()
            if row:
                return User(id=row[0], name=row[1], is_admin=bool(row[2]), authorized=bool(row[3]))
            return None

    def get_all_users(self) -> list[User]:
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT id, name, is_admin, authorized FROM users")
            return [
                User(id=row[0], name=row[1], is_admin=bool(row[2]), authorized=bool(row[3]))
                for row in c.fetchall()
            ]

    def set_user_authorized(self, user_id: str, authorized: bool) -> None:
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("UPDATE users SET authorized = ? WHERE id = ?", (authorized, user_id))
            conn.commit()

    # --- Directory Access Control ---
    def get_user_directories(self, user_id: str) -> list[UserDirectory]:
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT directory, access_granted, is_exported FROM user_directories WHERE user_id = ?", (user_id,))
            return [
                UserDirectory(directory=row[0], access_granted=bool(row[1]), is_exported=bool(row[2]))
                for row in c.fetchall()
            ]

    def get_exported_directories(self, user_id: str) -> list[str]:
        """Returns list of directories that user has access to AND are exported (visible)"""
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT directory FROM user_directories WHERE user_id = ? AND access_granted = 1 AND is_exported = 1", (user_id,))
            return [row[0] for row in c.fetchall()]

    def set_directory_access(self, user_id: str, directory: str, access_granted: bool) -> None:
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO user_directories (user_id, directory, access_granted, is_exported)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(user_id, directory) DO UPDATE SET access_granted = ?
            ''', (user_id, directory, access_granted, access_granted))
            conn.commit()

    def set_directory_export(self, user_id: str, directory: str, is_exported: bool) -> None:
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute('''
                UPDATE user_directories SET is_exported = ? WHERE user_id = ? AND directory = ?
            ''', (is_exported, user_id, directory))
            conn.commit()

    # --- Hidden Files ---
    def get_hidden_files(self, user_id: str) -> set[str]:
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT file_uri FROM hidden_files WHERE user_id = ?", (user_id,))
            return set(row[0] for row in c.fetchall())

    def get_hidden_files_ordered(self, user_id: str) -> list[str]:
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT file_uri FROM hidden_files WHERE user_id = ? ORDER BY deleted_at DESC", (user_id,))
            return [row[0] for row in c.fetchall()]

    def hide_files(self, user_id: str, uris: list[str]) -> None:
        with self._get_conn() as conn:
            c = conn.cursor()
            for uri in uris:
                c.execute("INSERT OR IGNORE INTO hidden_files (user_id, file_uri) VALUES (?, ?)", (user_id, uri))
            conn.commit()

    def unhide_file(self, user_id: str, uri: str) -> None:
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM hidden_files WHERE user_id = ? AND file_uri = ?", (user_id, uri))
            conn.commit()
