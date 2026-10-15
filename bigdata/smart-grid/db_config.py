"""db_config.py - one place for the database connection used by every program."""
import os
import psycopg  # PostgreSQL driver (psycopg 3)


def get_connection():
    """Open a connection to the assignment database.

    Settings come from environment variables so no password is stored in code.
    The defaults match this project's setup.
    """
    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "smart_meters"),   # database created in 1.1
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD"),             # set in the terminal, see Step 5
    )