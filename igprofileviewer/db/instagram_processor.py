import asyncio
import aiohttp
from typing import List, Tuple
from .queue_manager import ProfileQueue
from .processors import process_profile_data, process_posts
from .supabase import init_supabase
import traceback  # Add this at the top with other imports

class InstagramProcessor:
    def __init__(self, batch_size: int = 1, target_count: int = 10, queue_state_file: str = None):
        self.api_key = None
        self.supabase = init_supabase()
        self.queue = ProfileQueue(batch_size=batch_size, target_count=target_count)
        self.queue_state_file = queue_state_file

    async def process_single_post(self, post, media_list):
        try:
            # Insert post first
            post_result = self.supabase.table('posts').upsert(post).execute()
            if not post_result.data:
                return f"Failed to insert post"
            
            post_id = post_result.data[0]['id']
            
            # Batch insert all media records
            if media_list:
                media_records = [{**media, 'post_id': post_id} for media in media_list]
                self.supabase.table('post_media').insert(media_records).execute()
            
            return None
            
        except Exception as e:
            return f"Error processing post {post.get('shortcode', 'unknown')}: {str(e)}"

    async def process_posts_parallel(self, posts_data, profile_id, username):
        processed_posts = process_posts(posts_data, profile_id, username)
        if not processed_posts:
            print(f"No posts to process for {username}")
            return []
            
        print(f"Processing {len(processed_posts)} posts for {username}")
        chunk_size = 10
        results = []
        errors = []
        
        for i in range(0, len(processed_posts), chunk_size):
            chunk = processed_posts[i:i + chunk_size]
            tasks = [self.process_single_post(post, media) for post, media in chunk]
            chunk_results = await asyncio.gather(*tasks)
            
            # Handle results
            for result in chunk_results:
                if result is not None:  # None means success, string means error
                    errors.append(result)
                    
        if errors:
            print(f"Encountered {len(errors)} errors while processing posts for {username}:")
            for error in errors[:5]:  # Show first 5 errors
                print(f"- {error}")
                
        return errors

    async def _fetch_profile_data(self, session, username):
        base_url = "https://api.scrapecreators.com/v1/instagram"
        headers = {"x-api-key": self.api_key, "Accept": "application/json"}
        
        async with session.get(f"{base_url}/profile", headers=headers, params={"handle": username}) as response:
            if response.status != 200:
                print(f"Error fetching profile {username}: Status {response.status}")
                return None
            return await response.json()

    async def _process_profile_data(self, profile_data):
        if not profile_data.get('data', {}).get('user'):
            return None
            
        processed_profile = process_profile_data(profile_data)
        if not processed_profile.get('username'):
            return None
            
        try:
            # Remove await since Supabase operations are synchronous
            result = self.supabase.table('profiles').insert(processed_profile).execute()
            if not result.data:
                return None
                
            # Extract related users
            user = profile_data.get('data', {}).get('user', {})
            related_users = []
            for edge in user.get('edge_related_profiles', {}).get('edges', []):
                if username := edge.get('node', {}).get('username'):
                    related_users.append(username)
                    
            return {'profile_id': result.data[0]['id'], 'related_users': related_users}
            
        except Exception as e:
            print(f"Error inserting profile: {str(e)}")
            return None

    async def _process_profile_posts(self, profile_data, profile_id, username):
        user = profile_data.get('data', {}).get('user', {})
        posts_data = user.get('edge_owner_to_timeline_media', {})
        return await self.process_posts_parallel(posts_data, profile_id, username)

    async def process_profile(self, session: aiohttp.ClientSession, username: str) -> Tuple[str, List[str]]:
        try:
            # Fetch profile data first
            profile_data = await self._fetch_profile_data(session, username)
            if not profile_data:
                return username, []

            # Process profile first to get profile_id
            profile_result = await self._process_profile_data(profile_data)
            if not profile_result:
                return username, []

            # Now process posts with the profile_id and check for errors
            posts_errors = await self._process_profile_posts(profile_data, profile_result['profile_id'], username)
            if posts_errors:
                print(f"Completed processing profile {username} with {len(posts_errors)} post errors")
            else:
                print(f"Successfully processed all posts for {username}")
            
            return username, profile_result.get('related_users', [])
            
        except Exception as e:
            print(f"Error processing profile {username}:")
            traceback.print_exc()
            return username, []

    async def process_profiles(self, api_key: str, start_username: str = None):
        self.api_key = api_key
        
        if self.queue_state_file:
            self.queue.load_state(self.queue_state_file)
        
        # Add queue cleaning at startup
        print("Performing initial queue cleanup...")
        self.queue.clean_queue(self.supabase)
        
        if not self.queue.has_items() and self.queue.processed_count == 0 and start_username:
            self.queue.add_to_queue(start_username)
        
        async with aiohttp.ClientSession() as session:
            while self.queue.should_continue():
                # if self.queue.processed_count % 100 == 0:
                #     self.queue.clean_queue(self.supabase)
                
                batch = self.queue.get_next_batch()
                if not batch:
                    continue
                    
                print(f"\nProcessing batch of {len(batch)} profiles...")
                try:
                    # Batch check existing profiles
                    existing_profiles = self.supabase.table('profiles').select('id', 'username').in_('username', batch).execute()
                    existing_usernames = {profile['username'] for profile in existing_profiles.data}
                    
                    # Filter out existing profiles
                    profiles_to_process = [username for username in batch if username not in existing_usernames]
                    
                    # Mark existing profiles as processed
                    for username in existing_usernames:
                        self.queue.mark_processed(username)
                    
                    if not profiles_to_process:
                        continue
                    
                    tasks = [self.process_profile(session, username) for username in profiles_to_process]
                    results = await asyncio.gather(*tasks)
                    
                    for i, (username, related_users) in enumerate(results):
                        original_username = batch[i]
                        verify_profile = self.supabase.table('profiles').select('id').eq('username', original_username).execute()
                        if verify_profile.data:
                            self.queue.mark_processed(original_username)
                            for related_username in related_users:
                                self.queue.add_to_queue(related_username)
                        else:
                            print(f"Error: Profile {original_username} was not found in database after processing")
                        
                        print(f"Progress: {self.queue.processed_count}/{self.queue.target_count} profiles (Queue size: {len(self.queue.queue)})")
                    
                    if self.queue_state_file:
                        self.queue.save_state(self.queue_state_file)
                except Exception as e:
                    print(f"Error processing batch: {str(e)}")
            
            print(f"\nCompleted! Processed {self.queue.processed_count} profiles")
            if self.queue_state_file:
                self.queue.save_state(self.queue_state_file)