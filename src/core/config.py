import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    """Application settings matching production environment variables."""
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    # Support both SUPABASE_KEY and SUPABASE_API names
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", os.getenv("SUPABASE_API", ""))

    @property
    def is_configured(self) -> bool:
        return bool(self.SUPABASE_URL and self.SUPABASE_KEY)

settings = Settings()

if not settings.is_configured:
    raise ValueError(
        "Invalid configuration: SUPABASE_URL and SUPABASE_KEY (or SUPABASE_API) env variables are required."
    )
