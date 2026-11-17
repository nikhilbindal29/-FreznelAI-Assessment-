# Lexaloffle BBS – first 100 games scraper

This project collects up to the first 100 cartridge/game entries from the Lexaloffle BBS
PICO-8 cartridges page and writes `data/games.csv`.

## Fields
- game_name
- author_name
- game_artwork
- game_code
- license
- like_count
- game_description
- top_5_comments

`top_5_comments` is stored as a JSON-encoded array inside the CSV cell. `game_artwork`
contains the artwork URL (not a downloaded image). `game_code` is the cartridge/code
identifier when exposed by the BBS page; it is not the game's source code.

## Run (Python 3.10+)
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
python scraper.py
```

The target page is configured in `scraper.py`. The script follows the site's pagination,
visits each game's thread, extracts metadata/comments where available, and stops at 100.
Missing fields are left blank rather than guessed. Respect the site's terms and avoid
aggressive request rates.

## Important
The execution environment used to prepare this ZIP could not make direct HTTP requests to
Lexaloffle, so a verified 100-record live scrape could not be produced here. The included
CSV is a correctly structured header/template; run the scraper from a machine with internet
access to populate it with live records. The scraper prints progress and reports the final
row count.
