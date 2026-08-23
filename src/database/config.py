import os
from dotenv import load_dotenv
from supabase import create_client, Client

# Load .env if present
load_dotenv()

supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_KEY")

if not supabase_url or not supabase_key:
    # Try reading from Streamlit secrets if running in Streamlit compatibility
    try:
        import streamlit as st
        supabase_url = supabase_url or st.secrets.get("SUPABASE_URL")
        supabase_key = supabase_key or st.secrets.get("SUPABASE_KEY")
    except Exception:
        pass

if not supabase_url or not supabase_key:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables or .env file.")

supabase: Client = create_client(supabase_url, supabase_key)