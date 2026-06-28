"""
auth.py — StatMind Magic Link Authentication
FastAPI router — add to main.py with: app.include_router(auth_router)

Dependencies:
  pip install python-jose[cryptography] resend

Environment variables needed:
  RESEND_API_KEY=re_xxxxxxxxxxxx   (free at resend.com — 100 emails/day)
  JWT_SECRET=your-random-secret    (run: python -c "import secrets; print(secrets.token_hex(32))")
  JWT_EXPIRE_MINUTES=10080         (7 days)
"""

import os
import sqlite3
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Header, APIRouter, BackgroundTasks, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from jose import jwt, JWTError

# ── Config ────────────────────────────────────────────────────────────────────
_JWT_SECRET_ENV = os.environ.get('JWT_SECRET')
_IS_PROD = (os.getenv('ENV') or os.getenv('ENVIRONMENT', 'development')).lower() == 'production'
if _JWT_SECRET_ENV:
    JWT_SECRET = _JWT_SECRET_ENV
elif _IS_PROD:
    # Fail fast: a random per-worker secret in prod silently breaks auth across
    # gunicorn workers (token signed by one worker rejected by another) and
    # makes sessions unverifiable. Refuse to start instead.
    raise RuntimeError(
        "JWT_SECRET must be set in production. Generate one with "
        "`python -c \"import secrets; print(secrets.token_hex(32))\"` and set it "
        "in the environment. Refusing to start with a random per-worker secret."
    )
else:
    # Development only: ephemeral secret, with a visible warning.
    JWT_SECRET = secrets.token_hex(32)
    print("[AUTH WARNING] JWT_SECRET not set — using an ephemeral dev secret. "
          "Tokens will not survive a restart. Set JWT_SECRET for stable auth.")
JWT_ALGORITHM   = 'HS256'
JWT_EXPIRE_MINS = int(os.environ.get('JWT_EXPIRE_MINUTES', 10080))  # 7 days
RESEND_API_KEY  = ''  # loaded dynamically in send_magic_link_email()
APP_URL         = os.environ.get('APP_URL', 'https://statmind.tech')
FROM_EMAIL      = 'StatMind <hello@statmind.tech>'
MAGIC_EXPIRE_MINS = 15

auth_router = APIRouter(prefix='/api/v1/auth', tags=['auth'])
security    = HTTPBearer(auto_error=False)

