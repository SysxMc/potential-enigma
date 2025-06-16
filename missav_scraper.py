import requests
from bs4 import BeautifulSoup
import json
import datetime
from tqdm import tqdm
import concurrent.futures

FLARESOLVERR_URL = "http://localhost:8191/v1"
PLAYLIST_URL = "https://missav.ws/en/playlists/dprelff6" # Example playlist URL

def get_page_content(url):
    """Fetches page content using FlareSolverr."""
    try:
        response = requests.post(FLARESOLVERR_URL, json={
            "cmd": "request.get",
            "url": url,
            "maxTimeout": 60000
        })
        response.raise_for_status()
        return response.json()["solution"]["response"]
    except requests.exceptions.RequestException as e:
        print(f"Error fetching page with FlareSolverr: {e}")
        return None

def parse_playlist_page(html_content):
    """Parses the playlist page HTML and extracts video details."""
    soup = BeautifulSoup(html_content, 'html.parser')
    videos = []
    
    # The user provided element is <ul role="list" class="mb-12 space-y-8">
    # Each video item is an <li> within this ul
    playlist_items = soup.find('ul', {'role': 'list', 'class': 'mb-12 space-y-8'})
    
    if playlist_items:
        for li in playlist_items.find_all('li', class_='sm:flex'):
            title_tag = li.find('label', class_='block text-base font-medium text-nord4 line-clamp-1')
            title = title_tag.text.strip() if title_tag else 'N/A'

            link_tag = li.find('a', alt=True)
            link = link_tag['href'] if link_tag else 'N/A'

            cover_img_tag = li.find('img', class_='w-full')
            cover_img = cover_img_tag['data-src'] if cover_img_tag and 'data-src' in cover_img_tag.attrs else 'N/A'

            preview_video_tag = li.find('video', class_='preview')
            preview_video = preview_video_tag['data-src'] if preview_video_tag and 'data-src' in preview_video_tag.attrs else 'N/A'

            duration_tag = li.find('span', class_='absolute bottom-1 right-1 rounded-lg px-2 py-1 text-xs text-nord5 bg-gray-800 bg-opacity-75')
            duration = duration_tag.text.strip() if duration_tag else 'N/A'

            uncensored_tag = li.find('span', class_='absolute bottom-1 left-1 rounded-lg px-2 py-1 text-xs text-nord5 bg-blue-800 bg-opacity-75')
            uncensored = True if uncensored_tag and 'Uncensored' in uncensored_tag.text else False

            videos.append({
                'title': title,
                'link': link,
                'cover_image': cover_img,
                'preview_video': preview_video,
                'duration': duration,
                'uncensored': uncensored
            })
    return videos

def get_total_pages(base_url):
    """Determines the total number of pages in the playlist."""
    print(f"Fetching first page to determine total pages from {base_url}...")
    html_content = get_page_content(base_url)
    if not html_content:
        return 1 # Default to 1 if unable to fetch or parse

    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Find the pagination container
    pagination_container = soup.find('span', class_='relative z-0 inline-flex shadow-sm')
    
    max_page = 1
    if pagination_container:
        # Find all 'a' and 'span' tags within the pagination container that contain page numbers
        # This is more general and less dependent on specific classes for page links
        page_elements = pagination_container.find_all(['a', 'span'])
        
        for element in page_elements:
            try:
                page_num = int(element.text.strip())
                if page_num > max_page:
                    max_page = page_num
            except ValueError:
                continue # Ignore non-numeric text like '...' or 'Next'

    print(f"Detected {max_page} total pages.")
    return max_page

def fetch_all_playlist_pages(base_url, total_pages, concurrent_requests=5):
    """Fetches videos from multiple playlist pages concurrently."""
    all_videos = []
    urls_to_fetch = [f"{base_url}?page={i}" for i in range(1, total_pages + 1)]

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_requests) as executor:
        futures = {executor.submit(get_page_content, url): url for url in urls_to_fetch}
        for future in tqdm(concurrent.futures.as_completed(futures), total=len(urls_to_fetch), desc="Fetching pages"):
            url = futures[future]
            try:
                html_content = future.result()
                if html_content:
                    videos_on_page = parse_playlist_page(html_content)
                    all_videos.extend(videos_on_page)
            except Exception as exc:
                print(f"Page {url} generated an exception: {exc}")
    return all_videos, total_pages # Return total_pages as well

def save_data_to_json(data, pages_fetched, filename="missav_posts.json"):
    """Saves the scraped data to a JSON file with metadata."""
    metadata = {
        "last_fetched": datetime.datetime.now().isoformat(),
        "total_posts": len(data),
        "pages_fetched": pages_fetched, # Added pages_fetched
        "missav_playlist_url": PLAYLIST_URL,
        "flare_solverr_url": FLARESOLVERR_URL
    }
    output = {
        "metadata": metadata,
        "posts": data
    }
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=4)
    print(f"Successfully fetched {len(data)} posts from {pages_fetched} pages and saved to {filename}")

if __name__ == "__main__":
    total_pages = get_total_pages(PLAYLIST_URL)
    
    print(f"Starting to fetch MissAV playlist from {PLAYLIST_URL} across {total_pages} pages with 10 concurrent requests...")
    scraped_videos, pages_fetched_count = fetch_all_playlist_pages(PLAYLIST_URL, total_pages=total_pages, concurrent_requests=10)
    
    if scraped_videos:
        save_data_to_json(scraped_videos, pages_fetched_count)
    else:
        print("No videos were scraped.")
