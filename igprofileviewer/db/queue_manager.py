from collections import deque
from typing import List, Dict, Any, Set
import json
from pathlib import Path

class ProfileQueue:
    def __init__(self, batch_size: int = 1, target_count: int = 10):
        self.queue = deque()
        self.batch_size = batch_size
        self.target_count = target_count
        self.processed_count = 0
        self.processed_usernames = set()
        
    def add_to_queue(self, username: str) -> None:
        """Add username to queue if not already processed."""
        if username not in self.processed_usernames and self.processed_count < self.target_count:
            self.queue.append(username)
    
    def mark_processed(self, username: str) -> None:
        """Mark a username as processed."""
        self.processed_usernames.add(username)
        self.processed_count += 1
    
    def get_next_batch(self) -> List[str]:
        """Get next batch of usernames to process."""
        batch = []
        while len(batch) < self.batch_size and self.queue and self.processed_count < self.target_count:
            batch.append(self.queue.popleft())
        return batch
    
    def should_continue(self) -> bool:
        """Check if we should continue processing."""
        return self.processed_count < self.target_count and (len(self.queue) > 0 or len(self.processed_usernames) == 0)
    
    def has_items(self) -> bool:
        """Check if queue has items."""
        return len(self.queue) > 0
    
    def clean_queue(self, supabase) -> None:
        """Remove usernames that already exist in the database from the queue."""
        print("\nCleaning queue...")
        initial_size = len(self.queue)
        
        # Convert deque to list for iteration
        usernames = list(self.queue)
        self.queue.clear()
        
        # Batch process usernames to check existence (50 at a time)
        batch_size = 50
        cleaned_count = 0
        
        for i in range(0, len(usernames), batch_size):
            batch = usernames[i:i + batch_size]
            # Use 'in' operator for more efficient querying
            existing_profiles = supabase.table('profiles').select('username').in_('username', batch).execute()
            existing_usernames = {profile['username'] for profile in existing_profiles.data}
            
            # Add back usernames that don't exist in database
            for username in batch:
                if username not in existing_usernames and username not in self.processed_usernames:
                    self.queue.append(username)
                else:
                    cleaned_count += 1
        
        print(f"Cleaned {cleaned_count} already processed usernames from queue")
        print(f"Queue size reduced from {initial_size} to {len(self.queue)}")
    
    def save_state(self, filepath: str) -> None:
        """Save queue state to file with duplicate removal."""
        # Remove duplicates while maintaining order
        seen = set()
        unique_queue = []
        for username in self.queue:
            if username not in seen and username not in self.processed_usernames:
                seen.add(username)
                unique_queue.append(username)
        
        state = {
            'queue': unique_queue,
            'processed': list(self.processed_usernames)
        }
        with open(filepath, 'w') as f:
            json.dump(state, f)
    
    def load_state(self, filepath: str) -> None:
        """Load queue state from file."""
        if Path(filepath).exists():
            with open(filepath, 'r') as f:
                state = json.load(f)
                self.queue = deque(state['queue'])
                self.processed_usernames = set(state['processed'])