"""
schemas.py — Marshmallow request schemas
=========================================
All incoming JSON bodies are validated here before reaching business logic.
Each schema uses strict typing, sensible bounds, and returns clear error messages.
"""

from marshmallow import Schema, fields, validate, validates, ValidationError, pre_load


# ── User / Profile ─────────────────────────────────────────────────────────

class ProfileSchema(Schema):
    age = fields.Integer(
        required=True,
        validate=validate.Range(min=1, max=120, error="age must be between 1 and 120"),
        metadata={"description": "Client age in years"},
    )
    income = fields.Float(
        required=True,
        validate=validate.Range(min=0, error="income cannot be negative"),
        metadata={"description": "Monthly gross income in ₹"},
    )
    expenses = fields.Float(
        required=True,
        validate=validate.Range(min=0, error="expenses cannot be negative"),
        metadata={"description": "Monthly total expenses in ₹"},
    )
    savings = fields.Float(
        required=True,
        validate=validate.Range(min=0, error="savings cannot be negative"),
        metadata={"description": "Monthly savings in ₹"},
    )
    risk_appetite = fields.String(
        required=True,
        validate=validate.OneOf(
            ["low", "medium", "high"],
            error="risk_appetite must be one of: low, medium, high",
        ),
        metadata={"description": "Client risk tolerance"},
    )
    financial_goals = fields.String(
        required=True,
        validate=validate.Length(
            min=3, max=500,
            error="financial_goals must be between 3 and 500 characters",
        ),
        metadata={"description": "Free-text description of financial goals"},
    )
    # Optional — used for debt-to-income scoring
    debt_emi = fields.Float(
        load_default=None,
        validate=validate.Range(min=0, error="debt_emi cannot be negative"),
        metadata={"description": "Total monthly EMI / debt repayments in ₹ (optional)"},
    )

    @pre_load
    def strip_strings(self, data, **kwargs):
        """Strip whitespace from all string fields before validation."""
        for key in ("risk_appetite", "financial_goals"):
            if isinstance(data.get(key), str):
                data[key] = data[key].strip().lower() if key == "risk_appetite" else data[key].strip()
        return data

    @validates("financial_goals")
    def validate_goals_not_whitespace(self, value, **kwargs):
        if not value.strip():
            raise ValidationError("financial_goals must not be blank.")


# ── Report ─────────────────────────────────────────────────────────────────

class GenerateReportSchema(Schema):
    user_id = fields.Integer(
        required=True,
        validate=validate.Range(min=1, error="user_id must be a positive integer"),
        metadata={"description": "ID of the user profile to generate a report for"},
    )


# ── Chat ───────────────────────────────────────────────────────────────────

class ChatSchema(Schema):
    user_id = fields.Integer(
        required=True,
        validate=validate.Range(min=1, error="user_id must be a positive integer"),
    )
    query = fields.String(
        required=True,
        validate=validate.Length(
            min=1, max=2000,
            error="query must be between 1 and 2000 characters",
        ),
        metadata={"description": "The user's question for the AI advisor"},
    )

    @pre_load
    def strip_query(self, data, **kwargs):
        if isinstance(data.get("query"), str):
            data["query"] = data["query"].strip()
        return data

    @validates("query")
    def validate_query_not_blank(self, value, **kwargs):
        if not value.strip():
            raise ValidationError("query must not be blank.")


# ── Goal Feasibility Simulator ─────────────────────────────────────────────

