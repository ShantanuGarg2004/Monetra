"""Profile, report, and chat SQL. Routes call these functions."""
import hashlib
import hmac
import json

import secrets

from flask import g, has_request_context
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import IntegrityConflict, connection
from database.pdf_files import file_name_for, remove_pdf, resolve, write_pdf


# A credential that is not an account id. SQL that sees this matches nothing.
_NO_MATCH = object()
_CREDENTIAL_SCOPES = ("data", "llm")


def _account_scope():
    """Account id for this request.

    None means there is no request, so the caller passes an owner explicitly
    (the report worker). A person and a scoped API key both return their
    account id. There is no scope that sees every account.
    """
    if not has_request_context():
        return None
    actor = getattr(g, "actor", None)
    if actor is not None and actor.kind in ("user", "api_key"):
        try:
            return int(actor.credential)
        except (TypeError, ValueError):
            return _NO_MATCH
    return None


def _owned(sql: str, params: dict, column: str = "account_id"):
    scope = _account_scope()
    if scope is None:
        return sql, params
    if scope is _NO_MATCH:
        return sql + " AND 1 = 0", params
    bound = dict(params)
    bound["owner_account_id"] = scope
    return sql + f" AND {column} = :owner_account_id", bound


def get_user_by_id(user_id: int):
    sql, params = _owned(
        "SELECT * FROM users WHERE id = :user_id",
        {"user_id": user_id},
    )
    with connection() as conn:
        row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def get_all_users():
    sql, params = _owned("SELECT * FROM users WHERE 1 = 1", {})
    sql += " ORDER BY id ASC"
    with connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def insert_user(data: dict) -> int:
    scope = _account_scope()
    if scope is _NO_MATCH:
        from database.db import DatabaseError
        raise DatabaseError("api key cannot write profiles")
    with connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO users
                (age, income, expenses, savings, risk_appetite, financial_goals, account_id)
            VALUES (:age, :income, :expenses, :savings, :risk_appetite, :financial_goals, :account_id)
            RETURNING id
            """,
            {
                "age": data["age"],
                "income": data["income"],
                "expenses": data["expenses"],
                "savings": data["savings"],
                "risk_appetite": data["risk_appetite"],
                "financial_goals": data["financial_goals"],
                "account_id": scope,
            },
        )
        conn.commit()
        return cursor.lastrowid


def delete_user(user_id: int) -> bool:
    sql = (
        "SELECT users.id AS id, reports.pdf_path AS pdf_path "
        "FROM users LEFT JOIN reports ON reports.user_id = users.id "
        "WHERE users.id = :user_id"
    )
    sql, params = _owned(sql, {"user_id": user_id}, column="users.account_id")
    with connection() as conn:
        found = conn.execute(sql, params).fetchone()
        if not found:
            return False
        report = found
        conn.execute("DELETE FROM reports WHERE user_id = :user_id", {"user_id": user_id})
        conn.execute("DELETE FROM chat_history WHERE user_id = :user_id", {"user_id": user_id})
        conn.execute("DELETE FROM users WHERE id = :user_id", {"user_id": user_id})
        conn.commit()
    if report is not None:
        remove_pdf(report["pdf_path"])
    return True


def save_report(user_id: int, health_data: dict, ai_report: str) -> None:
    """Store advisory text. PDF location is cleared until a new file is written."""
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO reports (user_id, health_json, ai_report, pdf_path, generated_at)
            VALUES (:user_id, :health_json, :ai_report, NULL, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                health_json  = excluded.health_json,
                ai_report    = excluded.ai_report,
                pdf_path     = NULL,
                generated_at = CURRENT_TIMESTAMP
            """,
            {
                "user_id": user_id,
                "health_json": json.dumps(health_data),
                "ai_report": ai_report,
            },
        )
        conn.commit()


