"""load_meters.py - Task 1.2.4: load the 4,000 meter metadata rows into table meters."""
import smart_meter_simulator as sim      # the unchanged generator supplied with the assignment
from db_config import get_connection     # shared connection helper

# One INSERT per meter. %(name)s placeholders are filled from each dictionary's keys,
# so the dictionary keys must match the generator: meter_id, region, customer_type,
# base_power_kw, power_factor.
INSERT_SQL = """
    INSERT INTO meters (meter_id, region, customer_type, base_power_kw, power_factor)
    VALUES (%(meter_id)s, %(region)s, %(customer_type)s, %(base_power_kw)s, %(power_factor)s)
"""


def main():
    # Ask the generator for the metadata: a list of 4,000 dictionaries.
    meters = sim.meter_metadata()
    print(f"Generator returned {len(meters)} meter dictionaries")

    # 'with' commits the transaction when the block ends, and rolls back on error.
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Empty the table first so the script can be re-run safely (the primary key
            # would otherwise reject the second run).
            cur.execute("TRUNCATE meters")

            # Insert every dictionary as one row.
            cur.executemany(INSERT_SQL, meters)

            # Count what is stored, inside the same transaction.
            cur.execute("SELECT count(*) FROM meters")
            stored = cur.fetchone()[0]

    print(f"Rows now stored in meters: {stored}")
    # Stop loudly if the numbers disagree, instead of continuing with bad data.
    assert stored == len(meters) == 4000, "meters should contain exactly 4,000 rows"
    print("OK: meters contains 4,000 rows")


if __name__ == "__main__":
    main()