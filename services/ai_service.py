import logging
import time

from groq import APIStatusError, APITimeoutError, Groq, RateLimitError
from config import Config

logger = logging.getLogger(__name__)

# Initialize Groq client (OpenAI-compatible chat completions interface).
client = Groq(
    api_key=Config.GROQ_API_KEY,
    timeout=Config.GROQ_TIMEOUT_SECONDS,
)

# Chat context window (Wave 2): prefer recent turns within a char budget.
CHAT_HISTORY_MAX_MESSAGES = 20
CHAT_HISTORY_CHAR_BUDGET = 8000


# -------------------------------
# SYSTEM PERSONA
# -------------------------------
SYSTEM_PROMPT = """
You are Monetra, a professional personal financial advisor.

You specialize in:
- Budgeting
- Savings strategy
- Investing
- Risk management
- Goal planning
- Indian personal finance

Behavior Rules:
- Always give personalized advice.
- Be practical, not generic.
- Use real examples when useful (SIP, index funds, FD, emergency fund etc.)
- Avoid motivational fluff.
- Keep advice concise but meaningful.
- Sound like a real financial advisor.
- If user says simple things like 'hello', greet warmly and offer help.
"""


def _ai_error(code: str, message: str) -> dict:
    return {"error": message, "code": code}


def http_status_for_ai_code(code: str | None) -> int:
    if code == "upstream_timeout":
        return 504
    if code in ("upstream_rate_limit", "upstream_error"):
        return 503
    return 500


def format_conversation_context(history) -> str:
    """Build recent conversation text, newest-first selection within char budget."""
    if not history or not isinstance(history, list):
        return ""

    selected = history[-CHAT_HISTORY_MAX_MESSAGES:]
    lines_rev = []
    total = 0
    for msg in reversed(selected):
        role = msg.get("role", "user")
        content = msg.get("message") or msg.get("content") or ""
        if not content:
            continue
        line = f"{role}: {content}"
        if total + len(line) + 1 > CHAT_HISTORY_CHAR_BUDGET and lines_rev:
            break
        lines_rev.append(line)
        total += len(line) + 1

    return "\n".join(reversed(lines_rev))


# -------------------------------
# GROQ CALL WRAPPER
# -------------------------------
def ask_gpt(prompt, model=None, max_tokens=None):
    """
    Send a single-turn prompt to the Groq chat completions API.

    Returns
    -------
    tuple[bool, str | dict]
        ``(True, content)`` on success.
        ``(False, {"error", "code"})`` on failure — codes:
        ``upstream_rate_limit`` | ``upstream_timeout`` | ``upstream_error``.
    """
    selected_model = model or Config.GROQ_CHAT_MODEL
    token_budget = max_tokens if max_tokens is not None else Config.GROQ_CHAT_MAX_TOKENS

    if Config.GROQ_STUB:
        delay_ms = 0
        try:
            from flask import has_request_context, request
            if has_request_context():
                delay_ms = int(request.headers.get("X-FinPilot-Stub-Delay-Ms", "0") or 0)
        except (TypeError, ValueError):
            delay_ms = 0
        if delay_ms > 0:
            time.sleep(min(delay_ms, 5000) / 1000)
        return True, "Stubbed advisory. Groq was not called."

    try:
        response = client.chat.completions.create(
            model=selected_model,
            temperature=0.7,
            max_tokens=token_budget,
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        choice = response.choices[0]
        finish_reason = getattr(choice, "finish_reason", None)
        content = (choice.message.content or "").strip()

        if finish_reason == "length":
            logger.warning(
                "ask_gpt: response truncated (finish_reason=length, model=%s, max_tokens=%s, chars=%d)",
                selected_model,
                token_budget,
                len(content),
            )

        return True, content

    except (APITimeoutError, TimeoutError) as exc:
        logger.warning(
            "ask_gpt: Groq timeout after %ss (model=%s): %s",
            Config.GROQ_TIMEOUT_SECONDS,
            selected_model,
            exc,
        )
        return False, _ai_error("upstream_timeout", "AI provider timed out")
    except RateLimitError as exc:
        logger.warning("ask_gpt: Groq rate limit (model=%s): %s", selected_model, exc)
        return False, _ai_error("upstream_rate_limit", str(exc))
    except APIStatusError as exc:
        status = getattr(exc, "status_code", None)
        code = "upstream_rate_limit" if status == 429 else "upstream_error"
        logger.error(
            "ask_gpt: Groq APIStatusError status=%s model=%s: %s",
            status,
            selected_model,
            exc,
        )
        return False, _ai_error(code, str(exc))
    except Exception as exc:
        logger.exception("ask_gpt: Groq completion failed (model=%s)", selected_model)
        return False, _ai_error("upstream_error", str(exc))


# -------------------------------
# FINANCIAL REPORT GENERATION
# -------------------------------
def generate_financial_report(profile, health_data):

    prompt = f"""
Analyze this user profile and generate a professional advisory report.

USER PROFILE
Age: {profile['age']}
Monthly Income: ₹{profile['income']}
Monthly Expenses: ₹{profile['expenses']}
Current Savings: ₹{profile['savings']}
Risk Appetite: {profile['risk_appetite']}
Financial Goal: {profile['financial_goals']}

FINANCIAL HEALTH SCORE:
{health_data['score']}/100

Insights:
{', '.join(health_data['insights'])}

Warnings:
{', '.join(health_data['warnings'])}


Return response in this exact structure:

## Financial Summary
Brief assessment of current financial condition.

## Budget Optimization
Specific spending/saving improvements.

## Investment Recommendations
Suggest practical allocation strategy.
Mention percentages if possible.

## Risk Warnings
Mention financial risks or gaps.

## Goal Strategy
How user should achieve stated goal.

## 30-Day Action Plan
Give 5 actionable next steps.

Rules:
- Keep it practical.
- Use Indian finance examples.
- Personalized advice only.
- No generic textbook content.
"""

    return ask_gpt(
        prompt,
        model=Config.GROQ_REPORT_MODEL,
        max_tokens=Config.GROQ_REPORT_MAX_TOKENS,
    )


# -------------------------------
# CHAT ADVISOR
# -------------------------------
def chat_with_advisor(profile, user_query, history=None):

    conversation_context = format_conversation_context(history)

    prompt = f"""
You are the user's personal financial advisor.

User Financial Profile:
Age: {profile['age']}
Income: ₹{profile['income']}
Expenses: ₹{profile['expenses']}
Savings: ₹{profile['savings']}
Risk Appetite: {profile['risk_appetite']}
Goals: {profile['financial_goals']}

Recent Conversation:
{conversation_context}

Current User Message:
{user_query}

Instructions:
- Use user profile for personalized advice
- Use conversation context if relevant
- If user says hello, greet warmly
- Be concise and practical
"""

    return ask_gpt(
        prompt,
        model=Config.GROQ_CHAT_MODEL,
        max_tokens=Config.GROQ_CHAT_MAX_TOKENS,
    )