def store_pdf(user_id: int, pdf_bytes: bytes) -> str:
    name = write_pdf(user_id, pdf_bytes)
    with connection() as conn:
        conn.execute(
            "UPDATE reports SET pdf_path = :pdf_path WHERE user_id = :user_id",
            {"pdf_path": name, "user_id": user_id},
        )
        conn.commit()
    return name


def load_report(user_id: int) -> dict | None:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT health_json, ai_report, pdf_path
            FROM reports WHERE user_id = :user_id
            """,
            {"user_id": user_id},
        ).fetchone()
    if not row:
        return None
    health = row["health_json"]
    if isinstance(health, str):
        health = json.loads(health)
    return {
        "health": health,
        "ai_report": row["ai_report"],
        "pdf_ready": resolve(row["pdf_path"]) is not None,
    }


def load_pdf_bytes(user_id: int) -> bytes | None:
    with connection() as conn:
        row = conn.execute(
            "SELECT pdf_path FROM reports WHERE user_id = :user_id",
            {"user_id": user_id},
        ).fetchone()
    if not row:
        return None
    path = resolve(row["pdf_path"])
    if path is None:
        return None
    return path.read_bytes()


def load_chat_history(user_id: int, limit: int = 20) -> list:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT role, message FROM chat_history
            WHERE user_id = :user_id
            ORDER BY id DESC LIMIT :limit
            """,
            {"user_id": user_id, "limit": limit},
        ).fetchall()
    return [{"role": r["role"], "message": r["message"]} for r in reversed(rows)]


def save_chat_turn(user_id: int, user_message: str, ai_message: str) -> None:
    with connection() as conn:
        conn.execute(
            "INSERT INTO chat_history (user_id, role, message) VALUES (:user_id, :role, :message)",
            {"user_id": user_id, "role": "user", "message": user_message},
        )
        conn.execute(
            "INSERT INTO chat_history (user_id, role, message) VALUES (:user_id, :role, :message)",
            {"user_id": user_id, "role": "ai", "message": ai_message},
        )
        conn.commit()


def clear_chat_history(user_id: int) -> None:
    with connection() as conn:
        conn.execute("DELETE FROM chat_history WHERE user_id = :user_id", {"user_id": user_id})
        conn.commit()


def bump_session_version(account_id: int) -> None:
    """Invalidate every device for this account.

    Password reset, password change, email change, and account deletion call
    this together with a revoke of every session row. Logout does not.
    """
    with connection() as conn:
        conn.execute(
            "UPDATE accounts SET session_version = session_version + 1 WHERE id = :account_id",
            {"account_id": int(account_id)},
        )
        conn.commit()


