import pytest
import os
import sqlite3
import tempfile
from database import Database, User, UserDirectory

@pytest.fixture
def db():
    # Use a temporary file for the database instead of in-memory
    # because some parts of SQLite handle in-memory slightly differently
    # when recreating connections, though for this Database class
    # it creates a connection per method which wouldn't work with ":memory:" easily
    # since ":memory:" is per connection unless using shared cache.
    fd, path = tempfile.mkstemp()
    os.close(fd)
    database = Database(path)
    yield database
    os.remove(path)

def test_initial_user_is_admin(db):
    user = db.get_or_create_user("user_id_1")
    assert user.id == "user_id_1"
    assert user.is_admin is True
    assert user.authorized is True

def test_subsequent_user_is_not_admin(db):
    user1 = db.get_or_create_user("user_id_1")
    user2 = db.get_or_create_user("user_id_2")

    assert user1.is_admin is True
    assert user2.is_admin is False
    assert user2.authorized is False

def test_get_user_by_id(db):
    db.get_or_create_user("user_id_1")
    user = db.get_user_by_id("user_id_1")
    assert user is not None
    assert user.id == "user_id_1"
    assert user.is_admin is True

    missing = db.get_user_by_id("non_existent")
    assert missing is None

def test_get_all_users(db):
    db.get_or_create_user("user_1")
    db.get_or_create_user("user_2")

    users = db.get_all_users()
    assert len(users) == 2
    ids = [u.id for u in users]
    assert "user_1" in ids
    assert "user_2" in ids

def test_set_user_authorized(db):
    user = db.get_or_create_user("user_id_1")
    assert user.authorized is True # First user is admin/authorized

    user2 = db.get_or_create_user("user_id_2")
    assert user2.authorized is False

    db.set_user_authorized("user_id_2", True)
    updated_user2 = db.get_user_by_id("user_id_2")
    assert updated_user2.authorized is True

def test_directory_access_control(db):
    user = db.get_or_create_user("user_id_1")

    # Set access
    db.set_directory_access("user_id_1", "SDCard", True)

    dirs = db.get_user_directories("user_id_1")
    assert len(dirs) == 1
    assert dirs[0].directory == "SDCard"
    assert dirs[0].access_granted is True
    assert dirs[0].is_exported is True # default is True

def test_get_exported_directories(db):
    db.get_or_create_user("user_id_1")
    db.set_directory_access("user_id_1", "Dir1", True)
    db.set_directory_access("user_id_1", "Dir2", True)

    # Not exported
    db.set_directory_export("user_id_1", "Dir2", False)

    # Not accessible
    db.set_directory_access("user_id_1", "Dir3", False)

    exported = db.get_exported_directories("user_id_1")
    assert len(exported) == 1
    assert exported[0] == "Dir1"

def test_hide_unhide_files(db):
    db.get_or_create_user("user_id_1")

    # Hide files
    db.hide_files("user_id_1", ["/DCIM/Camera01/file1.mp4", "/DCIM/Camera01/file2.mp4"])

    hidden = db.get_hidden_files("user_id_1")
    assert len(hidden) == 2
    assert "/DCIM/Camera01/file1.mp4" in hidden
    assert "/DCIM/Camera01/file2.mp4" in hidden

    # Unhide one
    db.unhide_file("user_id_1", "/DCIM/Camera01/file1.mp4")

    hidden_after = db.get_hidden_files("user_id_1")
    assert len(hidden_after) == 1
    assert "/DCIM/Camera01/file2.mp4" in hidden_after

def test_get_hidden_files_ordered(db):
    import time
    db.get_or_create_user("user_id_1")

    # SQLite CURRENT_TIMESTAMP is in seconds, so we need a slight delay
    # or just trust the DB. Let's mock or just insert.
    db.hide_files("user_id_1", ["/DCIM/Camera01/file1.mp4"])
    time.sleep(1) # wait 1s to ensure distinct timestamp
    db.hide_files("user_id_1", ["/DCIM/Camera01/file2.mp4"])

    ordered = db.get_hidden_files_ordered("user_id_1")
    # Newest first
    assert ordered[0] == "/DCIM/Camera01/file2.mp4"
    assert ordered[1] == "/DCIM/Camera01/file1.mp4"
