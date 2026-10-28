"""Initialize the SQL schema, adding sample events only when events table is empty.

Run once from EC2 after loading .env: python scripts/init_db.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")
from services.sql_db import initialize_schema, check_connection

if __name__ == "__main__":
    initialize_schema(seed=True)
    check_connection()
    print("Connected to SQL database; schema ready; sample events present if database was empty.")