def insert_session(account_id: int, secret_hash: str, user_agent: str) -> dict:
    """One sign-in. expires_at is seven days from this insert and does not slide."""
    agent = (user_agent or "")[:200]
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO sessions (
                account_id, secret_hash, expires_at, last_seen_at, user_agent
            )
            VALUES (
                :account_id,
                :secret_hash,
                CURRENT_TIMESTAMP + INTERVAL '7 days',
                CURRENT_TIMESTAMP,
                :user_agent
            )
            RETURNING id, account_id, expires_at
            """,
            {
                "account_id": int(account_id),
                "secret_hash": secret_hash,
                "user_agent": agent,
            },
        ).fetchone()
        conn.commit()
    return dict(row)


def get_session_by_id(session_id: int):
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = :session_id",
            {"session_id": int(session_id)},
        ).fetchone()
    return dict(row) if row else None


def get_live_session(session_id: int):
    with connection() as conn:
        row = conn.execute(
            """
            SELECT id, account_id, expires_at, revoked_at
            FROM sessions
            WHERE id = :session_id
              AND revoked_at IS NULL
              AND expires_at > CURRENT_TIMESTAMP
            """,
            {"session_id": int(session_id)},
        ).fetchone()
    return dict(row) if row else None


def find_session_by_secret(digest: str):
    """Match the current refresh hash first, then the previous hash."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT id, account_id, secret_hash, previous_secret_hash, expires_at, revoked_at
            FROM sessions
            WHERE secret_hash = :digest OR previous_secret_hash = :digest
            ORDER BY CASE WHEN secret_hash = :digest THEN 0 ELSE 1 END, id DESC
            LIMIT 1
            """,
            {"digest": digest},
        ).fetchone()
    return dict(row) if row else None


def rotate_session_secret(session_id: int, current_hash: str, new_hash: str):
    """Store the new hash and keep the old one. Does not change expires_at."""
    with connection() as conn:
        row = conn.execute(
            """
            UPDATE sessions
            SET previous_secret_hash = secret_hash,
                secret_hash = :new_hash,
                last_seen_at = CURRENT_TIMESTAMP
            WHERE id = :session_id
              AND secret_hash = :current_hash
              AND revoked_at IS NULL
              AND expires_at > CURRENT_TIMESTAMP
            RETURNING id, account_id, expires_at
            """,
            {
                "session_id": int(session_id),
                "current_hash": current_hash,
                "new_hash": new_hash,
            },
        ).fetchone()
        conn.commit()
    return dict(row) if row else None


def revoke_session(session_id: int) -> None:
    with connection() as conn:
        conn.execute(
            """
            UPDATE sessions
            SET revoked_at = CURRENT_TIMESTAMP
            WHERE id = :session_id AND revoked_at IS NULL
            """,
            {"session_id": int(session_id)},
        )
        conn.commit()


def get_account_by_id(account_id: int):
    with connection() as conn:
        row = conn.execute("SELECT * FROM accounts WHERE id = :account_id", {"account_id": account_id}).fetchone()
    return dict(row) if row else None


def get_account_by_email(email: str):
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM accounts WHERE email = :email",
            {"email": email.strip().lower()},
        ).fetchone()
    return dict(row) if row else None


def _credential_scopes(raw: str) -> tuple[str, ...]:
    found = []
    for part in (raw or "").split(","):
        scope = part.strip()
        if scope in _CREDENTIAL_SCOPES and scope not in found:
            found.append(scope)
    return tuple(found)


def issue_api_credential(account_id: int, label: str, scopes: list[str]) -> tuple[str, int]:
    """Store a hash and return the raw key once, plus the row id."""
    name = (label or "").strip()
    if not name:
        raise ValueError("label is required")
    clean = []
    for scope in scopes:
        item = (scope or "").strip()
        if not item or item in clean:
            continue
        if item not in _CREDENTIAL_SCOPES:
            raise ValueError("scopes must be data, llm, or both")
        clean.append(item)
    if not clean:
        raise ValueError("scopes must be data, llm, or both")
    raw_key = secrets.token_urlsafe(32)
    with connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO api_credentials (account_id, label, key_hash, key_sha256, scopes)
            VALUES (:account_id, :label, :key_hash, :key_sha256, :scopes)
            RETURNING id
            """,
            {
                "account_id": int(account_id),
                "label": name,
                "key_hash": generate_password_hash(raw_key),
                "key_sha256": _key_digest(raw_key),
                "scopes": ",".join(clean),
            },
        )
        conn.commit()
        return raw_key, int(cursor.lastrowid)


def revoke_api_credential(credential_id: int) -> None:
    with connection() as conn:
        conn.execute(
            """
            UPDATE api_credentials
            SET revoked_at = CURRENT_TIMESTAMP
            WHERE id = :credential_id AND revoked_at IS NULL
            """,
            {"credential_id": int(credential_id)},
        )
        conn.commit()