class GoalPlanSchema(Schema):
    user_id = fields.Integer(
        required=True,
        validate=validate.Range(min=1, error="user_id must be a positive integer"),
    )
    goal_name = fields.String(
        load_default="My Goal",
        validate=validate.Length(
            min=1, max=200,
            error="goal_name must be between 1 and 200 characters",
        ),
        metadata={"description": "Name/label for this simulation scenario"},
    )
    target_amount = fields.Float(
        required=True,
        validate=validate.Range(
            min=1, error="target_amount must be greater than 0"
        ),
        metadata={"description": "Goal amount in ₹"},
    )
    time_years = fields.Float(
        required=True,
        validate=validate.Range(
            min=0.5, error="time_years must be at least 0.5 (6 months)"
        ),
        metadata={"description": "Target horizon in years"},
    )

    @pre_load
    def strip_goal_name(self, data, **kwargs):
        if isinstance(data.get("goal_name"), str):
            data["goal_name"] = data["goal_name"].strip()
        return data

    @validates("goal_name")
    def validate_goal_name_not_blank(self, value, **kwargs):
        if value is not None and not value.strip():
            raise ValidationError("goal_name must not be blank.")


# ── Account login ──────────────────────────────────────────────────────────

class SignupSchema(Schema):
    email = fields.Email(required=True, error_messages={"required": "email is required", "invalid": "email must look like an email"})
    password = fields.String(
        required=True,
        validate=validate.Length(min=12, error="password must be at least 12 characters"),
    )
    confirm_password = fields.String(required=True)

    @pre_load
    def normalize_email(self, data, **kwargs):
        if isinstance(data.get("email"), str):
            data["email"] = data["email"].strip().lower()
        return data

class LoginSchema(Schema):
    email = fields.Email(required=True)
    password = fields.String(required=True)

    @pre_load
    def normalize_email(self, data, **kwargs):
        if isinstance(data.get("email"), str):
            data["email"] = data["email"].strip().lower()
        return data


class ForgotPasswordSchema(Schema):
    email = fields.Email(required=True, error_messages={"required": "email is required", "invalid": "email must look like an email"})

    @pre_load
    def normalize_email(self, data, **kwargs):
        if isinstance(data.get("email"), str):
            data["email"] = data["email"].strip().lower()
        return data


class ChangePasswordSchema(Schema):
    current_password = fields.String(
        required=True,
        validate=validate.Length(min=1, error="password is required"),
        error_messages={"required": "password is required"},
    )
    password = fields.String(
        required=True,
        validate=validate.Length(min=12, error="password must be at least 12 characters"),
    )
    confirm_password = fields.String(required=True)


class DeleteAccountSchema(Schema):
    email = fields.Email(required=True, error_messages={"required": "email is required", "invalid": "email must look like an email"})
    password = fields.String(
        required=True,
        validate=validate.Length(min=1, error="password is required"),
        error_messages={"required": "password is required"},
    )

    @pre_load
    def normalize_email(self, data, **kwargs):
        if isinstance(data.get("email"), str):
            data["email"] = data["email"].strip().lower()
        return data


class ChangeEmailSchema(Schema):
    email = fields.Email(required=True, error_messages={"required": "email is required", "invalid": "email must look like an email"})
    password = fields.String(
        required=True,
        validate=validate.Length(min=1, error="password is required"),
        error_messages={"required": "password is required"},
    )

    @pre_load
    def normalize_email(self, data, **kwargs):
        if isinstance(data.get("email"), str):
            data["email"] = data["email"].strip().lower()
        return data


class NewPasswordSchema(Schema):
    password = fields.String(
        required=True,
        validate=validate.Length(min=12, error="password must be at least 12 characters"),
    )
    confirm_password = fields.String(required=True)


def passwords_match(data: dict) -> bool:
    return data.get("password") == data.get("confirm_password")


# ── Singleton instances (import and reuse these) ───────────────────────────

profile_schema         = ProfileSchema()
generate_report_schema = GenerateReportSchema()
chat_schema            = ChatSchema()
goal_plan_schema       = GoalPlanSchema()
signup_schema          = SignupSchema()
login_schema           = LoginSchema()
forgot_password_schema = ForgotPasswordSchema()
new_password_schema    = NewPasswordSchema()
change_email_schema    = ChangeEmailSchema()
change_password_schema = ChangePasswordSchema()
delete_account_schema  = DeleteAccountSchema()