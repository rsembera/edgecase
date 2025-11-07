"""
EdgeCase - Practice Management for Independent Therapists
"""

from core.database import Database
from pathlib import Path

def test_database():
    """Test database setup."""
    # Create database in home directory
    db_path = Path.home() / "edgecase_data" / "edgecase.db"
    db = Database(str(db_path))
    
    # Add a test client
    test_client = {
        'file_number': '20251206-TEST',
        'name': 'Test Client',
        'phone': '555-1234',
        'email': 'test@example.com',
        'client_type': 'active'
    }
    
    client_id = db.add_client(test_client)
    print(f"✓ Created test client with ID: {client_id}")
    
    # Retrieve client
    client = db.get_client(client_id)
    print(f"✓ Retrieved client: {client['name']}")
    
    # List all clients
    all_clients = db.get_all_clients()
    print(f"✓ Total clients in database: {len(all_clients)}")
    
    print("\n✓ Database setup successful!")

if __name__ == "__main__":
    test_database()