def _key_digest(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _credential_row(row) -> dict:
    return {
        "id": row["id"],
        "account_id": row["account_id"],
        "label": row["label"],
        "scopes": _credential_scopes(row["scopes"]),
    }


def find_active_api_credential(raw_key: str):
    """Match a presented key to a live row. The raw key is not stored.

    New keys are found by an indexed SHA-256 digest. Rows issued before that
    column existed still have only a password hash, and those are scanned
    until they are reissued.
    """
    if not raw_key:
        return None
    digest = _key_digest(raw_key)
    with connection() as conn:
        row = conn.execute(
            """
            SELECT id, account_id, label, scopes, key_sha256
            FROM api_credentials
            WHERE revoked_at IS NULL AND key_sha256 = :key_sha256
            """,
            {"key_sha256": digest},
        ).fetchone()
        if row is not None:
            stored = row["key_sha256"] or ""
            if len(stored) == len(digest) and hmac.compare_digest(stored, digest):
                return _credential_row(row)
            return None
        legacy = conn.execute(
            """
            SELECT id, account_id, label, scopes, key_hash
            FROM api_credentials
            WHERE revoked_at IS NULL AND key_sha256 IS NULL
            """
        ).fetchall()
    for old in legacy:
        try:
            matches = check_password_hash(old["key_hash"], raw_key)
        except (TypeError, ValueError):
            matches = False
        if matches:
            return _credential_row(old)
    return None


def mark_email_verified(account_id: int) -> None:
    """Test and bootstrap helper. Signup itself leaves email_verified_at null."""
    with connection() as conn:
        conn.execute(
            """
            UPDATE accounts
            SET email_verified_at = COALESCE(email_verified_at, CURRENT_TIMESTAMP)
            WHERE id = :account_id
            """,
            {"account_id": int(account_id)},
        )
        conn.commit()


def replace_challenge(account_id: int, purpose: str, secret_hash: str, target_email: str | None = None, minutes: int = 30) -> dict:
    """Consume any open row for this account and purpose, then insert a challenge."""
    with connection() as conn:
        conn.execute(
            """
            UPDATE auth_challenges
            SET consumed_at = CURRENT_TIMESTAMP
            WHERE account_id = :account_id
              AND purpose = :purpose
              AND consumed_at IS NULL
            """,
            {"account_id": int(account_id), "purpose": purpose},
        )
        row = conn.execute(
            """
            INSERT INTO auth_challenges (account_id, purpose, secret_hash, target_email, expires_at)
            VALUES (
                :account_id,
                :purpose,
                :secret_hash,
                :target_email,
                CURRENT_TIMESTAMP + (:minutes * INTERVAL '1 minute')
            )
            RETURNING id, expires_at
            """,
            {
                "account_id": int(account_id),
                "purpose": purpose,
                "secret_hash": secret_hash,
                "target_email": target_email,
                "minutes": int(minutes),
            },
        ).fetchone()
        conn.commit()
    return dict(row)


def replace_verify_challenge(account_id: int, secret_hash: str) -> dict:
    """Consume any open verify_email row and insert a new 30-minute challenge."""
    return replace_challenge(int(account_id), "verify_email", secret_hash)


def confirm_verify_challenge(challenge_id: int, secret_hash: str) -> bool:
    """Consume a live matching secret and mark the account verified. One transaction."""
    with connection() as conn:
        row = conn.execute(
            """
            UPDATE auth_challenges
            SET consumed_at = CURRENT_TIMESTAMP
            WHERE id = :challenge_id
              AND purpose = 'verify_email'
              AND secret_hash = :secret_hash
              AND consumed_at IS NULL
              AND expires_at > CURRENT_TIMESTAMP
            RETURNING account_id
            """,
            {"challenge_id": int(challenge_id), "secret_hash": secret_hash},
        ).fetchone()
        if not row:
            conn.rollback()
            return False
        conn.execute(
            """
            UPDATE accounts
            SET email_verified_at = COALESCE(email_verified_at, CURRENT_TIMESTAMP)
            WHERE id = :account_id
            """,
            {"account_id": int(row["account_id"])},
        )
        conn.commit()
    return True


def register_wrong_attempt(challenge_id: int, purpose: str) -> None:
    """Count a wrong secret. The fifth miss consumes the row."""
    with connection() as conn:
        conn.execute(
            """
            UPDATE auth_challenges
            SET attempt_count = attempt_count + 1,
                consumed_at = CASE
                    WHEN attempt_count + 1 >= 5 THEN CURRENT_TIMESTAMP
                    ELSE consumed_at
                END
            WHERE id = :challenge_id
              AND purpose = :purpose
              AND consumed_at IS NULL
            """,
            {"challenge_id": int(challenge_id), "purpose": purpose},
        )
        conn.commit()


def register_wrong_verify_attempt(challenge_id: int) -> None:
    register_wrong_attempt(int(challenge_id), "verify_email")


def get_challenge(challenge_id: int, purpose: str):
    with connection() as conn:
        row = conn.execute(
            """
            SELECT id, account_id, purpose, secret_hash, target_email, expires_at, consumed_at, attempt_count
            FROM auth_challenges
            WHERE id = :challenge_id AND purpose = :purpose
            """,
            {"challenge_id": int(challenge_id), "purpose": purpose},
        ).fetchone()
    return dict(row) if row else None


def get_verify_challenge(challenge_id: int):
    return get_challenge(int(challenge_id), "verify_email")


def get_open_challenge(account_id: int, purpose: str):
    """The newest live challenge for this account and purpose, or None."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT id, account_id, purpose, secret_hash, target_email, expires_at, consumed_at, attempt_count
            FROM auth_challenges
            WHERE account_id = :account_id
              AND purpose = :purpose
              AND consumed_at IS NULL
              AND expires_at > CURRENT_TIMESTAMP
            ORDER BY id DESC
            LIMIT 1
            """,
            {"account_id": int(account_id), "purpose": purpose},
        ).fetchone()
    return dict(row) if row else None


