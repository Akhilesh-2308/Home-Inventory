import os
import psycopg2
from dotenv import load_dotenv

# Load the .env file
load_dotenv()

database_url = os.getenv("DATABASE_URL")
print(f"Testing connection to: {database_url}")

try:
    conn = psycopg2.connect(database_url)
    print("SUCCESS: Connected to database successfully!")
    conn.close()
except Exception as e:
    print(f"FAILURE: Could not connect to database.\nError: {e}")
