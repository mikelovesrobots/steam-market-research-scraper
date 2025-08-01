# SteamSpy Scraper

A Python script that scrapes game data from SteamSpy and analyzes game tags to find underserved niches.

## Features

- Downloads all game data from SteamSpy using a two-phase approach
- Uses 10 parallel requests for individual game details (with permission from SteamSpy owner)
- Caches both paginated lists and individual game details to disk for fast resumption
- Respects SteamSpy's rate limits (60 seconds for bulk requests, 10 parallel for individual games)
- Analyzes game tags to calculate statistics:
  - Games count per tag
  - Median user score (positive review percentage)
  - Mean playtime (in minutes)
  - 75th percentile playtime (in minutes)
  - Median price (in USD)
  - Median owner count (from SteamSpy ranges)
  - Median total reviews (positive + negative)
  - Median calculated owners (total reviews × 30)

## Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

Dependencies: `requests` (for sync bulk requests) and `aiohttp` (for async parallel individual requests)

2. Test API connectivity (optional):

```bash
python test_api.py
```

3. Run the scraper:

```bash
python steamspy_scraper.py
```

⚠️ **Runtime**: With ~80,000+ games and 10 parallel requests, expect about 2-3 hours for a complete scrape (much faster than the original 25+ hours!).

## How it works

### Phase 1: Collect Game IDs (Fast)

1. **Bulk Collection**: Fetches paginated data from `https://steamspy.com/api.php?request=all&page=X`
2. **Page Caching**: Each page saved as `cache/page_X.json`
3. **Rate Limiting**: 60 seconds between bulk API requests

### Phase 2: Fetch Individual Game Details (Parallel)

1. **Parallel Requests**: Fetches detailed data using 10 concurrent requests to `https://steamspy.com/api.php?request=appdetails&appid=X`
2. **Game Caching**: Each game saved as `cache/games/game_X.json`
3. **Concurrency Control**: Semaphore limits to 10 simultaneous requests (with SteamSpy owner permission)
4. **Batch Processing**: Processes games in batches of 1,000 for progress updates

### Phase 3: Analysis

1. **Tag Extraction**: Processes detailed game data to extract tags
2. **Statistics**: Calculates median values for each tag
3. **Output**: Prints tab-delimited results sorted by games count

## Output Format

```
Name	Games Count	Userscore (median)	Playtime (mean)	Playtime (75th percentile)	Price (median)	Owners (median)	Total Reviews (median)	Calculated Owners (median)
Action	15420	78.5	120	240	$19.99	50000	85	2550
Indie	12350	82.1	95	180	$14.99	25000	45	1350
...
```

## Cache Directory

The script creates a `cache/` directory structure:

- `cache/page_X.json` - Cached pages from the bulk "all" requests
- `cache/games/game_X.json` - Cached individual game details

You can safely delete the entire `cache/` directory to start fresh, or keep it to resume from where you left off. The individual game cache is especially valuable since re-fetching all games takes 25+ hours.

## Finding Underserved Niches

Look for tags with:

- **Low games count** (<1000) - not oversaturated
- **High 75th percentile playtime** (>120 minutes) - successful games are engaging
- **High mean playtime** relative to game count - consistent engagement
- **High median price** (>$10) - can charge premium pricing
- **High calculated owners vs. SteamSpy owners** - more precise ownership estimates

The **calculated owners** (reviews × 30) often provides more accurate ownership data than SteamSpy's broad ranges, especially for newer games with good review counts.

These represent potentially underserved niches in the gaming market.
