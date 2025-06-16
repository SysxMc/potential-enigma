import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
import json
from tqdm.asyncio import tqdm
from datetime import datetime, timedelta
from urllib.parse import quote_plus

PROXY_API_URL = "https://fetch.mrspidyxd.workers.dev/"

async def fetch_posts(session, url):
    try:
        # Send a request to the new proxy API
        # URL-encode the target URL before passing it as a parameter to the proxy
        encoded_url = quote_plus(url)
        proxy_url = f"{PROXY_API_URL}?url={encoded_url}"
        
        async with session.get(proxy_url) as response:
            response.raise_for_status()
            html_content = await response.text()
        
    except aiohttp.ClientError as e:
        print(f"Error communicating with proxy API or fetching URL: {e}")
        return []

    soup = BeautifulSoup(html_content, 'html.parser')
    
    posts_data = []
    
    # The main content area containing the posts
    content_div = soup.find('div', id='content', class_='site-content')
    if not content_div:
        # print(f"Could not find the main content div for {url}. This might indicate the proxy failed to get the correct page content.")
        return []

    # Find all individual post articles within the content area
    # Based on the provided HTML, each post is within a div with class 'inside-article'
    articles = content_div.find_all('div', class_='inside-article')

    if not articles:
        # print(f"No articles found for {url}. Check the HTML structure and selectors.")
        return []

    for article in articles:
        post = {}

        # Post URL and Title
        title_link = article.find('div', class_='grid1').find('a')
        if title_link:
            post['title'] = title_link.get_text(strip=True)
            post['url'] = title_link['href']
        else:
            post['title'] = 'N/A'
            post['url'] = 'N/A'

        # Image URL
        img_tag = article.find('div', class_='imgg').find('img')
        if img_tag:
            post['image_url'] = img_tag['src']
        else:
            post['image_url'] = 'N/A'

        # Tags
        tags_p = article.find('p', class_='tags')
        if tags_p:
            tags = [a.get_text(strip=True) for a in tags_p.find_all('a')]
            post['tags'] = ', '.join(tags)
        else:
            post['tags'] = 'N/A'

        # Stats (Views, Hearts, Comments) and Date
        javstats_div = article.find('div', class_='javstats')
        if javstats_div:
            stats_text = javstats_div.get_text(strip=True)
            
            # Regex to extract numbers for views, hearts, comments
            views_match = re.search(r'(\d{1,3}(?:,\d{3})*)\s*\S*\s*(\d+)\s*\S*\s*(\d+)', stats_text)
            if views_match:
                post['views'] = views_match.group(1).replace(',', '')
                post['hearts'] = views_match.group(2)
                post['comments'] = views_match.group(3)
            else:
                post['views'] = 'N/A'
                post['hearts'] = 'N/A'
                post['comments'] = 'N/A'
        else:
            post['views'] = 'N/A'
            post['hearts'] = 'N/A'
            post['comments'] = 'N/A'

        date_div = article.find('div', class_='date')
        if date_div:
            post['date'] = date_div.get_text(strip=True)
        else:
            post['date'] = 'N/A'

        posts_data.append(post)
    
    return posts_data

async def scrape_jav_guru(session, num_pages_to_scrape=10):
    base_url = "https://jav.guru/"
    all_posts = []

    urls_to_fetch = []
    for page_num in range(1, num_pages_to_scrape + 1):
        if page_num == 1:
            urls_to_fetch.append(base_url)
        else:
            urls_to_fetch.append(f"{base_url}page/{page_num}/")
    
    print(f"\n--- Scraping {num_pages_to_scrape} pages from {base_url} ---")
    tasks = [fetch_posts(session, url) for url in urls_to_fetch]
    
    for posts_on_page in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Scraping jav.guru pages"):
        page_posts = await posts_on_page
        if page_posts:
            all_posts.extend(page_posts)
    
    return all_posts

