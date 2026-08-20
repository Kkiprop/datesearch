import csv
import pymongo

# MongoDB connection string
MONGO_URI = "mongodb://mongoheydo:dtcaFrR9S9t7ozRS@mongoforheydotech-shard-00-00.5uryy.mongodb.net:27017,mongoforheydotech-shard-00-01.5uryy.mongodb.net:27017,mongoforheydotech-shard-00-02.5uryy.mongodb.net:27017/?authSource=admin&authMechanism=DEFAULT&tls=true&retryWrites=true&appName=Heydo_mongo&w=majority"
DB_NAME = "Payroll_dashboard"
COLLECTION_NAME = "Employee_rates"

# File path for the CSV file
CSV_FILE = "employee_details_unique.csv"

def csv_to_json(csv_file_path):
    """Convert CSV file to a list of JSON objects."""
    data = []
    with open(csv_file_path, mode='r', encoding='utf-8') as file:
        csv_reader = csv.DictReader(file)
        for row in csv_reader:
            # Convert numeric fields to float
            row['Regular Rate'] = float(row['Regular Rate'])
            row['Overtime Rate'] = float(row['Overtime Rate'])
            data.append(row)
    return data

def insert_to_mongodb(data):
    """Insert data into MongoDB collection."""
    try:
        # Connect to MongoDB
        client = pymongo.MongoClient(MONGO_URI)
        db = client[DB_NAME]
        collection = db[COLLECTION_NAME]

        # Insert data into the collection
        result = collection.insert_many(data)
        print(f"Inserted {len(result.inserted_ids)} documents into MongoDB.")

    except Exception as e:
        print(f"An error occurred: {e}")

    finally:
        # Close the connection
        client.close()

if __name__ == "__main__":
    # Convert CSV to JSON
    employee_data = csv_to_json(CSV_FILE)

    # Insert JSON data into MongoDB
    insert_to_mongodb(employee_data)