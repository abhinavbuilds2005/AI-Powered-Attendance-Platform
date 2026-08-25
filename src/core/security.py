import bcrypt

def hash_pass(pwd: str) -> str:
    """Hash password string using bcrypt."""
    return bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode()

def check_pass(pwd: str, hashed: str) -> bool:
    """Verify password string against hashed password using bcrypt."""
    try:
        return bcrypt.checkpw(pwd.encode(), hashed.encode())
    except (ValueError, TypeError):
        return False
