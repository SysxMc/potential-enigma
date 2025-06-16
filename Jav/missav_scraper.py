import requests
from bs4 import BeautifulSoup
import json
import datetime
from tqdm import tqdm
import concurrent.futures
import time
import pickle
from pathlib import Path
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- Configuration ---
FLARESOLVERR_URL = "http://localhost:8191/v1"
PLAYLIST_URL = "https://missav.ws/en/playlists/dprelff6" # Example playlist URL
CACHE_DIR = Path("cache")
CACHE_EXPIRE_HOURS = 24
CONCURRENT_REQUESTS = 10
PROGRESS_FILE = Path("scrape_progress.json")
OUTPUT_FILENAME = "missav_posts.json"

# Create cache directory if it doesn't exist
CACHE_DIR.mkdir(exist_ok=True)

# --- Circuit Breaker State ---
flare_solverr_failures = 0
MAX_FLARE_FAILURES = 5
FLARE_COOLDOWN = 300  # 5 minutes

def get_session():
    """Create a requests session with robust retry logic."""
    session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504]
    )
    session.mount('http://', HTTPAdapter(max_retries=retries))
    session.mount('https://', HTTPAdapter(max_retries=retries))
    return session

def get_cache_key(url):
    """Generate a consistent cache key from a URL."""
    return f"page_{hash(url)}.cache"

def get_page_content(url):
    """
    Fetches page content using FlareSolverr, with caching and a circuit breaker.
    """
    global flare_solverr_failures
    
    cache_file = CACHE_DIR / get_cache_key(url)
    
    # Try to load from cache if it's recent
    if cache_file.exists():
        cache_time = datetime.datetime.fromtimestamp(cache_file.stat().st_mtime)
        if (datetime.datetime.now() - cache_time).total_seconds() < CACHE_EXPIRE_HOURS * 3600:
            with open(cache_file, 'rb') as f:
                return pickle.load(f)
    
    # Check circuit breaker before making a new request
    if flare_solverr_failures >= MAX_FLARE_FAILURES:
        print(f"FlareSolverr circuit breaker tripped. Cooling down for {FLARE_COOLDOWN}s.")
        time.sleep(FLARE_COOLDOWN)
        flare_solverr_failures = 0 # Reset after cooldown
    
    # Fetch fresh content if not cached or expired
    try:
        session = get_session()
        response = session.post(FLARESOLVERR_URL, json={
            "cmd": "request.get",
            "url": url,
            "maxTimeout": 120000
        }, timeout=130) # Timeout for the request to FlareSolverr
        response.raise_for_status()
        content = response.json().get("solution", {}).get("response")

        if not content:
             raise ValueError("Empty response from FlareSolverr")

        flare_solverr_failures = 0  # Reset failure counter on success
        
        # Save successful response to cache
        with open(cache_file, 'wb') as f:
            pickle.dump(content, f)
            
        return content
    except (requests.exceptions.RequestException, ValueError) as e:
        flare_solverr_failures += 1
        print(f"Error fetching page '{url}' with FlareSolverr (failure #{flare_solverr_failures}): {e}")
        return None

def parse_playlist_page(html_content):
    """Parses the playlist page HTML to extract details for each video."""
    if not html_content:
        return []
    soup = BeautifulSoup(html_content, 'html.parser')
    videos = []
    
    playlist_items = soup.find('ul', {'role': 'list', 'class': 'mb-12 space-y-8'})
    
    if playlist_items:
        for li in playlist_items.find_all('li', class_='sm:flex'):
            title_tag = li.find('label', class_='block text-base font-medium text-nord4 line-clamp-1')
            link_tag = li.find('a', alt=True)
            cover_img_tag = li.find('img', class_='w-full')
            preview_video_tag = li.find('video', class_='preview')
            duration_tag = li.find('span', class_='absolute bottom-1 right-1 rounded-lg')
            # --- FIXED: Used 'string' instead of the deprecated 'text' argument ---
            uncensored_tag = li.find('span', string='Uncensored')

            videos.append({
                'title': title_tag.text.strip() if title_tag else 'N/A',
                'link': link_tag['href'] if link_tag else 'N/A',
                'cover_image': cover_img_tag['data-src'] if cover_img_tag and 'data-src' in cover_img_tag.attrs else 'N/A',
                'preview_video': preview_video_tag['data-src'] if preview_video_tag and 'data-src' in preview_video_tag.attrs else 'N/A',
                'duration': duration_tag.text.strip() if duration_tag else 'N/A',
                'uncensored': bool(uncensored_tag)
            })
    return videos

