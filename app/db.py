from dotenv import load_dotenv
import os
from pymongo import MongoClient

# Load environment variables from .env file
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
client = MongoClient(MONGO_URI)

# Main database
db = client["fintech_db"]

# Collections
users_collection = db["users"]
financial_data_collection = db["financial_data"]
