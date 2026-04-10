"""Tests for the auth module: user management, password hashing, JWT tokens."""

import json
import pytest

from app import auth
from app.auth import (
    authenticate,
    admin_reset_password,
    change_password,
    create_token,
    create_user,
    decode_token,
    ensure_default_admin,
    get_user,
    list_users,
)


@pytest.fixture(autouse=True)
def isolated_users(monkeypatch, tmp_path):
    """Point the user store and JWT secret at a temp directory for every test."""
    workdir = tmp_path / "default"
    workdir.mkdir()
    monkeypatch.setattr(auth.settings, "codex_workdir", str(workdir), raising=False)
    # Reset the cached JWT secret so each test generates a fresh one
    monkeypatch.setattr(auth, "_JWT_SECRET", "", raising=False)
    yield


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

class TestEnsureDefaultAdmin:
    def test_creates_admin_when_no_users(self):
        ensure_default_admin()
        users = list_users()
        assert len(users) == 1
        assert users[0]["username"] == "admin"
        assert users[0]["role"] == "admin"

    def test_does_not_overwrite_existing_users(self):
        create_user("alice", "pass1234", "admin")
        ensure_default_admin()
        users = list_users()
        assert len(users) == 1
        assert users[0]["username"] == "alice"

    def test_default_admin_can_authenticate(self):
        ensure_default_admin()
        user = authenticate("admin", "admin")
        assert user is not None
        assert user["username"] == "admin"
        assert user["role"] == "admin"


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------

class TestCreateUser:
    def test_create_user_basic(self):
        result = create_user("bob", "secret99", "user")
        assert result["username"] == "bob"
        assert result["role"] == "user"
        assert get_user("bob") is not None

    def test_create_admin_user(self):
        result = create_user("superadmin", "admin123", "admin")
        assert result["role"] == "admin"

    def test_duplicate_username_raises(self):
        create_user("charlie", "pass1234")
        with pytest.raises(ValueError, match="already exists"):
            create_user("charlie", "other456")

    def test_empty_username_raises(self):
        with pytest.raises(ValueError, match="Username"):
            create_user("", "pass1234")

    def test_short_password_raises(self):
        with pytest.raises(ValueError, match="at least 4"):
            create_user("dave", "ab")

    def test_invalid_role_raises(self):
        with pytest.raises(ValueError, match="Role"):
            create_user("eve", "pass1234", "superuser")


class TestListUsers:
    def test_empty_initially(self):
        assert list_users() == []

    def test_lists_all_users(self):
        create_user("u1", "pass1234", "user")
        create_user("u2", "pass1234", "admin")
        users = list_users()
        names = {u["username"] for u in users}
        assert names == {"u1", "u2"}

    def test_does_not_expose_passwords(self):
        create_user("u1", "pass1234")
        users = list_users()
        assert "password" not in users[0]


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

class TestAuthenticate:
    def test_valid_credentials(self):
        create_user("frank", "mypassword")
        user = authenticate("frank", "mypassword")
        assert user is not None
        assert user["username"] == "frank"

    def test_wrong_password(self):
        create_user("grace", "correct")
        assert authenticate("grace", "wrong") is None

    def test_nonexistent_user(self):
        assert authenticate("nobody", "anything") is None

    def test_returns_role(self):
        create_user("heidi", "pass1234", "admin")
        user = authenticate("heidi", "pass1234")
        assert user["role"] == "admin"


# ---------------------------------------------------------------------------
# Change password
# ---------------------------------------------------------------------------

class TestChangePassword:
    def test_change_password_success(self):
        create_user("ivan", "oldpass1")
        change_password("ivan", "oldpass1", "newpass1")
        assert authenticate("ivan", "oldpass1") is None
        assert authenticate("ivan", "newpass1") is not None

    def test_wrong_old_password_raises(self):
        create_user("judy", "correct1")
        with pytest.raises(ValueError, match="incorrect"):
            change_password("judy", "wrong123", "newpass1")

    def test_short_new_password_raises(self):
        create_user("karl", "pass1234")
        with pytest.raises(ValueError, match="at least 4"):
            change_password("karl", "pass1234", "ab")

    def test_nonexistent_user_raises(self):
        with pytest.raises(ValueError, match="not found"):
            change_password("nobody", "old12345", "new12345")


# ---------------------------------------------------------------------------
# Admin reset password
# ---------------------------------------------------------------------------

class TestAdminResetPassword:
    def test_reset_success(self):
        create_user("liam", "original")
        admin_reset_password("liam", "resetpw1")
        assert authenticate("liam", "original") is None
        assert authenticate("liam", "resetpw1") is not None

    def test_nonexistent_user_raises(self):
        with pytest.raises(ValueError, match="not found"):
            admin_reset_password("ghost", "newpass1")

    def test_short_password_raises(self):
        create_user("mia", "pass1234")
        with pytest.raises(ValueError, match="at least 4"):
            admin_reset_password("mia", "ab")


# ---------------------------------------------------------------------------
# JWT tokens
# ---------------------------------------------------------------------------

class TestJWT:
    def test_create_and_decode(self):
        create_user("nancy", "pass1234", "user")
        token = create_token("nancy")
        assert isinstance(token, str)
        assert len(token) > 20
        user = decode_token(token)
        assert user is not None
        assert user["username"] == "nancy"
        assert user["role"] == "user"

    def test_invalid_token_returns_none(self):
        assert decode_token("garbage.token.here") is None

    def test_expired_token_returns_none(self, monkeypatch):
        create_user("oscar", "pass1234")
        monkeypatch.setattr(auth, "_JWT_EXPIRE_SECONDS", -1, raising=False)
        token = create_token("oscar")
        assert decode_token(token) is None

    def test_token_for_deleted_user_returns_none(self):
        create_user("pete", "pass1234")
        token = create_token("pete")
        # Manually remove the user from the store
        users = auth._load_users()
        del users["pete"]
        auth._save_users(users)
        assert decode_token(token) is None

    def test_jwt_secret_persisted_to_file(self):
        create_user("quinn", "pass1234")
        create_token("quinn")
        secret_path = auth._users_file().parent / ".jwt_secret"
        assert secret_path.is_file()
        assert len(secret_path.read_text().strip()) > 0


# ---------------------------------------------------------------------------
# User store persistence
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_users_survive_reload(self):
        create_user("rachel", "pass1234", "admin")
        # Read directly from the file
        data = json.loads(auth._users_file().read_text(encoding="utf-8"))
        assert "rachel" in data
        assert data["rachel"]["role"] == "admin"
        assert "$" in data["rachel"]["password"]  # salt$hash format