def get_total_pages(base_url):
    """Determines the total number of pages in the playlist from the pagination controls."""
    print(f"Fetching first page to determine total pages from {base_url}...")
    html_content = get_page_content(base_url)
    if not html_content:
        print("Could not fetch first page. Defaulting to 1 page.")
        return 1

    soup = BeautifulSoup(html_content, 'html.parser')
    pagination_container = soup.find('span', class_='relative z-0 inline-flex shadow-sm')
    
    max_page = 1
    if pagination_container:
        page_elements = pagination_container.find_all(['a', 'span'])
        for element in page_elements:
            try:
                page_num = int(element.text.strip())
                if page_num > max_page:
                    max_page = page_num
            except (ValueError, TypeError):
                continue # Ignore non-numeric text like '...' or 'Next'
    
    print(f"Detected {max_page} total pages.")
    return max_page

def fetch_all_playlist_pages(base_url, total_pages):
    """Fetches all videos from a playlist concurrently, with progress saving."""
    all_videos = []
    urls_to_fetch = [f"{base_url}?page={i}" for i in range(1, total_pages + 1)]
    
    # Load progress if it exists
    completed_urls = set()
    if PROGRESS_FILE.exists():
        try:
            with open(PROGRESS_FILE, 'r') as f:
                progress_data = json.load(f)
                completed_urls = set(progress_data.get('completed_urls', []))
                all_videos = progress_data.get('collected_videos', [])
                print(f"Resuming scrape. {len(completed_urls)} pages already completed.")
        except Exception as e:
            print(f"Could not load progress file, starting fresh. Error: {e}")

    # The function to be executed by each thread
    def process_url(url):
        time.sleep(1 / CONCURRENT_REQUESTS) # Basic rate limiting
        html_content = get_page_content(url)
        return parse_playlist_page(html_content) if html_content else []

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENT_REQUESTS) as executor:
            futures = {executor.submit(process_url, url): url for url in urls_to_fetch if url not in completed_urls}
            
            for future in tqdm(concurrent.futures.as_completed(futures), total=len(futures), desc="Fetching pages"):
                url = futures[future]
                try:
                    videos_on_page = future.result()
                    if videos_on_page:
                        all_videos.extend(videos_on_page)
                        completed_urls.add(url)
                    
                    if len(completed_urls) % 10 == 0:
                        with open(PROGRESS_FILE, 'w') as f:
                            json.dump({'completed_urls': list(completed_urls), 'collected_videos': all_videos}, f)
                except Exception as exc:
                    print(f"URL '{url}' generated an exception: {exc}")

    except KeyboardInterrupt:
        print("\nInterrupted by user. Saving progress...")
    finally:
        with open(PROGRESS_FILE, 'w') as f:
            json.dump({'completed_urls': list(completed_urls), 'collected_videos': all_videos}, f)
        print("Progress saved.")

    return all_videos, len(completed_urls)

def save_data_to_json(data, pages_fetched):
    """Saves the final scraped data to a JSON file with rich metadata."""
    metadata = {
        "source_playlist": PLAYLIST_URL,
        # --- FIXED: Used timezone-aware datetime object for UTC ---
        "last_fetched_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "total_posts_scraped": len(data),
        "total_pages_fetched": pages_fetched,
    }
    output = {"metadata": metadata, "posts": data}
    
    with open(OUTPUT_FILENAME, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=4)
        
    print(f"Successfully saved {len(data)} posts from {pages_fetched} pages to '{OUTPUT_FILENAME}'")

if __name__ == "__main__":
    total_pages_to_scrape = get_total_pages(PLAYLIST_URL)
    
    if total_pages_to_scrape > 0:
        scraped_videos, num_pages_fetched = fetch_all_playlist_pages(PLAYLIST_URL, total_pages=total_pages_to_scrape)
        
        if scraped_videos:
            save_data_to_json(scraped_videos, num_pages_fetched)
            if PROGRESS_FILE.exists():
                PROGRESS_FILE.unlink()
        else:
            print("Scraping finished, but no new videos were found.")
