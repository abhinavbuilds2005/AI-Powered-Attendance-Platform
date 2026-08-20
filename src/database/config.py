import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

supabase_url = os.getenv("SUPABASE_URL")
supabase_api = os.getenv("SUPABASE_API") or os.getenv("SUPABASE_KEY")

if not supabase_url or not supabase_api:
    raise ValueError("SUPABASE_URL and SUPABASE_API (or SUPABASE_KEY) environment variables must be set.")

supabase: Client = create_client(supabase_url, supabase_api)
