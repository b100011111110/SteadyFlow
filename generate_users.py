import psycopg2
from psycopg2 import sql
import random
import string
from faker import Faker

# Initialize Faker
def generate_fake_data(n=500):
    fake = Faker()
    data = []
    for _ in range(n):
        name = fake.name()
        age = random.randint(18, 90)
        email = fake.email()
        data.append((name, age, email))
    return data

def connect_and_insert(data):
    try:
        # Connect to PostgreSQL
        conn = psycopg2.connect(
            host="localhost",
            database="mydb",
            user="postgres",
            password="password"  # Change as needed
        )
        cursor = conn.cursor()

        # Insert data
        insert_query = sql.SQL("INSERT INTO users (name, age, email) VALUES (%s, %s, %s)")
        cursor.executemany(insert_query, data)
        conn.commit()
        print(f"✅ Successfully inserted {len(data)} records.")

    except psycopg2.OperationalError as e:
        print(f"❌ Database connection failed: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if 'conn' in locals():
            cursor.close()
            conn.close()

if __name__ == "__main__":
    print("🚀 Generating 500 fake records...")
    records = generate_fake_data(500)
    print("📦 Data generated. Inserting into database...")
    connect_and_insert(records)