def consume_login_code(challenge_id: int, secret_hash: str) -> bool:
    """Consume a live login_code row when the hash matches."""
    with connection() as conn:
        row = conn.execute(
            """
            UPDATE auth_challenges
            SET consumed_at = CURRENT_TIMESTAMP
            WHERE id = :challenge_id
              AND purpose = 'login_code'
              AND secret_hash = :secret_hash
              AND consumed_at IS NULL
              AND expires_at > CURRENT_TIMESTAMP
            RETURNING id
            """,
            {"challenge_id": int(challenge_id), "secret_hash": secret_hash},
        ).fetchone()
        conn.commit()
    return row is not None


def complete_password_reset(challenge_id: int, secret_hash: str, password: str) -> bool:
    """Consume a live reset secret, replace the password, and sign every device out.

    Scoped API keys are left in place. One transaction.
    """
    password_hash = generate_password_hash(password)
    with connection() as conn:
        row = conn.execute(
            """
            UPDATE auth_challenges
            SET consumed_at = CURRENT_TIMESTAMP
            WHERE id = :challenge_id
              AND purpose = 'reset_password'
              AND secret_hash = :secret_hash
              AND consumed_at IS NULL
              AND expires_at > CURRENT_TIMESTAMP
            RETURNING account_id
            """,
            {"challenge_id": int(challenge_id), "secret_hash": secret_hash},
        ).fetchone()
        if not row:
            conn.rollback()
            return False
        account_id = int(row["account_id"])
        conn.execute(
            """
            UPDATE accounts
            SET password_hash = :password_hash,
                session_version = session_version + 1
            WHERE id = :account_id
            """,
            {"account_id": account_id, "password_hash": password_hash},
        )
        conn.execute(
            """
            UPDATE sessions
            SET revoked_at = CURRENT_TIMESTAMP
            WHERE account_id = :account_id AND revoked_at IS NULL
            """,
            {"account_id": account_id},
        )
        conn.commit()
    return True


