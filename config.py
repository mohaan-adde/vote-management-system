from supabase import create_client, ClientOptions
import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
# optional expose for debug
print("Loaded SUPABASE_URL:", bool(SUPABASE_URL))
print("Loaded SUPABASE_KEY:", bool(SUPABASE_KEY))

supabase = create_client(
    SUPABASE_URL, 
    SUPABASE_KEY,
    options=ClientOptions(
        postgrest_client_timeout=60,
        storage_client_timeout=60
    )
)
