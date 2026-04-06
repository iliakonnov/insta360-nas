import os
import pytest
import jinja2
from database import User, UserDirectory


@pytest.fixture
def env():
    templates_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(templates_dir),
        autoescape=True,
    )


# ---------------------------------------------------------------------------
# dashboard.html
# ---------------------------------------------------------------------------

def test_dashboard_renders_user_name(env):
    user = User(id="u1", name="Alice", is_admin=True, authorized=True)
    html = env.get_template("dashboard.html").render(
        user=user, directories=[], hidden_files=[]
    )
    assert "Alice" in html


def test_dashboard_renders_directories(env):
    user = User(id="u1", name="Bob", is_admin=False, authorized=True)
    dirs = [
        UserDirectory(directory="SDCard", access_granted=True, is_exported=True),
        UserDirectory(directory="Internal", access_granted=True, is_exported=False),
    ]
    html = env.get_template("dashboard.html").render(
        user=user, directories=dirs, hidden_files=[]
    )
    assert "SDCard" in html
    assert "Internal" in html


def test_dashboard_exported_checkbox_checked(env):
    user = User(id="u1", name="Bob", is_admin=False, authorized=True)
    dirs = [UserDirectory(directory="SDCard", access_granted=True, is_exported=True)]
    html = env.get_template("dashboard.html").render(
        user=user, directories=dirs, hidden_files=[]
    )
    assert "checked" in html


def test_dashboard_unexported_checkbox_not_checked(env):
    user = User(id="u1", name="Bob", is_admin=False, authorized=True)
    dirs = [UserDirectory(directory="Internal", access_granted=True, is_exported=False)]
    html = env.get_template("dashboard.html").render(
        user=user, directories=dirs, hidden_files=[]
    )
    assert "checked" not in html


def test_dashboard_renders_hidden_files(env):
    user = User(id="u1", name="Carol", is_admin=False, authorized=True)
    hidden = ["/DCIM/Camera01/video.mp4", "/DCIM/Camera01/photo.jpg"]
    html = env.get_template("dashboard.html").render(
        user=user, directories=[], hidden_files=hidden
    )
    assert "/DCIM/Camera01/video.mp4" in html
    assert "/DCIM/Camera01/photo.jpg" in html


def test_dashboard_no_hidden_files_message(env):
    user = User(id="u1", name="Carol", is_admin=False, authorized=True)
    html = env.get_template("dashboard.html").render(
        user=user, directories=[], hidden_files=[]
    )
    assert "No hidden files" in html


# ---------------------------------------------------------------------------
# admin.html
# ---------------------------------------------------------------------------

def test_admin_renders_user_ids_and_names(env):
    users = [
        User(id="u1", name="Alice", is_admin=True, authorized=True),
        User(id="u2", name="Bob", is_admin=False, authorized=False),
    ]
    html = env.get_template("admin.html").render(
        users=users, top_levels=[], u_access={"u1": set(), "u2": set()}
    )
    assert "u1" in html
    assert "Alice" in html
    assert "u2" in html
    assert "Bob" in html


def test_admin_shows_admin_status(env):
    users = [User(id="u1", name="Alice", is_admin=True, authorized=True)]
    html = env.get_template("admin.html").render(
        users=users, top_levels=[], u_access={"u1": set()}
    )
    assert "Admin" in html


def test_admin_shows_non_admin_status(env):
    users = [User(id="u2", name="Bob", is_admin=False, authorized=False)]
    html = env.get_template("admin.html").render(
        users=users, top_levels=[], u_access={"u2": set()}
    )
    assert "User" in html


def test_admin_authorized_checkbox_checked(env):
    users = [User(id="u1", name="Alice", is_admin=True, authorized=True)]
    html = env.get_template("admin.html").render(
        users=users, top_levels=[], u_access={"u1": set()}
    )
    assert "checked" in html


def test_admin_unauthorized_checkbox_not_checked(env):
    users = [User(id="u2", name="Bob", is_admin=False, authorized=False)]
    html = env.get_template("admin.html").render(
        users=users, top_levels=[], u_access={"u2": set()}
    )
    # No checkboxes should be checked for an unauthorized, non-admin user
    # with no directory access
    assert "checked" not in html


def test_admin_renders_top_level_directories(env):
    users = [User(id="u1", name="Alice", is_admin=True, authorized=True)]
    html = env.get_template("admin.html").render(
        users=users,
        top_levels=["SDCard", "Internal"],
        u_access={"u1": {"SDCard"}},
    )
    assert "SDCard" in html
    assert "Internal" in html


def test_admin_directory_access_checked_when_granted(env):
    users = [User(id="u1", name="Alice", is_admin=True, authorized=True)]
    html = env.get_template("admin.html").render(
        users=users,
        top_levels=["SDCard"],
        u_access={"u1": {"SDCard"}},
    )
    # "checked" appears for both the authorized checkbox and the directory access checkbox
    assert html.count("checked") >= 2


def test_admin_directory_access_not_checked_when_not_granted(env):
    users = [User(id="u1", name="Alice", is_admin=True, authorized=True)]
    html = env.get_template("admin.html").render(
        users=users,
        top_levels=["Internal"],
        u_access={"u1": set()},  # no access to Internal
    )
    # Only the authorized checkbox is checked, not the directory one
    assert html.count("checked") == 1


# ---------------------------------------------------------------------------
# directory.html
# ---------------------------------------------------------------------------

def test_directory_renders_file_names(env):
    items = [
        {"name": "video.mp4", "link": "video.mp4", "size": "1024"},
        {"name": "photo.jpg", "link": "photo.jpg", "size": "512"},
    ]
    html = env.get_template("directory.html").render(items=items)
    assert "video.mp4" in html
    assert "photo.jpg" in html


def test_directory_renders_links(env):
    items = [{"name": "video.mp4", "link": "video.mp4", "size": "1024"}]
    html = env.get_template("directory.html").render(items=items)
    assert 'href="video.mp4"' in html


def test_directory_renders_sizes(env):
    items = [{"name": "video.mp4", "link": "video.mp4", "size": "2048576"}]
    html = env.get_template("directory.html").render(items=items)
    assert "2048576" in html


def test_directory_renders_subdirectory_link(env):
    items = [{"name": "Camera01", "link": "Camera01/", "size": "directory"}]
    html = env.get_template("directory.html").render(items=items)
    assert 'href="Camera01/"' in html
    assert "directory" in html


def test_directory_empty_listing(env):
    html = env.get_template("directory.html").render(items=[])
    assert "<table" in html
    assert "<tr>" not in html
