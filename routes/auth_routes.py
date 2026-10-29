import logging
from database.db import IntegrityConflict

from flask import Blueprint, g, jsonify, request
from marshmallow import ValidationError
from werkzeug.security import check_password_hash

from database.repository import (
    change_password,
    delete_account,
    get_account_by_email,
    get_account_by_id,
    insert_account,
    revoke_session,
)
from schemas import (
    change_email_schema,
    change_password_schema,
    delete_account_schema,
    forgot_password_schema,
    login_code_schema,
    login_schema,
    new_password_schema,
    passwords_match,
    signup_schema,
)
from services.rate_limit.gateway import get_gateway
from services.sessions import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    attach_cookies,
    clear_cookies,
    consume_refresh_secret,
    open_session,
    read_token,
    refresh_cookie_max_age,
    revoke_presented_refresh,
)

logger = logging.getLogger(__name__)
auth_bp = Blueprint("auth", __name__)


def _account_body(account: dict):
    return {
        "account_id": account["id"],
        "email": account["email"],
        "email_verified": account.get("email_verified_at") is not None,
    }


def _failed_login(email: str):
    gateway = get_gateway()
    if gateway is not None:
        decision = gateway.note_failed_password(email)
        if decision is not None and not decision.allowed:
            return gateway.denial_response(decision)
    return jsonify({
        "error": "Email or password is incorrect.",
        "code": "invalid_credentials",
    }), 401


def _user_agent() -> str:
    return (request.headers.get("User-Agent") or "")[:200]


def _session_ended():
    resp = jsonify({
        "error": "Your session ended. Sign in again.",
        "code": "session_expired",
    })
    resp.status_code = 401
    return clear_cookies(resp)


def _signed_in(account: dict, status: int, extra: dict | None = None):
    opened = open_session(account["id"], _user_agent())
    body = _account_body(account)
    if extra:
        body.update(extra)
    resp = jsonify(body)
    resp.status_code = status
    return attach_cookies(
        resp,
        account["id"],
        opened["session_id"],
        account["session_version"],
        opened["refresh_secret"],
        refresh_cookie_max_age(opened["expires_at"]),
    )


@auth_bp.route("/auth/signup", methods=["POST"])
def signup():
    """
    Create an account and set the session cookie.
    ---
    tags:
      - Auth
    security: []
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - email
            - password
            - confirm_password
          properties:
            email:
              type: string
              example: person@example.com
            password:
              type: string
              example: correct-horse
            confirm_password:
              type: string
              example: correct-horse
    responses:
      201:
        description: Account created. finpilot_access and finpilot_refresh cookies are set.
      400:
        description: Validation error
      409:
        description: Email already registered
    """
    raw = request.get_json(silent=True)
    if not raw:
        return jsonify({"error": "Invalid or missing JSON body"}), 400
    try:
        data = signup_schema.load(raw)
    except ValidationError as exc:
        return jsonify({"error": "Validation failed", "details": exc.messages}), 400
    if not passwords_match(data):
        return jsonify({
            "error": "Validation failed",
            "details": {"confirm_password": ["confirm password must match password"]},
        }), 400
    if get_account_by_email(data["email"]):
        return jsonify({
            "error": "An account with this email already exists",
            "code": "account_exists",
        }), 409
    try:
        account = insert_account(data["email"], data["password"])
    except IntegrityConflict:
        return jsonify({
            "error": "An account with this email already exists",
            "code": "account_exists",
        }), 409
    from services.verification import SEND_FAILED, send_verification

    extra = None
    if not send_verification(account):
        extra = {"message": SEND_FAILED}
    return _signed_in(account, 201, extra)


@auth_bp.route("/auth/login", methods=["POST"])
def login():
    """
    Sign in and set the session cookie.
    ---
    tags:
      - Auth
    security: []
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - email
            - password
          properties:
            email:
              type: string
              example: bootstrap@finpilot.local
            password:
              type: string
              example: finpilot-bootstrap-local
    responses:
      200:
        description: Signed in. finpilot_access and finpilot_refresh cookies are set.
      401:
        description: Email or password is incorrect
    """
    raw = request.get_json(silent=True)
    if not raw:
        return jsonify({"error": "Invalid or missing JSON body"}), 400
    try:
        data = login_schema.load(raw)
    except ValidationError as exc:
        return jsonify({"error": "Validation failed", "details": exc.messages}), 400
    account = get_account_by_email(data["email"])
    if not account or not account.get("password_hash"):
        return _failed_login(data["email"])
    if not check_password_hash(account["password_hash"], data["password"]):
        return _failed_login(data["email"])
    if account.get("email_verified_at") is None:
        return _signup_link_required(account)
    from services.login_code import code_message, send_login_code

    status, decision = send_login_code(account)
    if status == "limited":
        gateway = get_gateway()
        if gateway is not None and decision is not None:
            return gateway.denial_response(decision)
        return jsonify({"error": "Too many requests. Try again shortly.", "code": "rate_limit_exceeded"}), 429
    if status != "sent":
        return jsonify({
            "error": f"The sign-in code could not be sent to {account['email']}. Try again.",
            "code": "email_delivery_failed",
        }), 503
    resp = jsonify({
        "otp_required": True,
        "email": account["email"],
        "message": code_message(account["email"]),
    })
    return clear_cookies(resp)


