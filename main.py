"""
EdgeCase - Practice Management for Independent Therapists
Entry-based architecture test
"""

from core.database import Database
from pathlib import Path

def test_database():
    """Test Entry-based database setup."""
    # Create database in home directory
    db_path = Path.home() / "edgecase_data" / "edgecase.db"
    
    # Delete old database if it exists (fresh start)
    if db_path.exists():
        db_path.unlink()
    
    db = Database(str(db_path))
    
    print("=== Testing Entry-Based Architecture ===\n")
    
    # Test 1: Check default client types were created
    types = db.get_all_client_types()
    print(f"✓ Default client types created: {len(types)}")
    for t in types:
        print(f"  - {t['name']} ({t['code']}) - {t['color']}")
    
    # Test 2: Add a custom client type
    custom_type = db.add_client_type({
        'name': 'Reduced Rate',
        'color': '#0088FF',
        'code': 'RED',
        'file_number_style': 'YYYYMMDD-III',
        'session_fee': 100.0,
        'session_duration': 50,
        'retention_period': 2555
    })
    print(f"\n✓ Created custom type 'Reduced Rate' with ID: {custom_type}")
    
    # Test 3: Add a client
    active_type = types[0]  # Active type
    test_client = {
        'file_number': '20251108-RLS',
        'first_name': 'Richard',
        'middle_name': 'L',
        'last_name': 'Sembera',
        'type_id': active_type['id']
    }
    
    client_id = db.add_client(test_client)
    print(f"✓ Created test client with ID: {client_id}")
    
    # Test 4: Create a Profile entry
    profile_entry = {
        'client_id': client_id,
        'class': 'profile',
        'description': 'Client Profile',
        'content': 'Initial intake information for Richard Sembera.'
    }
    
    entry_id = db.add_entry(profile_entry)
    print(f"✓ Created Profile entry with ID: {entry_id}")
    
    # Test 5: Create a Session entry
    session_entry = {
        'client_id': client_id,
        'class': 'session',
        'description': 'Session Number 1',
        'modality': 'in-person',
        'session_number': 1,
        'service': 'Psychotherapy',
        'duration': 50,
        'fee': 150.0,
        'content': 'First session notes go here...'
    }
    
    session_id = db.add_entry(session_entry)
    print(f"✓ Created Session entry with ID: {session_id}")
    
    # Test 6: Retrieve client entries
    entries = db.get_client_entries(client_id)
    print(f"\n✓ Retrieved {len(entries)} entries for client:")
    for e in entries:
        print(f"  - {e['class']}: {e['description']}")
    
    # Test 7: List all clients
    all_clients = db.get_all_clients()
    print(f"\n✓ Total clients in database: {len(all_clients)}")
    for c in all_clients:
        print(f"  - {c['file_number']}: {c['first_name']} {c['last_name']}")
    
    print("\n✓ Entry-based database setup successful!")

if __name__ == "__main__":
    test_database()