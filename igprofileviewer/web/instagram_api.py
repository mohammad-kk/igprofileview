import os
import requests
from typing import Optional, Dict, Any
import logging
from datetime import datetime

class InstagramAPI:
    def __init__(self, api_key: Optional[str] = None):
        """Initialize the Instagram API client.
        
        Args:
            api_key (str, optional): API key for authentication. If not provided, 
                                   will try to get from environment variable.
        """
        self.api_key = api_key or os.getenv("INSTAGRAM_API_KEY")
        if not self.api_key:
            raise ValueError("API key must be provided or set in INSTAGRAM_API_KEY environment variable")
            
        self.base_url = "https://api.scrapecreators.com/v1/instagram"
        self.headers = {
            "x-api-key": self.api_key,
            "Accept": "application/json"
        }
        
        # Configure logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def get_profile(self, username: str) -> Dict[str, Any]:
        """Fetch Instagram profile data for a given username.
        
        Args:
            username (str): Instagram username to fetch profile for
            
        Returns:
            dict: Profile data if successful
            
        Raises:
            requests.RequestException: If API request fails
        """
        try:
            url = f"{self.base_url}/profile"
            params = {"handle": username}
            
            response = requests.get(
                url,
                headers=self.headers,
                params=params
            )
            response.raise_for_status()
            
            return response.json()
            
        except requests.RequestException as e:
            self.logger.error(f"Error fetching profile for {username}: {str(e)}")
            raise

    def get_following(self, username: str) -> Dict[str, Any]:
        """Fetch users that a given Instagram user is following.
        
        Args:
            username (str): Instagram username to fetch following list for
            
        Returns:
            dict: Following data if successful
            
        Raises:
            requests.RequestException: If API request fails
        """
        try:
            url = f"{self.base_url}/user/following"
            params = {"handle": username}
            
            response = requests.get(
                url,
                headers=self.headers,
                params=params
            )
            response.raise_for_status()
            
            return response.json()
            
        except requests.RequestException as e:
            self.logger.error(f"Error fetching following list for {username}: {str(e)}")
            raise

def main():
    """Example usage of the InstagramAPI class."""
    try:
        # Initialize API client
        api = InstagramAPI()
        
        # Example username
        username = "example_user"
        
        # Get profile data
        profile_data = api.get_profile(username)
        print(f"\nSuccessfully fetched profile data for {username}")
        
        # Get following data
        following_data = api.get_following(username)
        print(f"\nSuccessfully fetched following data for {username}")
        
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    main()