def complete_email_change(challenge_id: int, secret_hash: str) -> str:
    """Consume a live change_email secret.

    Returns 'ok' when the address is updated, 'taken' when another account
    already has it (the challenge is still consumed), or 'invalid'.
    """
    with connection() as conn:
        row = conn.execute(
            """
            UPDATE auth_challenges
            SET consumed_at = CURRENT_TIMESTAMP
            WHERE id = :challenge_id
              AND purpose = 'change_email'
              AND secret_hash = :secret_hash
              AND consumed_at IS NULL
              AND expires_at > CURRENT_TIMESTAMP
            RETURNING account_id, target_email
            """,
            {"challenge_id": int(challenge_id), "secret_hash": secret_hash},
        ).fetchone()
        if not row:
            conn.rollback()
            return "invalid"
        account_id = int(row["account_id"])
        target = (row["target_email"] or "").strip().lower()
        if not target:
            conn.commit()
            return "invalid"
        other = conn.execute(
            """
            SELECT id FROM accounts
            WHERE email = :email AND id <> :account_id
            """,
            {"email": target, "account_id": account_id},
        ).fetchone()
        if other:
            conn.commit()
            return "taken"
        try:
            conn.execute(
                """
                UPDATE accounts
                SET email = :email,
                    email_verified_at = CURRENT_TIMESTAMP,
                    session_version = session_version + 1
                WHERE id = :account_id
                """,
                {"email": target, "account_id": account_id},
            )
        except IntegrityConflict:
            conn.rollback()
            conn.execute(
                """
                UPDATE auth_challenges
                SET consumed_at = CURRENT_TIMESTAMP
                WHERE id = :challenge_id AND consumed_at IS NULL
                """,
                {"challenge_id": int(challenge_id)},
            )
            conn.commit()
            return "taken"
        conn.execute(
            """
            UPDATE sessions
            SET revoked_at = CURRENT_TIMESTAMP
            WHERE account_id = :account_id AND revoked_at IS NULL
            """,
            {"account_id": account_id},
        )
        conn.commit()
    return "ok"


def change_password(account_id: int, password: str) -> None:
    """Replace the password hash and sign every device out. One transaction."""
    password_hash = generate_password_hash(password)
    with connection() as conn:
        conn.execute(
            """
            UPDATE accounts
            SET password_hash = :password_hash,
                session_version = session_version + 1
            WHERE id = :account_id
            """,
            {"account_id": int(account_id), "password_hash": password_hash},
        )
        conn.execute(
            """
            UPDATE sessions
            SET revoked_at = CURRENT_TIMESTAMP
            WHERE account_id = :account_id AND revoked_at IS NULL
            """,
            {"account_id": int(account_id)},
        )
        conn.commit()


def delete_account(account_id: int) -> None:
    """Remove one account and the rows that belong to it. One transaction.

    PDF files are removed after the commit. A failed transaction leaves them in place.
    """
    account_id = int(account_id)
    pdf_names: list[str] = []
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT users.id AS user_id, reports.pdf_path AS pdf_path
            FROM users
            LEFT JOIN reports ON reports.user_id = users.id
            WHERE users.account_id = :account_id
            """,
            {"account_id": account_id},
        ).fetchall()
        for row in rows:
            pdf_names.append(file_name_for(row["user_id"]))
            if row["pdf_path"]:
                pdf_names.append(row["pdf_path"])
        conn.execute(
            """
            UPDATE sessions
            SET revoked_at = CURRENT_TIMESTAMP
            WHERE account_id = :account_id AND revoked_at IS NULL
            """,
            {"account_id": account_id},
        )
        conn.execute(
            """
            UPDATE accounts
            SET session_version = session_version + 1
            WHERE id = :account_id
            """,
            {"account_id": account_id},
        )
        conn.execute(
            """
            UPDATE api_credentials
            SET revoked_at = CURRENT_TIMESTAMP
            WHERE account_id = :account_id AND revoked_at IS NULL
            """,
            {"account_id": account_id},
        )
        conn.execute(
            """
            DELETE FROM jobs
            WHERE account_id = :account_id
               OR user_id IN (SELECT id FROM users WHERE account_id = :account_id)
            """,
            {"account_id": account_id},
        )
        conn.execute("DELETE FROM users WHERE account_id = :account_id", {"account_id": account_id})
        conn.execute(
            "DELETE FROM auth_challenges WHERE account_id = :account_id",
            {"account_id": account_id},
        )
        conn.execute("DELETE FROM sessions WHERE account_id = :account_id", {"account_id": account_id})
        conn.execute(
            "DELETE FROM api_credentials WHERE account_id = :account_id",
            {"account_id": account_id},
        )
        conn.execute("DELETE FROM accounts WHERE id = :account_id", {"account_id": account_id})
        conn.commit()
    for name in dict.fromkeys(pdf_names):
        remove_pdf(name)


def insert_account(email: str, password: str) -> dict:
    with connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO accounts (email, password_hash, auth_provider)
            VALUES (:email, :password_hash, 'local')
            RETURNING id
            """,
            {
                "email": email.strip().lower(),
                "password_hash": generate_password_hash(password),
            },
        )
        conn.commit()
        account_id = cursor.lastrowid
    return get_account_by_id(account_id)