def _signup_link_required(account: dict):
    """A correct password on an unconfirmed account sends the signup link and does not sign in."""
    from services.login_code import unconfirmed_message
    from services.verification import send_verification

    recipient = account["email"]
    gateway = get_gateway()
    if gateway is not None:
        decision = gateway.note_resend(recipient)
        if decision is not None and not decision.allowed:
            resp = jsonify({
                "error": unconfirmed_message(recipient),
                "code": "email_unverified",
                "email": recipient,
            })
            resp.status_code = 403
            return clear_cookies(resp)
    if not send_verification(account):
        return jsonify({
            "error": f"The signup link could not be sent to {recipient}. Try again.",
            "code": "email_delivery_failed",
            "email": recipient,
        }), 503
    resp = jsonify({
        "error": unconfirmed_message(recipient),
        "code": "email_unverified",
        "email": recipient,
    })
    resp.status_code = 403
    return clear_cookies(resp)


@auth_bp.route("/auth/login-code", methods=["POST"])
def login_code():
    """
    Finish sign-in with the emailed code. A correct password does not set a cookie by itself.
    ---
    tags:
      - Auth
    security: []
    responses:
      200:
        description: Signed in
      400:
        description: That code is incorrect or expired
    """
    from services.login_code import INVALID_CODE, VerificationStoreError, confirm_login_code

    raw = request.get_json(silent=True)
    if not raw:
        return jsonify({"error": "Invalid or missing JSON body"}), 400
    try:
        data = login_code_schema.load(raw)
    except ValidationError as exc:
        return jsonify({"error": "Validation failed", "details": exc.messages}), 400
    try:
        account = confirm_login_code(data["email"], data["code"])
    except VerificationStoreError as exc:
        gateway = get_gateway()
        if gateway is not None:
            return gateway.denial_response(exc.decision)
        return jsonify({"error": "Rate limit exceeded", "code": "rate_limit_exceeded"}), 429
    if account is None:
        return jsonify({"error": INVALID_CODE, "code": "invalid_code"}), 400
    return _signed_in(account, 200)


@auth_bp.route("/auth/logout", methods=["POST"])
def logout():
    """
    Clear the session cookie.
    ---
    tags:
      - Auth
    security: []
    responses:
      200:
        description: Signed out
    """
    resp = jsonify({"message": "Signed out"})
    token = request.cookies.get(ACCESS_COOKIE, "")
    payload = read_token(token) if token else None
    if payload and payload.get("session_id") is not None:
        revoke_session(int(payload["session_id"]))
    else:
        revoke_presented_refresh(request.cookies.get(REFRESH_COOKIE, ""))
    return clear_cookies(resp)


@auth_bp.route("/auth/refresh", methods=["POST"])
def refresh():
    """
    Rotate the refresh secret and set a new access cookie.
    ---
    tags:
      - Auth
    security: []
    responses:
      200:
        description: New access cookie and refresh cookie
      401:
        description: Refresh secret missing, expired, or reused
    """
    outcome = consume_refresh_secret(request.cookies.get(REFRESH_COOKIE, ""))
    if not isinstance(outcome, dict):
        return _session_ended()
    account = get_account_by_id(int(outcome["account_id"]))
    if not account:
        return _session_ended()
    resp = jsonify(_account_body(account))
    return attach_cookies(
        resp,
        account["id"],
        outcome["session_id"],
        account["session_version"],
        outcome["refresh_secret"],
        refresh_cookie_max_age(outcome["expires_at"]),
    )


@auth_bp.route("/auth/verify-email", methods=["POST"])
def verify_email():
    """
    Confirm a verification link. Opening the link does not consume it.
    ---
    tags:
      - Auth
    security: []
    responses:
      200:
        description: Email verified
      400:
        description: That link is invalid or expired
    """
    from services.verification import INVALID_LINK, VerificationStoreError, describe_challenge

    raw = request.get_json(silent=True) or {}
    try:
        challenge_id = int(raw.get("id"))
    except (TypeError, ValueError):
        return jsonify({"error": INVALID_LINK}), 400
    token = raw.get("token") if isinstance(raw.get("token"), str) else ""
    try:
        outcome = describe_challenge(challenge_id, token)
    except VerificationStoreError as exc:
        gateway = get_gateway()
        if gateway is not None:
            return gateway.denial_response(exc.decision)
        return jsonify({"error": "Rate limit exceeded", "code": "rate_limit_exceeded"}), 429
    if outcome != "ok":
        return jsonify({"error": INVALID_LINK}), 400
    return jsonify({"message": "Email confirmed."})


