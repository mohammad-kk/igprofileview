import json
from datetime import datetime
from .queue_manager import ProfileQueue

def process_profile_data(profile_data):
    """Extract relevant profile information from API response."""
    if not isinstance(profile_data, dict):
        raise ValueError(f"Expected dict for profile_data, got {type(profile_data)}")
        
    user = profile_data.get('data', {}).get('user', {})
    if not user:
        raise ValueError("No user data found in profile_data")
        
    # # Add debug logging
    # print(f"Processing user data with fields: {user.keys()}")
    
    try:
        return {
            'username': user.get('username'),
            'full_name': user.get('full_name'),
            'biography': user.get('biography'),
            'followers_count': user.get('edge_followed_by', {}).get('count', 0),
            'following_count': user.get('edge_follow', {}).get('count', 0),
            'is_private': user.get('is_private', False),
            'is_verified': user.get('is_verified', False),
            'profile_data': user,  # Store the entire user object as JSONB
            'last_updated': datetime.now().isoformat(),
            'created_at': datetime.now().isoformat()
        }
    except Exception as e:
        print(f"Error creating profile dict:")
        print(f"Available user data: {json.dumps(user, indent=2)}")
        raise

def process_posts(posts_data, profile_id, username):
    """Process posts data from API response."""
    posts = []
    
    for edge in posts_data.get('edges', []):
        node = edge.get('node', {})
        
        # Handle caption extraction safely
        caption = ''
        caption_edges = node.get('edge_media_to_caption', {}).get('edges', [])
        if caption_edges and len(caption_edges) > 0:
            caption = caption_edges[0].get('node', {}).get('text', '')

        post = {
            'profile_id': profile_id,
            'username': username,
            'type': node.get('__typename', '').replace('Graph', ''),
            'shortcode': node.get('shortcode'),
            'display_url': node.get('display_url'),
            'timestamp': node.get('taken_at_timestamp'),
            'caption': caption,  # Use safely extracted caption
            'likes_count': node.get('edge_liked_by', {}).get('count', 0),
            'location': node.get('location', {}),
            'created_at': datetime.now().isoformat()
        }
        
        # Handle media
        media_list = []
        if node.get('__typename') == 'GraphSidecar':
            # Handle carousel posts
            sidecar_edges = node.get('edge_sidecar_to_children', {}).get('edges', [])
            for idx, child in enumerate(sidecar_edges, 1):
                child_node = child.get('node', {})
                media_list.append({
                    'username': username,  # Add username field
                    'type': child_node.get('__typename', '').replace('Graph', ''),
                    'display_url': child_node.get('display_url'),
                    'media_order': idx
                })
        else:
            # Handle single media posts
            media_list.append({
                'username': username,  # Add username field
                'type': node.get('__typename', '').replace('Graph', ''),
                'display_url': node.get('display_url'),
                'media_order': 1
            })
        
        posts.append((post, media_list))
    
    return posts

# def insert_profile_and_queue_related(supabase, profile_data, queue: ProfileQueue):
#     """Insert profile and queue its related profiles."""
#     # Process and insert main profile
#     processed_profile = process_profile_data(profile_data)
    
#     # Get related profiles
#     related_profiles = profile_data.get('data', {}).get('user', {}).get('edge_related_profiles', {}).get('edges', [])
    
#     # Insert main profile
#     result = supabase.table('profiles').insert(processed_profile).execute()
#     profile_id = result.data[0]['id']
    
#     # Queue related profiles and create relationships
#     for edge in related_profiles:
#         node = edge.get('node', {})
#         username = node.get('username')
        
#         if username:
#             # Add to queue for later processing
#             queue.add_to_queue(username, node)
            
#             try:
#                 # Try to get existing profile ID
#                 related_result = supabase.table('profiles').select('id').eq('username', username).execute()
#                 if related_result.data:
#                     related_profile_id = related_result.data[0]['id']
#                 else:
#                     # Create minimal profile entry
#                     minimal_profile = {
#                         'username': username,
#                         'full_name': node.get('full_name'),
#                         'is_verified': node.get('is_verified', False),
#                         'created_at': datetime.now().isoformat(),
#                         'last_updated': datetime.now().isoformat()
#                     }
#                     related_result = supabase.table('profiles').insert(minimal_profile).execute()
#                     related_profile_id = related_result.data[0]['id']
                
#                 # Insert relationship
#                 relationship = {
#                     'profile_id': profile_id,
#                     'related_profile_id': related_profile_id,
#                     'relationship_type': 'related',
#                     'created_at': datetime.now().isoformat()
#                 }
#                 supabase.table('profile_relationships').insert(relationship).execute()
                
#             except Exception as e:
#                 print(f"Error processing relationship for {username}: {str(e)}")
    
#     return profile_id, len(related_profiles)

# def process_queued_profiles(supabase, queue: ProfileQueue, api):
#     """Process profiles from the queue in batches."""
#     while queue.has_items():
#         batch = queue.get_next_batch()
#         for username, cached_data in batch:
#             try:
#                 # Fetch full profile data
#                 profile_data = api.get_profile(username)
#                 # Process profile and queue its related profiles
#                 insert_profile_and_queue_related(supabase, profile_data, queue)
#                 print(f"Processed queued profile: {username}")
#             except Exception as e:
#                 print(f"Error processing queued profile {username}: {str(e)}")
#                 # Re-queue failed profiles
#                 queue.add_to_queue(username, cached_data)