from supabase import create_client
import os
import datetime
import json
import uuid

def init_supabase():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables")
    
    try:
        # Try the standard initialization first
        return create_client(url, key)
    except TypeError as e:
        if 'proxy' in str(e):
            # Handle older versions of supabase-py that don't accept proxy
            import importlib
            supabase_module = importlib.import_module('supabase')
            client_class = getattr(supabase_module, 'Client', None)
            if client_class:
                return client_class(url, key)
        # If we can't handle it, re-raise
        raise

def process_profile_for_display(profile_data, supabase):
    # Save to database if Supabase is available
    if supabase:
        try:
            process_profile_data(profile_data, supabase)
        except Exception as e:
            print(f"Warning: Failed to save profile data to database: {e}")

def process_profile_data(profile_data, supabase_client=None):
    """Process and save profile data to Supabase."""
    if not supabase_client:
        print("No Supabase client provided, skipping database save")
        return profile_data
    
    # Extract user data
    user = profile_data.get('data', {}).get('user', {})
    if not user:
        print("No user data found in profile_data")
        return profile_data
    
    username = user.get('username')
    
    # Create profile record
    profile_record = {
        'username': username,
        'full_name': user.get('full_name'),
        'biography': user.get('biography'),
        'is_private': user.get('is_private', False),
        'is_verified': user.get('is_verified', False),
        'followers_count': user.get('edge_followed_by', {}).get('count', 0),
        'following_count': user.get('edge_follow', {}).get('count', 0),
        'profile_data': json.dumps(user),  # Store full profile data as JSON
        'last_updated': datetime.datetime.now().isoformat()
    }
    
    # Insert or update profile in database
    try:
        print(f"Saving profile data for {username}")
        response = supabase_client.table('profiles').upsert(profile_record).execute()
        print(f"Profile data saved successfully: {response}")
        
        # Get the profile ID
        profile_query = supabase_client.table('profiles').select('id').eq('username', username).execute()
        profile_id = profile_query.data[0]['id'] if profile_query.data else None
        
        if profile_id:
            # Process posts
            process_posts(user, profile_id, supabase_client)
            
            # Process related profiles
            process_related_profiles(user, profile_id, supabase_client)
        else:
            print(f"Could not find profile ID for {username}")
            
    except Exception as e:
        print(f"Error saving profile data: {e}")
    
    return profile_data

def process_posts(user_data, profile_id, supabase_client):
    """Process and save posts data to Supabase."""
    posts = user_data.get('edge_owner_to_timeline_media', {}).get('edges', [])
    
    for edge in posts:
        node = edge.get('node', {})
        shortcode = node.get('shortcode')
        
        if not shortcode:
            continue
            
        # Get caption
        caption_edges = node.get('edge_media_to_caption', {}).get('edges', [])
        caption = caption_edges[0].get('node', {}).get('text', '') if caption_edges else ''
        
        # Create post record
        post_record = {
            'profile_id': profile_id,
            'shortcode': shortcode,
            'type': node.get('__typename', '').replace('Graph', ''),
            'display_url': node.get('display_url'),
            'timestamp': node.get('taken_at_timestamp'),
            'caption': caption,
            'location': json.dumps(node.get('location', {})),
            'likes_count': node.get('edge_liked_by', {}).get('count', 0),
            'username': user_data.get('username'),
            'created_at': datetime.datetime.now().isoformat()
        }
        
        try:
            # Insert or update post
            post_response = supabase_client.table('posts').upsert(post_record).execute()
            
            # Get post ID
            post_query = supabase_client.table('posts').select('id').eq('shortcode', shortcode).execute()
            post_id = post_query.data[0]['id'] if post_query.data else None
            
            if post_id:
                # Process media for carousel posts
                if node.get('__typename') == 'GraphSidecar':
                    process_post_media(node, post_id, user_data.get('username'), supabase_client)
                else:
                    # Single image/video post
                    media_record = {
                        'post_id': post_id,
                        'type': 'image' if not node.get('is_video') else 'video',
                        'display_url': node.get('display_url'),
                        'media_order': 0,
                        'username': user_data.get('username'),
                        'created_at': datetime.datetime.now().isoformat()
                    }
                    supabase_client.table('post_media').upsert(media_record).execute()
                    
        except Exception as e:
            print(f"Error saving post {shortcode}: {e}")

def process_post_media(node_data, post_id, username, supabase_client):
    """Process and save carousel post media."""
    sidecar_edges = node_data.get('edge_sidecar_to_children', {}).get('edges', [])
    
    for i, child in enumerate(sidecar_edges):
        child_node = child.get('node', {})
        
        media_record = {
            'post_id': post_id,
            'type': 'image' if not child_node.get('is_video') else 'video',
            'display_url': child_node.get('display_url'),
            'media_order': i,
            'username': username,
            'created_at': datetime.datetime.now().isoformat()
        }
        
        try:
            supabase_client.table('post_media').upsert(media_record).execute()
        except Exception as e:
            print(f"Error saving media for post {post_id}, order {i}: {e}")

def process_related_profiles(user_data, profile_id, supabase_client):
    """Process and save related profiles."""
    related_profiles = user_data.get('edge_related_profiles', {}).get('edges', [])
    
    for edge in related_profiles:
        related_node = edge.get('node', {})
        related_username = related_node.get('username')
        
        if not related_username:
            continue
            
        # First, save the related profile basic info
        related_profile = {
            'username': related_username,
            'full_name': related_node.get('full_name'),
            'is_verified': related_node.get('is_verified', False),
            'profile_data': json.dumps(related_node),
            'last_updated': datetime.datetime.now().isoformat()
        }
        
        try:
            # Upsert the related profile
            supabase_client.table('profiles').upsert(related_profile).execute()
            
            # Get the related profile ID
            related_query = supabase_client.table('profiles').select('id').eq('username', related_username).execute()
            related_id = related_query.data[0]['id'] if related_query.data else None
            
            if related_id:
                # Create relationship record
                relationship = {
                    'profile_id': profile_id,
                    'related_profile_id': related_id,
                    'relationship_type': 'related',
                    'created_at': datetime.datetime.now().isoformat()
                }
                
                supabase_client.table('profile_relationships').upsert(relationship).execute()
                
        except Exception as e:
            print(f"Error saving related profile {related_username}: {e}")