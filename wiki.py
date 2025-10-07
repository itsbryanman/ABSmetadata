#!/usr/bin/env python3
"""
Audiobookshelf Author Metadata Updater
Automatically fetches missing author descriptions and images from Wikipedia
"""

import requests
import time
from typing import Optional, Dict
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AudiobookshelfMetadataUpdater:
    def __init__(self, abs_url: str, api_token: str, library_id: str = None):
        """
        Initialize the updater

        Args:
            abs_url: Your Audiobookshelf server URL (e.g., 'http://localhost:13378')
            api_token: Your API token from Audiobookshelf settings
            library_id: Optional library ID to filter authors
        """
        self.abs_url = abs_url.rstrip('/')
        self.library_id = library_id
        self.headers = {'Authorization': f'Bearer {api_token}'}
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
    def get_all_authors(self) -> list:
        """Fetch all authors from Audiobookshelf"""
        try:
            url = f'{self.abs_url}/api/authors'
            if self.library_id:
                url = f'{self.abs_url}/api/libraries/{self.library_id}/authors'
            response = self.session.get(url)
            response.raise_for_status()
            authors = response.json().get('authors', [])
            logger.info(f"Found {len(authors)} authors")
            return authors
        except Exception as e:
            logger.error(f"Error fetching authors: {e}")
            return []
    
    def needs_update(self, author: Dict) -> bool:
        """Check if author needs metadata update"""
        missing_description = not author.get('description')
        missing_image = not author.get('imagePath')
        return missing_description or missing_image
    
    def search_wikipedia(self, author_name: str) -> Optional[Dict]:
        """Search Wikipedia for author information"""
        try:
            # Search for the page
            search_url = "https://en.wikipedia.org/w/api.php"
            search_params = {
                'action': 'query',
                'format': 'json',
                'list': 'search',
                'srsearch': f'{author_name} author writer',
                'srlimit': 1
            }

            headers = {
                'User-Agent': 'AudiobookshelfBot/1.0 (Educational/Personal Use)'
            }

            search_response = requests.get(search_url, params=search_params, headers=headers)
            search_data = search_response.json()
            
            if not search_data.get('query', {}).get('search'):
                logger.warning(f"No Wikipedia page found for {author_name}")
                return None
            
            page_title = search_data['query']['search'][0]['title']
            
            # Get page content and image
            page_params = {
                'action': 'query',
                'format': 'json',
                'titles': page_title,
                'prop': 'extracts|pageimages',
                'exintro': True,
                'explaintext': True,
                'piprop': 'original',
                'redirects': 1
            }
            
            page_response = requests.get(search_url, params=page_params, headers=headers)
            page_data = page_response.json()
            
            pages = page_data.get('query', {}).get('pages', {})
            page_info = next(iter(pages.values()))
            
            result = {
                'description': page_info.get('extract', '').strip(),
                'image_url': page_info.get('original', {}).get('source'),
                'source': f"https://en.wikipedia.org/wiki/{page_title.replace(' ', '_')}"
            }
            
            logger.info(f"Found Wikipedia data for {author_name}")
            return result
            
        except Exception as e:
            logger.error(f"Error searching Wikipedia for {author_name}: {e}")
            return None
    
    def upload_image_url(self, author_id: str, image_url: str) -> bool:
        """Upload image URL to Audiobookshelf"""
        try:
            logger.info(f"Uploading image URL to Audiobookshelf: {image_url}")

            # Audiobookshelf expects a JSON payload with a 'url' field
            upload_response = self.session.post(
                f'{self.abs_url}/api/authors/{author_id}/image',
                json={'url': image_url}
            )

            if upload_response.status_code != 200:
                logger.error(f"Image upload failed with status {upload_response.status_code}: {upload_response.text}")
                upload_response.raise_for_status()

            logger.info(f"Successfully uploaded image for author {author_id}")
            return True

        except Exception as e:
            logger.error(f"Error uploading image for author {author_id}: {e}")
            return False

    def update_author(self, author_id: str, description: str = None, image_url: str = None) -> bool:
        """Update author metadata in Audiobookshelf"""
        try:
            success = True

            # Update description
            if description:
                update_data = {'description': description}
                response = self.session.patch(
                    f'{self.abs_url}/api/authors/{author_id}',
                    json=update_data
                )
                response.raise_for_status()
                logger.info(f"Successfully updated description for author {author_id}")

            # Upload image URL
            if image_url:
                image_success = self.upload_image_url(author_id, image_url)
                success = success and image_success

            return success

        except Exception as e:
            logger.error(f"Error updating author {author_id}: {e}")
            return False
    
    def process_authors(self, dry_run: bool = True, delay: float = 1.0):
        """
        Process all authors and update missing metadata
        
        Args:
            dry_run: If True, only show what would be updated without making changes
            delay: Delay in seconds between Wikipedia API calls to be respectful
        """
        authors = self.get_all_authors()
        
        if not authors:
            logger.error("No authors found or error fetching authors")
            return
        
        updated_count = 0
        skipped_count = 0
        
        for author in authors:
            author_name = author.get('name', 'Unknown')
            author_id = author.get('id')
            
            if not self.needs_update(author):
                logger.info(f"Skipping {author_name} - already has metadata")
                skipped_count += 1
                continue
            
            logger.info(f"Processing {author_name}...")
            
            wiki_data = self.search_wikipedia(author_name)
            
            if wiki_data:
                if dry_run:
                    logger.info(f"[DRY RUN] Would update {author_name}")
                    if wiki_data.get('description'):
                        logger.info(f"  Description: {wiki_data['description'][:100]}...")
                    if wiki_data.get('image_url'):
                        logger.info(f"  Image: {wiki_data['image_url']}")
                else:
                    success = self.update_author(
                        author_id,
                        description=wiki_data.get('description') if not author.get('description') else None,
                        image_url=wiki_data.get('image_url') if not author.get('imagePath') else None
                    )
                    if success:
                        updated_count += 1
            
            # Be respectful to Wikipedia's servers
            time.sleep(delay)
        
        logger.info(f"\nProcessing complete!")
        logger.info(f"Authors updated: {updated_count}")
        logger.info(f"Authors skipped: {skipped_count}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Update Audiobookshelf author metadata from Wikipedia')
    parser.add_argument('--dry-run', action='store_true', help='Run in dry-run mode (no changes will be made)')
    args = parser.parse_args()

    # Configuration
    ABS_URL = "YOUR_URL"
    API_TOKEN = "YOUR_API_TOKEN"
    LIBRARY_ID = "YOUR LIBRARY ID"

    # Create updater instance
    updater = AudiobookshelfMetadataUpdater(ABS_URL, API_TOKEN, LIBRARY_ID)

    if args.dry_run:
        print("Running in DRY RUN mode - no changes will be made")
        print("="*60)
        updater.process_authors(dry_run=True, delay=1.0)
    else:
        print("Running in UPDATE mode - changes will be made")
        print("="*60)
        updater.process_authors(dry_run=False, delay=1.0)


if __name__ == "__main__":
    main()
