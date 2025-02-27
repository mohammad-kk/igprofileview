import os
from flask import Flask, render_template, request, flash, redirect, url_for, send_file, Response
from dotenv import load_dotenv
from instagram_api import InstagramAPI
import json
import requests
from io import BytesIO
import sys
import asyncio
from pathlib import Path

# Add parent directory to path to import from db module
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from igprofileviewer.db.processors import process_profile_data, process_posts
from igprofileviewer.db.supabase import init_supabase

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")

# Initialize Supabase client
supabase = init_supabase()

def process_profile_for_display(profile_data):
    """Process profile data for display in templates."""
    user = profile_data.get('data', {}).get('user', {})
    if not user:
        return None
    
    # Create a simplified profile dictionary
    profile = {
        'username': user.get('username'),
        'full_name': user.get('full_name'),
        'biography': user.get('biography'),
        'is_verified': user.get('is_verified', False),
        'is_private': user.get('is_private', False),
        'followers_count': user.get('edge_followed_by', {}).get('count', 0),
        'following_count': user.get('edge_follow', {}).get('count', 0),
        'external_url': user.get('external_url'),
        'profile_pic_url': user.get('profile_pic_url'),
        'profile_pic_url_hd': user.get('profile_pic_url_hd'),
    }
    
    # Process posts with improved image handling
    posts = []
    for edge in user.get('edge_owner_to_timeline_media', {}).get('edges', [])[:18]:  # Get first 18 posts
        node = edge.get('node', {})
        
        # Get caption
        caption_edges = node.get('edge_media_to_caption', {}).get('edges', [])
        caption = caption_edges[0].get('node', {}).get('text', '') if caption_edges else ''
        
        # Handle different post types
        post_images = []
        
        if node.get('__typename') == 'GraphSidecar':
            # This is a carousel post - get all images
            sidecar_edges = node.get('edge_sidecar_to_children', {}).get('edges', [])
            for child in sidecar_edges:
                child_node = child.get('node', {})
                # Use the exact URL as provided by the API
                post_images.append({
                    'display_url': child_node.get('display_url'),
                    'accessibility_caption': child_node.get('accessibility_caption', '')
                })
        else:
            # Single image post
            post_images.append({
                'display_url': node.get('display_url'),
                'accessibility_caption': node.get('accessibility_caption', '')
            })
        
        # Create post entry with all image-related information
        post_entry = {
            'type': node.get('__typename', '').replace('Graph', ''),
            'shortcode': node.get('shortcode'),
            'display_url': node.get('display_url'),  # Main display URL
            'thumbnail_src': node.get('thumbnail_src'),
            'images': post_images,
            'caption': caption,
            'likes_count': node.get('edge_liked_by', {}).get('count', 0),
            'comments_count': node.get('edge_media_to_comment', {}).get('count', 0),
            # Add these to help with debugging
            'is_video': node.get('is_video', False),
            'post_type': node.get('__typename', '')
        }
        
        posts.append(post_entry)
    
    # Add related users
    related_users = []
    edge_related_profiles = user.get('edge_related_profiles', {}).get('edges', [])
    for edge in edge_related_profiles:
        related_node = edge.get('node', {})
        related_users.append({
            'username': related_node.get('username'),
            'full_name': related_node.get('full_name'),
            'profile_pic_url': related_node.get('profile_pic_url'),
            'is_verified': related_node.get('is_verified', False)
        })
    
    profile['posts'] = posts
    profile['related_users'] = related_users
    return profile

def store_complete_profile_data(profile_data):
    """Process and store profile data with posts in Supabase database."""
    try:
        # Process the profile data for database storage
        processed_profile = process_profile_data(profile_data)
        
        if not processed_profile.get('username'):
            return False, "Could not process profile data"
        
        username = processed_profile['username']
            
        # Check if profile already exists
        existing = supabase.table('profiles').select('id').eq('username', username).execute()
        
        # Insert or update profile
        if existing.data:
            # Profile exists, update it
            profile_id = existing.data[0]['id']
            supabase.table('profiles').update(processed_profile).eq('id', profile_id).execute()
        else:
            # Insert new profile
            result = supabase.table('profiles').insert(processed_profile).execute()
            if not result.data:
                return False, "Failed to save profile"
            profile_id = result.data[0]['id']
            
        # Process posts data
        user = profile_data.get('data', {}).get('user', {})
        posts_data = user.get('edge_owner_to_timeline_media', {})
        processed_posts = process_posts(posts_data, profile_id, username)
        
        posts_saved = 0
        for post, media_list in processed_posts:
            try:
                # Insert post
                post_result = supabase.table('posts').upsert(post).execute()
                if post_result.data:
                    post_id = post_result.data[0]['id']
                    posts_saved += 1
                    
                    # Insert media for this post
                    if media_list:
                        media_records = [{**media, 'post_id': post_id} for media in media_list]
                        supabase.table('post_media').insert(media_records).execute()
            except Exception as post_error:
                # Log error but continue with other posts
                print(f"Error saving post: {str(post_error)}")
                
        return True, f"Saved profile and {posts_saved} posts for {username}"
                
    except Exception as e:
        return False, f"Database error: {str(e)}"

@app.route('/', methods=['GET', 'POST'])
def index():
    """Home page with search form."""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        if not username:
            flash('Please enter a username', 'error')
            return redirect(url_for('index'))
        
        return redirect(url_for('profile', username=username))
    
    return render_template('index.html')

@app.route('/profile/<username>')
def profile(username):
    """Display profile information for a given username."""
    try:
        api = InstagramAPI()
        profile_data = api.get_profile(username)
        
        processed_profile = process_profile_for_display(profile_data)
        if not processed_profile:
            flash('No profile data found for this username', 'error')
            return redirect(url_for('index'))
        
        # Store complete profile data including posts
        success, message = store_complete_profile_data(profile_data)
        if success:
            flash(message, 'info')
        else:
            flash(message, 'warning')
        
        return render_template('profile.html', profile=processed_profile)
        
    except Exception as e:
        flash(f'Error fetching profile: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/image-proxy')
def image_proxy():
    """Proxy images from Instagram to bypass CORS and referrer restrictions."""
    url = request.args.get('url')
    if not url:
        return "No URL provided", 400
    
    try:
        # Use custom headers to bypass restrictions
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
            'Referer': 'https://www.instagram.com/',
        }
        
        # Make request to get the image
        response = requests.get(url, headers=headers, stream=True)
        response.raise_for_status()
        
        # Create in-memory file-like object with the image data
        img_io = BytesIO(response.content)
        
        # Determine content type
        content_type = response.headers.get('Content-Type', 'image/jpeg')
        
        # Send image directly to client
        return send_file(
            img_io,
            mimetype=content_type,
            as_attachment=False,
            download_name=url.split('/')[-1]
        )
    
    except Exception as e:
        return f"Error loading image: {str(e)}", 500

@app.route('/embed/<shortcode>')
def embed_post(shortcode):
    """Get Instagram oEmbed HTML for a post."""
    try:
        embed_url = f"https://api.instagram.com/oembed/?url=https://www.instagram.com/p/{shortcode}/&omitscript=true"
        response = requests.get(embed_url)
        response.raise_for_status()
        data = response.json()
        return render_template('embed.html', embed_html=data['html'], shortcode=shortcode)
    except Exception as e:
        return f"Error embedding post: {str(e)}", 500

if __name__ == '__main__':
    app.run(debug=True) 