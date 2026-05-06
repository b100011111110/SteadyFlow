import psycopg2
from faker import Faker
import random

# Initialize Faker
fake = Faker()

# Database connection parameters
conn_params = {
    'dbname': 'mydb',
    'user': 'postgres',
    'password': 'password',
    'host': 'localhost',
    'port': '5432'
}

# Connect to PostgreSQL
try:
    conn = psycopg2.connect(**conn_params)
    cursor = conn.cursor()

    # Generate and insert 500 fake records
    for _ in range(500):
        name = fake.name()
        email = fake.email()
        age = random.randint(18, 90)
        country = fake.country()
        
        insert_query = """
        INSERT INTO users (name, email, age, country)
        VALUES (%s, %s, %s, %s)
        """
        cursor.execute(insert_query, (name, email, age, country))
    
    # Commit the transaction
    conn.commit()
    print("Successfully inserted 500 fake records into the 'users' table.")

except Exception as e:
    print(f"Error: {e}")
    conn.rollback()

finally:
    cursor.close()
    conn.close()