document.addEventListener('DOMContentLoaded', () => {
    const postsContainer = document.getElementById('posts-container');
    const searchInput = document.getElementById('search-input');
    let allPosts = [];

    // Function to fetch posts data
    async function fetchPosts() {
        try {
            const response = await fetch('./missav_posts.json');
            const data = await response.json();
            allPosts = data.posts;
            displayPosts(allPosts);

            // Update metadata info
            document.getElementById('total-posts').textContent = data.metadata.total_posts;
            document.getElementById('pages-fetched').textContent = data.metadata.pages_fetched;
        } catch (error) {
            console.error('Error fetching posts:', error);
            postsContainer.innerHTML = '<p>Error loading posts. Please ensure missav_posts.json exists and is accessible.</p>';
            document.getElementById('total-posts').textContent = 'N/A';
            document.getElementById('pages-fetched').textContent = 'N/A';
        }
    }

    // Function to display posts
    function displayPosts(posts) {
        postsContainer.innerHTML = ''; // Clear existing posts
        if (posts.length === 0) {
            postsContainer.innerHTML = '<p>No posts found.</p>';
            return;
        }

        posts.forEach(post => {
            const postCard = document.createElement('div');
            postCard.classList.add('post-card');

            const uncensoredTag = post.uncensored ? `<span class="uncensored">Uncensored</span>` : '';

            postCard.innerHTML = `
                <a href="${post.link}" target="_blank">
                    <div class="thumbnail-container">
                        <img src="${post.cover_image}" alt="${post.title}" loading="lazy">
                        <video src="${post.preview_video}" loop muted playsinline preload="none"></video>
                    </div>
                    <div class="info">
                        <h2>${post.title}</h2>
                        <p>Duration: ${post.duration}</p>
                    </div>
                    <span class="duration">${post.duration}</span>
                    ${uncensoredTag}
                </a>
            `;
            postsContainer.appendChild(postCard);
        });

        // Add hover effects for video previews
        addVideoHoverEffects();
    }

    // Function to add video hover effects
    function addVideoHoverEffects() {
        document.querySelectorAll('.post-card').forEach(card => {
            const video = card.querySelector('video');
            if (video) {
                card.addEventListener('mouseenter', () => {
                    video.play().catch(error => console.error("Error playing video:", error));
                });
                card.addEventListener('mouseleave', () => {
                    video.pause();
                    video.currentTime = 0; // Reset video to start
                });
            }
        });
    }

    // Search functionality
    searchInput.addEventListener('input', (event) => {
        const searchTerm = event.target.value.toLowerCase();
        const filteredPosts = allPosts.filter(post =>
            post.title.toLowerCase().includes(searchTerm)
        );
        displayPosts(filteredPosts);
    });

    // Initial fetch of posts
    fetchPosts();
});