def enqueue_report_job(user_id: int, account_id) -> dict:
    """Insert one queued report job, or return the active job if one exists."""
    with connection() as conn:
        existing = _active_report_job(conn, user_id)
        if existing:
            return existing
        try:
            cursor = conn.execute(
                """
                INSERT INTO jobs (kind, account_id, user_id, status)
                VALUES ('report', :account_id, :user_id, 'queued')
                RETURNING id
                """,
                {"account_id": account_id, "user_id": user_id},
            )
            conn.commit()
            return {"job_id": cursor.lastrowid, "status": "queued"}
        except IntegrityConflict:
            conn.rollback()
            existing = _active_report_job(conn, user_id)
            if not existing:
                raise
            return existing


def _active_report_job(conn, user_id: int):
    row = conn.execute(
        """
        SELECT id, status FROM jobs
        WHERE user_id = :user_id AND kind = 'report' AND status IN ('queued', 'running')
        ORDER BY id
        LIMIT 1
        """,
        {"user_id": user_id},
    ).fetchone()
    if not row:
        return None
    return {"job_id": row["id"], "status": row["status"]}


def latest_report_job(user_id: int):
    """Newest report job, omitting a succeeded row so the stored report speaks for it."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT id, status, error_code
            FROM jobs
            WHERE user_id = :user_id AND kind = 'report'
            ORDER BY id DESC
            LIMIT 1
            """,
            {"user_id": user_id},
        ).fetchone()
    if not row or row["status"] == "succeeded":
        return None
    payload = {"job_id": row["id"], "status": row["status"]}
    if row["status"] == "failed":
        payload["error_code"] = row["error_code"]
    return payload


def get_user_for_owner(user_id: int, account_id):
    """Profile row only when it belongs to this job's account. NULL matches NULL."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM users
            WHERE id = :user_id AND account_id IS NOT DISTINCT FROM :account_id
            """,
            {"user_id": user_id, "account_id": account_id},
        ).fetchone()
    return dict(row) if row else None


def fail_stale_report_jobs(timeout_seconds: int) -> None:
    with connection() as conn:
        conn.execute(
            """
            UPDATE jobs
            SET status = 'failed',
                error_code = 'worker_lost',
                error_detail = 'worker_timeout',
                finished_at = CURRENT_TIMESTAMP
            WHERE kind IN ('report', 'chat')
              AND status = 'running'
              AND started_at IS NOT NULL
              AND started_at < CURRENT_TIMESTAMP - make_interval(secs => :timeout_seconds)
            """,
            {"timeout_seconds": int(timeout_seconds)},
        )
        conn.commit()