@auth_bp.route("/auth/resend-verification", methods=["POST"])
def resend_verification():
    """
    Send a new verification link and consume the previous unused one.
    ---
    tags:
      - Auth
    security: []
    responses:
      200:
        description: A new link was sent, or the address is already verified
    """
    from services.verification import send_verification

    actor = getattr(g, "actor", None)
    if actor is None or actor.kind != "user":
        return jsonify({
            "error": "Your session ended. Sign in again.",
            "code": "session_expired",
        }), 401
    account = get_account_by_id(int(actor.credential))
    if not account:
        return jsonify({
            "error": "Your session ended. Sign in again.",
            "code": "session_expired",
        }), 401
    if account.get("email_verified_at") is not None:
        return jsonify({"message": "Email already verified."})
    if not send_verification(account):
        return jsonify({
            "error": "The verification email could not be sent. Try again.",
            "code": "email_delivery_failed",
        }), 503
    return jsonify({"message": "Verification email sent."})


@auth_bp.route("/auth/forgot-password", methods=["POST"])
def forgot_password():
    """
    Ask for a reset link. The response does not say whether the address exists.
    ---
    tags:
      - Auth
    security: []
    responses:
      200:
        description: The same sentence for every address
    """
    from services.password_reset import FORGOT_MESSAGE, send_password_reset

    raw = request.get_json(silent=True)
    if not raw:
        return jsonify({"error": "Invalid or missing JSON body"}), 400
    try:
        data = forgot_password_schema.load(raw)
    except ValidationError as exc:
        return jsonify({"error": "Validation failed", "details": exc.messages}), 400
    account = get_account_by_email(data["email"])
    if account and account.get("email_verified_at") is not None:
        send_password_reset(account)
    return jsonify({"message": FORGOT_MESSAGE})


@auth_bp.route("/auth/reset-password", methods=["POST"])
def reset_password_route():
    """
    Set a new password from a reset link. Opening the link does not consume it.
    ---
    tags:
      - Auth
    security: []
    responses:
      200:
        description: Password replaced. No new session cookie.
      400:
        description: Invalid link, or the new password failed the rules
    """
    from services.password_reset import INVALID_LINK, RESET_DONE, VerificationStoreError, reset_password

    raw = request.get_json(silent=True) or {}
    try:
        data = new_password_schema.load({
            "password": raw.get("password"),
            "confirm_password": raw.get("confirm_password"),
        })
    except ValidationError as exc:
        return jsonify({"error": "Validation failed", "details": exc.messages}), 400
    if not passwords_match(data):
        return jsonify({
            "error": "Validation failed",
            "details": {"confirm_password": ["confirm password must match password"]},
        }), 400
    try:
        challenge_id = int(raw.get("id"))
    except (TypeError, ValueError):
        return jsonify({"error": INVALID_LINK}), 400
    token = raw.get("token") if isinstance(raw.get("token"), str) else ""
    try:
        outcome = reset_password(challenge_id, token, data["password"])
    except VerificationStoreError as exc:
        gateway = get_gateway()
        if gateway is not None:
            return gateway.denial_response(exc.decision)
        return jsonify({"error": "Rate limit exceeded", "code": "rate_limit_exceeded"}), 429
    if outcome != "ok":
        return jsonify({"error": INVALID_LINK}), 400
    resp = jsonify({"message": RESET_DONE})
    return clear_cookies(resp)


def _signed_in_account():
    actor = getattr(g, "actor", None)
    if actor is None or actor.kind != "user":
        return None
    return get_account_by_id(int(actor.credential))


@auth_bp.route("/auth/change-password", methods=["POST"])
def change_password_route():
    """
    Replace the password and sign every device out. This browser is not kept signed in.
    ---
    tags:
      - Auth
    security: []
    responses:
      200:
        description: Password updated. Cookies cleared.
      401:
        description: Wrong current password or signed out
    """
    from services.password_reset import RESET_DONE

    account = _signed_in_account()
    if not account:
        return jsonify({
            "error": "Your session ended. Sign in again.",
            "code": "session_expired",
        }), 401
    raw = request.get_json(silent=True)
    if not raw:
        return jsonify({"error": "Invalid or missing JSON body"}), 400
    try:
        data = change_password_schema.load(raw)
    except ValidationError as exc:
        return jsonify({"error": "Validation failed", "details": exc.messages}), 400
    if not passwords_match(data):
        return jsonify({
            "error": "Validation failed",
            "details": {"confirm_password": ["confirm password must match password"]},
        }), 400
    if not check_password_hash(account["password_hash"], data["current_password"]):
        return _failed_login(account["email"])
    change_password(account["id"], data["password"])
    return clear_cookies(jsonify({"message": RESET_DONE}))


