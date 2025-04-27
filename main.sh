#!/bin/bash

sources_file="sources.txt"
output_file="final_links.csv"
failed_file="failed.txt"
temp_dir="tmp_crwl_logs"

# Clean up from previous runs
mkdir -p "$temp_dir"
> "$sources_file"
> "$output_file"
> "$failed_file"

echo "Step 1: Collecting watch list URLs from pages 1 to 70..."

for page in {1..90}; do
    url="https://missav.ws/en/playlists/dprelff6?page=$page"
    echo "Processing page $page..."
    crwl "$url" -o md-fit | \
    awk '/Playlist: Spidys Watch List/,/Back to top/' | \
    grep -oP 'https://missav\.ws/[^\s)"]+' >> "$sources_file"
done

# Remove duplicates
sort -u "$sources_file" -o "$sources_file"

echo "Collected $(wc -l < "$sources_file") unique watch list URLs."

echo "Step 2: Extracting surrit.com links from each video page and saving as CSV..."

# Function to process each URL
extract_links() {
    url="$1"
    link=$(crwl "$url" | grep -oP '"(https://surrit\.com[^"]+)"' | tr -d '"' | sed -n '2p' || true)
    if [ -n "$link" ]; then
        echo "$url,$link"
    else
        echo "$url" >> "$failed_file"
    fi
}

export -f extract_links
export failed_file

# Write header to CSV
echo "source_url,link_url" > "$output_file"

# Use pv for progress bar if available
if command -v pv >/dev/null; then
    cat "$sources_file" | pv -l -s $(wc -l < "$sources_file") | \
    parallel --halt soon,fail=1 -j 10 extract_links {} >> "$output_file"
else
    cat "$sources_file" | \
    parallel --halt soon,fail=1 -j 10 extract_links {} >> "$output_file"
fi

# Remove duplicates
sort -u "$output_file" -o "$output_file"
sort -u "$failed_file" -o "$failed_file"

echo "Done!"
echo "Collected $(($(wc -l < "$output_file") - 1)) unique source-link pairs."
echo "Failed to extract from $(wc -l < "$failed_file") URLs. See $failed_file."
