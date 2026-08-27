import os
from dotenv import load_dotenv
from supabase import create_client, Client

# Load .env if present
load_dotenv()

supabase_url = os.environ.get("SUPABASE_URL", "")
supabase_key = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_API", "")

if not supabase_url or not supabase_key:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY (or SUPABASE_API) must be set in environment variables or .env file.")

supabase: Client = create_client(supabase_url, supabase_key)