def enqueue_chat_job(user_id: int, account_id, query: str) -> dict:
    """Queue one chat turn. The worker calls Groq. Many chats may be queued."""
    with connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO jobs (kind, account_id, user_id, status, payload)
            VALUES ('chat', :account_id, :user_id, 'queued', :payload)
            RETURNING id
            """,
            {"account_id": account_id, "user_id": user_id, "payload": query},
        )
        conn.commit()
        return {"job_id": cursor.lastrowid, "status": "queued"}


def latest_chat_job(user_id: int):
    """Newest chat job, omitting a succeeded row because the history has the reply."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT id, status, error_code
            FROM jobs
            WHERE user_id = :user_id AND kind = 'chat'
            ORDER BY id DESC
            LIMIT 1
            """,
            {"user_id": user_id},
        ).fetchone()
    if not row or row["status"] == "succeeded":
        return None
    payload = {"job_id": row["id"], "status": row["status"]}
    if row["status"] == "failed":
        payload["error_code"] = row["error_code"]
    return payload


def claim_next_report_job():
    with connection() as conn:
        row = conn.execute(
            """
            WITH next AS (
                SELECT id FROM jobs
                WHERE kind IN ('report', 'chat') AND status = 'queued'
                ORDER BY id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE jobs
            SET status = 'running',
                attempts = attempts + 1,
                started_at = CURRENT_TIMESTAMP
            FROM next
            WHERE jobs.id = next.id
            RETURNING jobs.id AS id, jobs.kind AS kind, jobs.account_id AS account_id,
                      jobs.user_id AS user_id, jobs.attempts AS attempts,
                      jobs.payload AS payload
            """
        ).fetchone()
        conn.commit()
    return dict(row) if row else None


def finish_report_job(job_id: int, status: str, error_code=None, error_detail=None) -> None:
    with connection() as conn:
        conn.execute(
            """
            UPDATE jobs
            SET status = :status,
                error_code = :error_code,
                error_detail = :error_detail,
                finished_at = CURRENT_TIMESTAMP
            WHERE id = :job_id
            """,
            {
                "status": status,
                "error_code": error_code,
                "error_detail": error_detail,
                "job_id": job_id,
            },
        )
        conn.commit()


def get_report_job(job_id: int):
    with connection() as conn:
        row = conn.execute(
            """
            SELECT id, status, error_code, error_detail, user_id, account_id, attempts
            FROM jobs WHERE id = :job_id
            """,
            {"job_id": job_id},
        ).fetchone()
    return dict(row) if row else None


def attach_orphan_profiles(conn) -> None:
    """Point every unowned profile at the bootstrap account. Reports and chats stay put."""
    from config import Config

    cols = {
        row["name"]
        for row in conn.execute(
            """
            SELECT column_name AS name
            FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = :table_name
            """,
            {"table_name": "users"},
        )
    }
    if "account_id" not in cols:
        return
    orphans = conn.execute("SELECT COUNT(*) AS n FROM users WHERE account_id IS NULL").fetchone()["n"]
    if not orphans:
        return
    email = (Config.BOOTSTRAP_ACCOUNT_EMAIL or "").strip().lower()
    password = Config.BOOTSTRAP_ACCOUNT_PASSWORD or ""
    if not email or not password:
        raise EnvironmentError(
            "Existing profiles have no account. Set BOOTSTRAP_ACCOUNT_EMAIL and "
            "BOOTSTRAP_ACCOUNT_PASSWORD before starting."
        )
    existing = conn.execute(
        "SELECT id FROM accounts WHERE email = :email",
        {"email": email},
    ).fetchone()
    if existing:
        account_id = existing["id"]
    else:
        cursor = conn.execute(
            """
            INSERT INTO accounts (email, password_hash, auth_provider, email_verified_at)
            VALUES (:email, :password_hash, 'local', CURRENT_TIMESTAMP)
            RETURNING id
            """,
            {"email": email, "password_hash": generate_password_hash(password)},
        )
        account_id = cursor.lastrowid
    conn.execute(
        "UPDATE users SET account_id = :account_id WHERE account_id IS NULL",
        {"account_id": account_id},
    )
