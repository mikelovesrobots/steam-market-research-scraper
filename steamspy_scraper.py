#!/usr/bin/env python3
"""
SteamSpy scraper that downloads all game data and analyzes tags.
Caches pages to disk to allow resuming if interrupted.
"""

import asyncio
import json
import statistics
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aiohttp
import requests

CACHE_DIR = Path("cache")
GAME_DETAILS_CACHE_DIR = Path("cache/games")
API_BASE_URL = "https://steamspy.com/api.php"
ALL_REQUESTS_RATE_LIMIT = 1  # 1 request per 60 seconds for 'all' requests
INDIVIDUAL_RATE_LIMIT = 1  # 1 request per second for individual game requests
MAX_CONCURRENT_REQUESTS = 10  # Maximum parallel requests for individual games


def setup_cache_directory() -> None:
    """Create cache directories if they don't exist."""
    CACHE_DIR.mkdir(exist_ok=True)
    GAME_DETAILS_CACHE_DIR.mkdir(exist_ok=True)


def get_cache_file_path(page: int) -> Path:
    """Get the cache file path for a given page."""
    return CACHE_DIR / f"page_{page}.json"


def is_page_cached(page: int) -> bool:
    """Check if a page is already cached."""
    return get_cache_file_path(page).exists()


def save_page_to_cache(page: int, data: Dict) -> None:
    """Save page data to cache."""
    cache_file = get_cache_file_path(page)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_page_from_cache(page: int) -> Dict:
    """Load page data from cache."""
    cache_file = get_cache_file_path(page)
    with open(cache_file, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_page_from_api(page: int) -> Optional[Dict]:
    """Fetch a page of data from SteamSpy API."""
    url = f"{API_BASE_URL}?request=all&page={page}"

    try:
        print(f"Fetching page {page} from API...")
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        data = response.json()

        # If the page is empty or has no games, we've reached the end
        if not data or len(data) == 0:
            return None

        return data

    except requests.RequestException as e:
        print(f"Error fetching page {page}: {e}")
        return None


def get_page_data(page: int) -> Optional[Dict]:
    """Get page data, either from cache or API."""
    if is_page_cached(page):
        print(f"Loading page {page} from cache...")
        return load_page_from_cache(page)

    data = fetch_page_from_api(page)
    if data is not None:
        save_page_to_cache(page, data)

    return data


def get_game_cache_file_path(app_id: int) -> Path:
    """Get the cache file path for a given game."""
    return GAME_DETAILS_CACHE_DIR / f"game_{app_id}.json"


def is_game_cached(app_id: int) -> bool:
    """Check if a game's details are already cached."""
    return get_game_cache_file_path(app_id).exists()


def save_game_to_cache(app_id: int, data: Dict) -> None:
    """Save game data to cache."""
    cache_file = get_game_cache_file_path(app_id)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_game_from_cache(app_id: int) -> Dict:
    """Load game data from cache."""
    cache_file = get_game_cache_file_path(app_id)
    with open(cache_file, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_game_from_api(app_id: int) -> Optional[Dict]:
    """Fetch game details from SteamSpy API."""
    url = f"{API_BASE_URL}?request=appdetails&appid={app_id}"

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        data = response.json()

        # Check if the response contains valid game data
        if not data or data.get("appid") != app_id:
            return None

        return data

    except requests.RequestException as e:
        print(f"Error fetching game {app_id}: {e}")
        return None


def get_game_data(app_id: int) -> Optional[Dict]:
    """Get game data, either from cache or API."""
    if is_game_cached(app_id):
        return load_game_from_cache(app_id)

    data = fetch_game_from_api(app_id)
    if data is not None:
        save_game_to_cache(app_id, data)

    return data


async def fetch_game_from_api_async(
    session: aiohttp.ClientSession, app_id: int, semaphore: asyncio.Semaphore
) -> Optional[Dict]:
    """Fetch game details from SteamSpy API using async/await."""
    url = f"{API_BASE_URL}?request=appdetails&appid={app_id}"

    async with semaphore:  # Limit concurrent requests
        try:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                response.raise_for_status()
                data = await response.json()

                # Check if the response contains valid game data
                if not data or data.get("appid") != app_id:
                    return None

                return data

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            print(f"Error fetching game {app_id}: {e}")
            return None


async def get_game_data_async(
    session: aiohttp.ClientSession, app_id: int, semaphore: asyncio.Semaphore
) -> Optional[Dict]:
    """Get game data async, either from cache or API."""
    if is_game_cached(app_id):
        return load_game_from_cache(app_id)

    data = await fetch_game_from_api_async(session, app_id, semaphore)
    if data is not None:
        save_game_to_cache(app_id, data)

    return data


def parse_owner_range(owner_string: str) -> Optional[int]:
    """Parse owner range string and return midpoint."""
    if not owner_string or owner_string == "":
        return None

    try:
        # Remove commas and split on ".."
        clean_string = owner_string.replace(",", "")
        if ".." in clean_string:
            start, end = clean_string.split("..")
            start_num = int(start.strip())
            end_num = int(end.strip())
            return (start_num + end_num) // 2
        else:
            # Single number
            return int(clean_string)
    except (ValueError, AttributeError):
        return None


def calculate_positive_percentage(positive: int, negative: int) -> Optional[float]:
    """Calculate positive review percentage."""
    total = positive + negative
    if total == 0:
        return None
    return (positive / total) * 100


def extract_tags_from_game(game_data: Dict) -> List[str]:
    """Extract tag names from game data."""
    tags_data = game_data.get("tags", {})
    if not isinstance(tags_data, dict):
        return []

    return list(tags_data.keys())


def scrape_all_pages() -> List[Dict]:
    """Scrape all pages from SteamSpy and return combined data."""
    setup_cache_directory()

    all_games = []
    page = 0

    while True:
        page_data = get_page_data(page)

        if page_data is None or len(page_data) == 0:
            print(f"Reached end of data at page {page}")
            break

        # Convert the page data to a list of games
        games_in_page = list(page_data.values())
        all_games.extend(games_in_page)

        print(f"Page {page}: {len(games_in_page)} games (total: {len(all_games)})")

        page += 1

        # Rate limiting: wait 60 seconds between API calls (not for cached pages)
        if not is_page_cached(page) and page_data is not None:
            print(f"Waiting {ALL_REQUESTS_RATE_LIMIT} seconds before next request...")
            time.sleep(ALL_REQUESTS_RATE_LIMIT)

    return all_games


async def fetch_detailed_game_data(game_ids: List[int]) -> List[Dict]:
    """Fetch detailed game data for all game IDs using async parallel requests."""
    total_games = len(game_ids)
    detailed_games = []

    print(
        f"Fetching detailed data for {total_games} games using {MAX_CONCURRENT_REQUESTS} parallel requests..."
    )

    # Count how many are already cached
    initially_cached = sum(1 for app_id in game_ids if is_game_cached(app_id))
    print(
        f"Found {initially_cached} games already cached, need to fetch {total_games - initially_cached} from API"
    )

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    batch_size = 1000  # Process in batches for progress updates

    async with aiohttp.ClientSession() as session:
        for batch_start in range(0, total_games, batch_size):
            batch_end = min(batch_start + batch_size, total_games)
            batch_ids = game_ids[batch_start:batch_end]

            print(f"Processing batch {batch_start + 1}-{batch_end} of {total_games}...")

            # Check cache status BEFORE processing batch
            cached_in_batch = sum(1 for app_id in batch_ids if is_game_cached(app_id))
            api_requests_in_batch = len(batch_ids) - cached_in_batch

            # Create async tasks for this batch
            tasks = [
                get_game_data_async(session, app_id, semaphore) for app_id in batch_ids
            ]

            # Execute batch and collect results
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            for app_id, result in zip(batch_ids, batch_results):
                if isinstance(result, Exception):
                    print(f"Error processing game {app_id}: {result}")
                elif result is not None:
                    detailed_games.append(result)

            print(
                f"Batch completed: {len(detailed_games)} total valid games, "
                f"{cached_in_batch} from cache in this batch, "
                f"{api_requests_in_batch} API requests in this batch"
            )

    final_cached = sum(1 for app_id in game_ids if is_game_cached(app_id))
    final_api_requests = final_cached - initially_cached

    print(
        f"Final: {len(detailed_games)} valid games, {final_cached} total cached, {final_api_requests} new API requests made"
    )
    return detailed_games


def analyze_tags(games: List[Dict]) -> Dict[str, Dict]:
    """Analyze games by tags and calculate statistics."""
    tag_stats = {}

    for game in games:
        # Extract game metrics
        positive = game.get("positive", 0) or 0
        negative = game.get("negative", 0) or 0
        userscore = calculate_positive_percentage(positive, negative)

        playtime = game.get("median_forever")
        if playtime is not None and playtime != "":
            try:
                playtime = int(playtime)
            except (ValueError, TypeError):
                playtime = None

        price = game.get("price")
        if price is not None and price != "":
            try:
                price = int(price) / 100  # Convert cents to dollars
            except (ValueError, TypeError):
                price = None

        owners = parse_owner_range(game.get("owners", ""))

        # Calculate total reviews and calculated owners
        total_reviews = positive + negative
        calculated_owners = total_reviews * 30 if total_reviews > 0 else None

        # Calculate estimated revenue (price * calculated_owners)
        estimated_revenue = None
        if price is not None and calculated_owners is not None:
            estimated_revenue = price * calculated_owners

        # Extract tags
        tags = extract_tags_from_game(game)

        for tag in tags:
            if tag not in tag_stats:
                tag_stats[tag] = {
                    "games": [],
                    "userscores": [],
                    "playtimes": [],
                    "prices": [],
                    "owners": [],
                    "total_reviews": [],
                    "calculated_owners": [],
                    "estimated_revenues": [],
                }

            tag_stats[tag]["games"].append(game.get("appid"))

            if userscore is not None:
                tag_stats[tag]["userscores"].append(userscore)

            if playtime is not None:
                tag_stats[tag]["playtimes"].append(playtime)

            if price is not None:
                tag_stats[tag]["prices"].append(price)

            if owners is not None:
                tag_stats[tag]["owners"].append(owners)

            # Always append total_reviews (could be 0)
            tag_stats[tag]["total_reviews"].append(total_reviews)

            if calculated_owners is not None:
                tag_stats[tag]["calculated_owners"].append(calculated_owners)

            if estimated_revenue is not None:
                tag_stats[tag]["estimated_revenues"].append(estimated_revenue)

    return tag_stats


def analyze_tag_pairs(games: List[Dict]) -> Dict[Tuple[str, str], Dict]:
    """Analyze games by tag pairs and calculate statistics for combinations."""
    tag_pair_stats = {}

    for game in games:
        # Extract game metrics (same as single tag analysis)
        positive = game.get("positive", 0) or 0
        negative = game.get("negative", 0) or 0
        userscore = calculate_positive_percentage(positive, negative)

        playtime = game.get("median_forever")
        if playtime is not None and playtime != "":
            try:
                playtime = int(playtime)
            except (ValueError, TypeError):
                playtime = None

        price = game.get("price")
        if price is not None and price != "":
            try:
                price = int(price) / 100  # Convert cents to dollars
            except (ValueError, TypeError):
                price = None

        owners = parse_owner_range(game.get("owners", ""))

        # Calculate total reviews and calculated owners
        total_reviews = positive + negative
        calculated_owners = total_reviews * 30 if total_reviews > 0 else None

        # Calculate estimated revenue (price * calculated_owners)
        estimated_revenue = None
        if price is not None and calculated_owners is not None:
            estimated_revenue = price * calculated_owners

        # Extract tags
        tags = extract_tags_from_game(game)

        # Generate all pairs of tags for this game
        for i in range(len(tags)):
            for j in range(i + 1, len(tags)):
                tag_a, tag_b = sorted(
                    [tags[i], tags[j]]
                )  # Sort to ensure consistent ordering
                tag_pair = (tag_a, tag_b)

                if tag_pair not in tag_pair_stats:
                    tag_pair_stats[tag_pair] = {
                        "games": [],
                        "userscores": [],
                        "playtimes": [],
                        "prices": [],
                        "owners": [],
                        "total_reviews": [],
                        "calculated_owners": [],
                        "estimated_revenues": [],
                    }

                tag_pair_stats[tag_pair]["games"].append(game.get("appid"))

                if userscore is not None:
                    tag_pair_stats[tag_pair]["userscores"].append(userscore)

                if playtime is not None:
                    tag_pair_stats[tag_pair]["playtimes"].append(playtime)

                if price is not None:
                    tag_pair_stats[tag_pair]["prices"].append(price)

                if owners is not None:
                    tag_pair_stats[tag_pair]["owners"].append(owners)

                # Always append total_reviews (could be 0)
                tag_pair_stats[tag_pair]["total_reviews"].append(total_reviews)

                if calculated_owners is not None:
                    tag_pair_stats[tag_pair]["calculated_owners"].append(
                        calculated_owners
                    )

                if estimated_revenue is not None:
                    tag_pair_stats[tag_pair]["estimated_revenues"].append(
                        estimated_revenue
                    )

    return tag_pair_stats


def calculate_tag_summary(
    tag_stats: Dict[str, Dict],
) -> List[Tuple[str, int, float, float, float, float, float, float, float, float]]:
    """Calculate summary statistics for each tag."""
    summary = []

    for tag, stats in tag_stats.items():
        games_count = len(stats["games"])

        userscore_median = (
            statistics.median(stats["userscores"]) if stats["userscores"] else 0
        )

        # Calculate mean playtime
        playtime_mean = statistics.mean(stats["playtimes"]) if stats["playtimes"] else 0

        # Calculate 75th percentile playtime (only for games with playtime > 0)
        playtimes_with_data = [pt for pt in stats["playtimes"] if pt > 0]
        if len(playtimes_with_data) >= 4:
            playtime_75th = statistics.quantiles(playtimes_with_data, n=4)[2]
        elif playtimes_with_data:
            playtime_75th = max(playtimes_with_data)  # Use max if too few data points
        else:
            playtime_75th = 0

        price_median = statistics.median(stats["prices"]) if stats["prices"] else 0
        owners_median = statistics.median(stats["owners"]) if stats["owners"] else 0

        # Calculate new metrics
        total_reviews_median = (
            statistics.median(stats["total_reviews"]) if stats["total_reviews"] else 0
        )
        calculated_owners_median = (
            statistics.median(stats["calculated_owners"])
            if stats["calculated_owners"]
            else 0
        )
        estimated_revenue_median = (
            statistics.median(stats["estimated_revenues"])
            if stats["estimated_revenues"]
            else 0
        )

        summary.append(
            (
                tag,
                games_count,
                userscore_median,
                playtime_mean,
                playtime_75th,
                price_median,
                owners_median,
                total_reviews_median,
                calculated_owners_median,
                estimated_revenue_median,
            )
        )

    return summary


def calculate_tag_pair_summary(
    tag_pair_stats: Dict[Tuple[str, str], Dict],
) -> List[Tuple[str, str, int, float, float, float, float, float, float, float, float]]:
    """Calculate summary statistics for each tag pair."""
    summary = []

    for tag_pair, stats in tag_pair_stats.items():
        # Skip pairs with fewer than 5 games to reduce noise
        if len(stats["games"]) < 5:
            continue
        tag_a, tag_b = tag_pair
        games_count = len(stats["games"])

        userscore_median = (
            statistics.median(stats["userscores"]) if stats["userscores"] else 0
        )

        # Calculate mean playtime
        playtime_mean = statistics.mean(stats["playtimes"]) if stats["playtimes"] else 0

        # Calculate 75th percentile playtime (only for games with playtime > 0)
        playtimes_with_data = [pt for pt in stats["playtimes"] if pt > 0]
        if len(playtimes_with_data) >= 4:
            playtime_75th = statistics.quantiles(playtimes_with_data, n=4)[2]
        elif playtimes_with_data:
            playtime_75th = max(playtimes_with_data)  # Use max if too few data points
        else:
            playtime_75th = 0

        price_median = statistics.median(stats["prices"]) if stats["prices"] else 0
        owners_median = statistics.median(stats["owners"]) if stats["owners"] else 0

        # Calculate new metrics
        total_reviews_median = (
            statistics.median(stats["total_reviews"]) if stats["total_reviews"] else 0
        )
        calculated_owners_median = (
            statistics.median(stats["calculated_owners"])
            if stats["calculated_owners"]
            else 0
        )
        estimated_revenue_median = (
            statistics.median(stats["estimated_revenues"])
            if stats["estimated_revenues"]
            else 0
        )

        summary.append(
            (
                tag_a,
                tag_b,
                games_count,
                userscore_median,
                playtime_mean,
                playtime_75th,
                price_median,
                owners_median,
                total_reviews_median,
                calculated_owners_median,
                estimated_revenue_median,
            )
        )

    return summary


def print_tag_analysis(
    summary: List[
        Tuple[str, int, float, float, float, float, float, float, float, float]
    ],
) -> None:
    """Print tag analysis in tab-delimited format."""
    print(
        "Name\tGames Count\tUserscore (median)\tPlaytime (mean)\tPlaytime (75th percentile)\tPrice (median)\tOwners (median)\tTotal Reviews (median)\tCalculated Owners (median)\tEstimated Revenue (median)"
    )

    # Sort by games count descending
    summary.sort(key=lambda x: x[1], reverse=True)

    for (
        tag,
        games_count,
        userscore_median,
        playtime_mean,
        playtime_75th,
        price_median,
        owners_median,
        total_reviews_median,
        calculated_owners_median,
        estimated_revenue_median,
    ) in summary:
        print(
            f"{tag}\t{games_count}\t{userscore_median:.1f}\t{playtime_mean:.0f}\t{playtime_75th:.0f}\t${price_median:.2f}\t{owners_median:.0f}\t{total_reviews_median:.0f}\t{calculated_owners_median:.0f}\t${estimated_revenue_median:,.0f}"
        )


def print_tag_pair_analysis(
    summary: List[
        Tuple[str, str, int, float, float, float, float, float, float, float, float]
    ],
) -> None:
    """Print tag pair analysis in tab-delimited format."""
    print(
        "Tag A\tTag B\tGames Count\tUserscore (median)\tPlaytime (mean)\tPlaytime (75th percentile)\tPrice (median)\tOwners (median)\tTotal Reviews (median)\tCalculated Owners (median)\tEstimated Revenue (median)"
    )

    # Sort by games count descending
    summary.sort(key=lambda x: x[2], reverse=True)

    for (
        tag_a,
        tag_b,
        games_count,
        userscore_median,
        playtime_mean,
        playtime_75th,
        price_median,
        owners_median,
        total_reviews_median,
        calculated_owners_median,
        estimated_revenue_median,
    ) in summary:
        print(
            f"{tag_a}\t{tag_b}\t{games_count}\t{userscore_median:.1f}\t{playtime_mean:.0f}\t{playtime_75th:.0f}\t${price_median:.2f}\t{owners_median:.0f}\t{total_reviews_median:.0f}\t{calculated_owners_median:.0f}\t${estimated_revenue_median:,.0f}"
        )


def main() -> None:
    """Main function to run the scraper and analysis."""
    print("Starting SteamSpy scraper...")

    # Phase 1: Scrape all game IDs from paginated 'all' requests
    print("Phase 1: Collecting all game IDs...")
    basic_games = scrape_all_pages()
    game_ids = [game.get("appid") for game in basic_games if game.get("appid")]
    print(f"Total game IDs collected: {len(game_ids)}")

    # Phase 2: Fetch detailed data for each game (including tags)
    print("\nPhase 2: Fetching detailed game data...")
    detailed_games = asyncio.run(fetch_detailed_game_data(game_ids))
    print(f"Total detailed games fetched: {len(detailed_games)}")

    # Phase 3: Analyze tags
    print("\nPhase 3: Analyzing tags...")
    tag_stats = analyze_tags(detailed_games)

    # Calculate summary
    summary = calculate_tag_summary(tag_stats)

    # Print results
    print(f"\nFound {len(summary)} unique tags")
    print("\nTag Analysis Results:")
    print_tag_analysis(summary)

    # Phase 4: Analyze tag pairs
    print("\nPhase 4: Analyzing tag pairs...")
    tag_pair_stats = analyze_tag_pairs(detailed_games)

    # Calculate tag pair summary
    pair_summary = calculate_tag_pair_summary(tag_pair_stats)

    # Print tag pair results
    print(f"\nFound {len(pair_summary)} unique tag pairs")
    print("\nTag Pair Analysis Results:")
    print_tag_pair_analysis(pair_summary)


if __name__ == "__main__":
    main()