@auth_bp.route("/auth/delete-account", methods=["POST"])
def delete_account_route():
    """
    Delete the signed-in account after the current password and a retyped email.
    ---
    tags:
      - Auth
    security: []
    responses:
      200:
        description: Account deleted
      401:
        description: Wrong current password or signed out
    """
    account = _signed_in_account()
    if not account:
        return jsonify({
            "error": "Your session ended. Sign in again.",
            "code": "session_expired",
        }), 401
    raw = request.get_json(silent=True)
    if not raw:
        return jsonify({"error": "Invalid or missing JSON body"}), 400
    try:
        data = delete_account_schema.load(raw)
    except ValidationError as exc:
        return jsonify({"error": "Validation failed", "details": exc.messages}), 400
    if not check_password_hash(account["password_hash"], data["password"]):
        return _failed_login(account["email"])
    if data["email"] != account["email"]:
        return jsonify({
            "error": "Type the email on this account to confirm.",
            "code": "email_mismatch",
        }), 400
    delete_account(account["id"])
    return clear_cookies(jsonify({"message": "Account deleted."}))


@auth_bp.route("/auth/change-email", methods=["POST"])
def change_email():
    """
    Ask to move this account to a new address. The address changes only after that inbox confirms.
    ---
    tags:
      - Auth
    security: []
    responses:
      200:
        description: Confirmation mail was sent to the new address
      401:
        description: Wrong password or signed out
    """
    from services.email_change import CHANGE_ACCEPTED, request_email_change

    actor = getattr(g, "actor", None)
    if actor is None or actor.kind != "user":
        return jsonify({
            "error": "Your session ended. Sign in again.",
            "code": "session_expired",
        }), 401
    account = get_account_by_id(int(actor.credential))
    if not account:
        return jsonify({
            "error": "Your session ended. Sign in again.",
            "code": "session_expired",
        }), 401
    if account.get("email_verified_at") is None:
        return jsonify({
            "error": "Verify your email before using this part of Monetra.",
            "code": "email_unverified",
        }), 403
    raw = request.get_json(silent=True)
    if not raw:
        return jsonify({"error": "Invalid or missing JSON body"}), 400
    try:
        data = change_email_schema.load(raw)
    except ValidationError as exc:
        return jsonify({"error": "Validation failed", "details": exc.messages}), 400
    if data["email"] == account["email"]:
        return jsonify({
            "error": "That is already the email on this account.",
            "code": "email_unchanged",
        }), 400
    if not check_password_hash(account["password_hash"], data["password"]):
        return _failed_login(account["email"])
    if request_email_change(account, data["email"]) != "sent":
        return jsonify({
            "error": "The confirmation email could not be sent. Try again.",
            "code": "email_delivery_failed",
        }), 503
    return jsonify({"message": CHANGE_ACCEPTED})


@auth_bp.route("/auth/confirm-email", methods=["POST"])
def confirm_email():
    """
    Confirm a new address. Opening the link does not consume it.
    ---
    tags:
      - Auth
    security: []
    responses:
      200:
        description: Email updated. No new session cookie.
      400:
        description: That link is invalid or expired
    """
    from services.email_change import CHANGE_DONE, INVALID_LINK, VerificationStoreError, confirm_email_change

    raw = request.get_json(silent=True) or {}
    try:
        challenge_id = int(raw.get("id"))
    except (TypeError, ValueError):
        return jsonify({"error": INVALID_LINK}), 400
    token = raw.get("token") if isinstance(raw.get("token"), str) else ""
    try:
        outcome = confirm_email_change(challenge_id, token)
    except VerificationStoreError as exc:
        gateway = get_gateway()
        if gateway is not None:
            return gateway.denial_response(exc.decision)
        return jsonify({"error": "Rate limit exceeded", "code": "rate_limit_exceeded"}), 429
    if outcome != "ok":
        return jsonify({"error": INVALID_LINK}), 400
    resp = jsonify({"message": CHANGE_DONE})
    return clear_cookies(resp)


@auth_bp.route("/auth/me", methods=["GET"])
def me():
    """
    Return the signed-in account. Requires a live finpilot_access cookie.
    ---
    tags:
      - Auth
    security: []
    responses:
      200:
        description: Current account
      401:
        description: Session missing or expired
    """
    actor = getattr(g, "actor", None)
    if actor is None or actor.kind != "user":
        return jsonify({
            "error": "Your session ended. Sign in again.",
            "code": "session_expired",
        }), 401
    account = get_account_by_id(int(actor.credential))
    if not account:
        return jsonify({
            "error": "Your session ended. Sign in again.",
            "code": "session_expired",
        }), 401
    return jsonify(_account_body(account))