async def scrape_onejav(session, num_load_more_clicks=20): # Set to 20 for ~3 weeks of data
    base_url = "https://onejav.com/"
    all_posts = []
    
    print(f"\n--- Scraping {base_url} (with {num_load_more_clicks} 'Load more' clicks) ---")

    # Initial page fetch
    initial_url = base_url
    html_content = await fetch_page_content(session, initial_url)
    if not html_content:
        print(f"Failed to fetch initial page from {initial_url}")
        return []

    soup = BeautifulSoup(html_content, 'html.parser')
    all_posts.extend(parse_onejav_posts(soup))

    # Simulate "Load more" clicks based on the JavaScript logic
    # The script makes a GET request to '/' with 'action=overview' and 'currentdate' parameters.
    for i in tqdm(range(num_load_more_clicks), desc="Loading more onejav.com posts"):
        # Find the last data-date from the 'card-overview' elements
        last_card_overview = soup.find_all('div', class_='card-overview')
        if not last_card_overview:
            # print("No more 'card-overview' elements found. Stopping 'Load more' simulation.")
            break
        
        current_date_param = last_card_overview[-1].get('data-date')
        if not current_date_param:
            # print("Could not find 'data-date' attribute on the last card-overview. Stopping 'Load more' simulation.")
            break

        # Construct the URL for the next load
        # The JavaScript uses url: '/', data: {'action': 'overview', 'currentdate': ...}
        next_load_url = f"{base_url}?action=overview&currentdate={current_date_param}"
        
        html_content = await fetch_page_content(session, next_load_url)
        if html_content:
            new_soup = BeautifulSoup(html_content, 'html.parser')
            # The new content is appended to #overview_list, so we need to parse it from the new_soup
            # and then update the main soup object to find the next 'last_card_overview'
            new_posts = parse_onejav_posts(new_soup)
            if new_posts:
                all_posts.extend(new_posts)
                # To correctly find the next 'last_card_overview', we need to update the soup
                # with the newly loaded content. This is tricky with simple concatenation.
                # A more robust way is to re-parse the entire accumulated HTML, but that's inefficient.
                # For simplicity, we'll assume the new_soup contains the *new* overview cards
                # and we can continue finding the last one from there.
                soup = new_soup # Update soup to continue from the newly loaded content
            else:
                # print(f"No new posts found for {next_load_url}. Stopping 'Load more' simulation.")
                break
        else:
            # print(f"Failed to fetch content for {next_load_url}. Stopping 'Load more' simulation.")
            break

    return all_posts

async def fetch_page_content(session, url):
    try:
        # URL-encode the target URL before passing it as a parameter to the proxy
        encoded_url = quote_plus(url)
        proxy_url = f"{PROXY_API_URL}?url={encoded_url}"
        async with session.get(proxy_url) as response:
            response.raise_for_status()
            return await response.text()
    except aiohttp.ClientError as e:
        print(f"Error communicating with proxy API or fetching URL: {e}")
        return None

def parse_onejav_posts(soup):
    posts_data = []
    # Find all individual post thumbnails within the content area
    # They are inside <div class="dragscroll"> and have class 'thumbnail is-inline'
    thumbnails = soup.find_all('div', class_='thumbnail is-inline')

    for thumbnail in thumbnails:
        post = {}
        link = thumbnail.find('a', class_='thumbnail-link')
        img = thumbnail.find('img')
        text_div = thumbnail.find('div', class_='thumbnail-text')

        if link and img and text_div:
            post['title'] = text_div.get_text(strip=True)
            post['url'] = f"https://onejav.com{link['href']}" # Prepend base URL
            post['image_url'] = img['src']
            # Extract ID from URL (e.g., /torrent/PARATHD4221 -> PARATHD4221)
            match = re.search(r'/torrent/([^/]+)', link['href'])
            if match:
                post['id'] = match.group(1)
            else:
                post['id'] = 'N/A'
            
            # Extract size from title if present (e.g., PARATHD4221 (4.8 GB))
            size_match = re.search(r'\(([\d.]+)\s*(GB|MB)\)', post['title'])
            if size_match:
                post['size'] = f"{size_match.group(1)} {size_match.group(2)}"
                post['title'] = re.sub(r'\s*\([\d.]+\s*(GB|MB)\)', '', post['title']).strip() # Remove size from title
            else:
                post['size'] = 'N/A'

        else:
            continue # Skip if essential elements are missing

        posts_data.append(post)
    return posts_data


async def main():
    all_scraped_data = {}

    async with aiohttp.ClientSession() as session:
        # Scrape jav.guru
        jav_guru_posts = await scrape_jav_guru(session, num_pages_to_scrape=20)
        if jav_guru_posts:
            all_scraped_data['jav_guru'] = {
                "metadata": {
                    "source": "https://jav.guru/",
                    "last_fetched_on": datetime.now().isoformat(),
                    "total_posts": len(jav_guru_posts)
                },
                "posts": jav_guru_posts
            }
            print(f"Finished scraping jav.guru. Total posts: {len(jav_guru_posts)}")
        else:
            print("No posts fetched from jav.guru.")

        # Scrape onejav.com
        onejav_posts = await scrape_onejav(session, num_load_more_clicks=20) # Fetch ~3 weeks of data
        if onejav_posts:
            all_scraped_data['onejav_com'] = {
                "metadata": {
                    "source": "https://onejav.com/",
                    "last_fetched_on": datetime.now().isoformat(),
                    "total_posts": len(onejav_posts)
                },
                "posts": onejav_posts
            }
            print(f"Finished scraping onejav.com. Total posts: {len(onejav_posts)}")
        else:
            print("No posts fetched from onejav.com.")

    output_filename = "all_scraped_data.json"
    if all_scraped_data:
        try:
            with open(output_filename, 'w', encoding='utf-8') as f:
                json.dump(all_scraped_data, f, ensure_ascii=False, indent=4)
            print(f"\nAll scraped data saved to {output_filename}")
        except IOError as e:
            print(f"Error saving all scraped data to JSON file: {e}")
    else:
        print("No data was fetched from any source.")

if __name__ == "__main__":
    asyncio.run(main())
