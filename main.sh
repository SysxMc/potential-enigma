#!/bin/bash

sources_file="sources.txt"
links_file="links.txt"
temp_dir="tmp_crwl_logs"

# Clean up from previous runs
mkdir -p "$temp_dir"
> "$sources_file"
> "$links_file"

echo "Step 1: Collecting watch list URLs from pages 1 to 70..."

for page in {1..70}; do
    url="https://missav.ws/en/playlists/dprelff6?page=$page"
    echo "Processing page $page..."
    crwl "$url" -o md-fit | \
    awk '/Playlist: Spidys Watch List/,/Back to top/' | \
    grep -oP 'https://missav\.ws/[^\s)"]+' >> "$sources_file"
done

# Remove duplicates
sort -u "$sources_file" -o "$sources_file"
echo "Collected $(wc -l < "$sources_file") unique watch list URLs."

echo "Step 2: Extracting surrit.com links from each video page..."

# Function to process each URL
extract_links() {
    url="$1"
    crwl "$url" | grep -oP '"(https://surrit\.com[^"]+)"' | tr -d '"' || true
}

export -f extract_links

# Use pv for progress bar if available
if command -v pv >/dev/null; then
    cat "$sources_file" | pv -l -s $(wc -l < "$sources_file") | \
    parallel --halt soon,fail=1 -j 10 extract_links {} >> "$links_file"
else
    cat "$sources_file" | \
    parallel --halt soon,fail=1 -j 10 extract_links {} >> "$links_file"
fi

# Remove duplicates in final output
sort -u "$links_file" -o "$links_file"

echo "Done! Collected $(wc -l < "$links_file") unique surrit.com links."