# ── Database ──────────────────────────────────────────────────────────────────
# Use /app/data if it exists (production), otherwise /tmp (CI/test)
_data_dir = '/app/data' if os.path.isdir('/app/data') else os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_data_dir, 'auth.db')
os.makedirs(_data_dir, exist_ok=True)

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db = get_db()
    db.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            email      TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS magic_tokens (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            email      TEXT NOT NULL,
            token_hash TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used       INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS email_captures (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            email      TEXT NOT NULL,
            source     TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    ''')
    db.commit()
    db.close()
    cleanup_expired_tokens()


def cleanup_expired_tokens():
    """Delete used or expired magic tokens so the table doesn't grow unbounded.

    Safe: both used tokens (used=1) and expired tokens (expires_at < now) are
    already non-replayable — verify_magic_link rejects them — so removing them
    deletes only dead rows and never affects a valid pending login. Runs on
    startup; for a low-traffic app that's sufficient to keep the table bounded.
    """
    try:
        db = get_db()
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            'DELETE FROM magic_tokens WHERE used = 1 OR expires_at < ?',
            (now,),
        )
        db.commit()
        db.close()
    except Exception:
        # Cleanup is best-effort; never block startup on it.
        pass

# Run on import
init_db()

# ── Models ────────────────────────────────────────────────────────────────────
class MagicLinkRequest(BaseModel):
    email: str

class VerifyRequest(BaseModel):
    token: str
    email: str

class EmailCaptureRequest(BaseModel):
    email: str
    source: Optional[str] = 'unknown'

# ── JWT helpers ───────────────────────────────────────────────────────────────
def create_jwt(email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINS)
    return jwt.encode(
        {'sub': email, 'exp': expire, 'iat': datetime.now(timezone.utc)},
        JWT_SECRET, algorithm=JWT_ALGORITHM
    )

def decode_jwt(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get('sub')
    except JWTError:
        return None

# ── Auth dependency ───────────────────────────────────────────────────────────
async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[str]:
    if not credentials:
        return None
    return decode_jwt(credentials.credentials)

async def require_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> str:
    email = await get_current_user(credentials)
    if not email:
        raise HTTPException(401, 'Authentication required')
    return email


async def require_admin(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_admin_secret: Optional[str] = Header(default=None, alias="X-Admin-Secret"),
) -> str:
    """Admin-only gate. Requires a valid login AND the correct ADMIN_SECRET
    passed in the X-Admin-Secret header. Protects PII-listing endpoints from
    being readable by any logged-in user."""
    email = await get_current_user(credentials)
    if not email:
        raise HTTPException(401, 'Authentication required')
    admin_secret = os.environ.get('ADMIN_SECRET', '')
    if not admin_secret:
        # No admin secret configured -> deny by default (never open to all).
        raise HTTPException(403, 'Admin access is not configured.')
    if not x_admin_secret or not secrets.compare_digest(x_admin_secret, admin_secret):
        raise HTTPException(403, 'Admin privileges required.')
    return email

# ── Email sender ──────────────────────────────────────────────────────────────
async def send_magic_link_email(email: str, token: str):
    link = f'{APP_URL}/app?auth_token={token}&email={email}'

    RESEND_API_KEY = ''  # loaded dynamically
    RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '')
    if not RESEND_API_KEY:
        # Dev mode — print link to console
        print(f'\n[AUTH DEV MODE] Magic link for {email}:\n{link}\n')
        return True

    import httpx
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                'https://api.resend.com/emails',
                headers={
                    'Authorization': f'Bearer {RESEND_API_KEY}',
                    'Content-Type': 'application/json',
                },
                json={
                    'from': FROM_EMAIL,
                    'to':   [email],
                    'subject': 'Your StatMind sign-in link',
                    'html': f'''
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
             background:#0b0d14;color:#e8eaf0;margin:0;padding:40px 20px">
  <div style="max-width:480px;margin:0 auto">
    <div style="background:linear-gradient(135deg,#6366f1,#818cf8);
                width:48px;height:48px;border-radius:12px;
                display:flex;align-items:center;justify-content:center;
                font-size:22px;font-weight:800;color:#fff;margin-bottom:24px">S</div>
    <h1 style="font-size:24px;font-weight:700;margin:0 0 8px;color:#e8eaf0">
      Sign in to StatMind
    </h1>
    <p style="color:#8b8fa8;font-size:15px;line-height:1.6;margin:0 0 28px">
      Click the button below to sign in. This link expires in {MAGIC_EXPIRE_MINS} minutes
      and can only be used once.
    </p>
    <a href="{link}"
       style="display:inline-block;background:linear-gradient(135deg,#6366f1,#818cf8);
              color:#fff;text-decoration:none;padding:14px 28px;border-radius:10px;
              font-size:15px;font-weight:700;letter-spacing:-.01em">
      Sign in to StatMind →
    </a>
    <p style="color:#4b4f66;font-size:12px;margin-top:28px;line-height:1.6">
      If you didn't request this email, you can safely ignore it.<br>
      This link will expire at {(datetime.now(timezone.utc) + timedelta(minutes=MAGIC_EXPIRE_MINS)).strftime('%H:%M UTC')}.
    </p>
    <hr style="border:none;border-top:1px solid #1e2535;margin:28px 0">
    <p style="color:#4b4f66;font-size:11px;margin:0">
      StatMind · Process Statistics Platform · statmind.tech
    </p>
  </div>
</body>
</html>
''',
                },
                timeout=10.0,
            )
            return r.status_code == 200
    except Exception as e:
        print(f'[AUTH] Email send failed: {e}')
        return False

# ── Routes ────────────────────────────────────────────────────────────────────

@auth_router.post('/magic-link')
async def send_magic_link(body: MagicLinkRequest, background_tasks: BackgroundTasks):
    """Send a magic link to the user's email."""
    email = body.email.strip().lower()
    if not email or '@' not in email:
        raise HTTPException(400, 'Valid email required')

    # Generate a secure token
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=MAGIC_EXPIRE_MINS)).isoformat()

    db = get_db()
    try:
        # Upsert user
        db.execute(
            'INSERT OR IGNORE INTO users (email) VALUES (?)',
            (email,)
        )
        # Store token
        db.execute(
            'INSERT INTO magic_tokens (email, token_hash, expires_at) VALUES (?, ?, ?)',
            (email, token_hash, expires_at)
        )
        db.commit()
    finally:
        db.close()

    # Send email
    background_tasks.add_task(send_magic_link_email, email, raw_token)
    sent = True

    if not sent and RESEND_API_KEY:
        raise HTTPException(500, 'Failed to send email. Please try again.')

    return {
        'success': True,
        'message': f'Magic link sent to {email}. Check your inbox.',
        'expires_in_minutes': MAGIC_EXPIRE_MINS,
        'dev_mode': not bool(os.environ.get('RESEND_API_KEY', '')),
    }


@auth_router.post('/verify')
async def verify_magic_link(body: VerifyRequest):
    """Verify a magic link token and return a JWT."""
    email = body.email.strip().lower()
    token_hash = hashlib.sha256(body.token.encode()).hexdigest()
    now = datetime.now(timezone.utc).isoformat()

    db = get_db()
    try:
        row = db.execute(
            '''SELECT * FROM magic_tokens
               WHERE email = ? AND token_hash = ? AND used = 0 AND expires_at > ?
               ORDER BY created_at DESC LIMIT 1''',
            (email, token_hash, now)
        ).fetchone()

        if not row:
            raise HTTPException(401, 'Invalid or expired magic link')

        # Mark token as used
        db.execute(
            'UPDATE magic_tokens SET used = 1 WHERE id = ?',
            (row['id'],)
        )
        db.commit()
    finally:
        db.close()

    jwt_token = create_jwt(email)
    return {
        'success': True,
        'token': jwt_token,
        'email': email,
        'expires_in_days': JWT_EXPIRE_MINS // 1440,
    }


@auth_router.get('/me')
async def get_me(email: str = Depends(require_auth)):
    """Return the current authenticated user."""
    db = get_db()
    try:
        user = db.execute(
            'SELECT email, created_at FROM users WHERE email = ?',
            (email,)
        ).fetchone()
    finally:
        db.close()

    if not user:
        raise HTTPException(404, 'User not found')

    return {
        'email': user['email'],
        'member_since': user['created_at'],
    }


@auth_router.post('/logout')
async def logout():
    """Logout (client should delete the JWT)."""
    return {'success': True, 'message': 'Logged out. Delete your token client-side.'}


# ── Email capture (enhanced) ──────────────────────────────────────────────────
@auth_router.post('/email-capture')
async def capture_email(body: EmailCaptureRequest):
    """Capture an email address (pre-auth lead capture)."""
    email = body.email.strip().lower()
    if not email or '@' not in email:
        raise HTTPException(400, 'Valid email required')

    db = get_db()
    try:
        db.execute(
            'INSERT INTO email_captures (email, source) VALUES (?, ?)',
            (email, body.source)
        )
        db.commit()
        count = db.execute('SELECT COUNT(*) FROM email_captures').fetchone()[0]
    finally:
        db.close()

    return {
        'success': True,
        'message': 'Email captured',
        'email': email,
    }


# ── Admin: list captured emails (auth required) ───────────────────────────────
@auth_router.get('/admin/emails')
async def list_captured_emails(email: str = Depends(require_admin)):
    """List all captured emails. Requires auth."""
    db = get_db()
    try:
        rows = db.execute(
            'SELECT email, source, created_at FROM email_captures ORDER BY created_at DESC'
        ).fetchall()
        users = db.execute(
            'SELECT email, created_at FROM users ORDER BY created_at DESC'
        ).fetchall()
    finally:
        db.close()

    return {
        'email_captures': [dict(r) for r in rows],
        'registered_users': [dict(r) for r in users],
        'total_captures': len(rows),
        'total_users': len(users),
    }
