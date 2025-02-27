# processors.py

import json
from datetime import datetime
from igprofileviewer.web.db.queue_manager import ProfileQueue

def process_profile_data(profile_data):
    """Extract relevant profile information from API response."""
    if not isinstance(profile_data, dict):
        raise ValueError(f"Expected dict for profile_data, got {type(profile_data)}")
        
    user = profile_data.get('data', {}).get('user', {})
    if not user:
        raise ValueError("No user data found in profile_data")
        
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