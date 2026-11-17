#!/usr/bin/env python3
"""
Lexaloffle BBS cartridge scraper.
Outputs the first 100 games visible in the configured cartridge listing.
"""
from __future__ import annotations

import csv
import json
import re
import time
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

BASE = "https://www.lexaloffle.com"
LISTING_URL = BASE + "/bbs/?cat=7&carts_tab=1&sub=2&mode=carts"
TARGET = 100
OUT = "data/games.csv"
DELAY_SECONDS = 0.8

FIELDS = [
    "game_name", "author_name", "game_artwork", "game_code",
    "license", "like_count", "game_description", "top_5_comments"
]

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; EducationalBBSResearch/1.0)"
})

def clean(node):
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)) if node else ""

def absolute(href):
    return urljoin(BASE, href) if href else ""

def parse_listing(html):
    soup = BeautifulSoup(html, "html.parser")
    found = []
    seen = set()

    # Cart entries link to a BBS post via pid; ignore navigation/profile links.
    for a in soup.select('a[href*="pid="], a[href*="tid="]'):
        href = absolute(a.get("href"))
        qs = parse_qs(urlparse(href).query)
        pid = (qs.get("pid") or [None])[0]
        tid = (qs.get("tid") or [None])[0]
        key = pid or tid or href
        if not key or key in seen:
            continue

        # Use the nearest card-like ancestor to obtain author/title/artwork.
        card = a
        for _ in range(5):
            if card.parent and card.parent.name not in ("body", "html"):
                card = card.parent
            if card.find("img") or len(clean(card)) > 20:
                break

        title = clean(a)
        if not title:
            title = clean(card.select_one("h1,h2,h3,.title,.post_title"))
        if not title:
            continue

        img = card.find("img")
        artwork = absolute(img.get("src") or img.get("data-src")) if img else ""
        text = clean(card)
        author = ""
        m = re.search(r"\bby\s+([A-Za-z0-9_ .'-]+)", text, re.I)
        if m:
            author = m.group(1).strip()

        # Like counts commonly appear as compact numeric labels in the listing.
        like_count = ""
        nums = re.findall(r"\b\d+\b", text)
        if nums:
            like_count = nums[-1]

        seen.add(key)
        found.append({
            "game_name": title,
            "author_name": author,
            "game_artwork": artwork,
            "game_code": str(pid or tid or ""),
            "license": "",
            "like_count": like_count,
            "game_description": "",
            "top_5_comments": "[]",
            "detail_url": href,
        })
    return found

def parse_detail(game):
    url = game.get("detail_url", "")
    if not url:
        return game
    try:
        response = session.get(url, timeout=25)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        # Prefer the main post/thread content, with sensible fallbacks.
        main = soup.select_one("#post, .post, .thread, #content") or soup
        text = clean(main)

        # Description: remove obvious UI fragments by using the first substantial paragraph.
        paragraphs = [clean(p) for p in main.select("p") if len(clean(p)) > 25]
        if paragraphs:
            game["game_description"] = paragraphs[0]

        # Artwork can be on the detail page even when absent in listing.
        if not game["game_artwork"]:
            img = main.find("img")
            if img:
                game["game_artwork"] = absolute(img.get("src") or img.get("data-src"))

        # License label, e.g. CC4-BY-NC-SA.
        lic = re.search(r"(?:License\s*:\s*)?(CC4-[A-Z-]+|CC-BY-[A-Z-]+)", text, re.I)
        if lic:
            game["license"] = lic.group(1)

        # Extract comment-like blocks, excluding the original post when possible.
        candidates = []
        selectors = [
            ".comment", ".reply", ".post_reply", ".bbs_post",
            "[id^='post_']", "[class*='reply']"
        ]
        for selector in selectors:
            for node in soup.select(selector):
                value = clean(node)
                if len(value) >= 8 and value not in candidates:
                    candidates.append(value)
        # Avoid treating the full page or duplicate nested containers as comments.
        comments = []
        for value in candidates:
            if not any(value in existing for existing in comments):
                comments.append(value)
        game["top_5_comments"] = json.dumps(comments[:5], ensure_ascii=False)

        # The cart PID is the BBS game identifier; retain it in game_code.
        return game
    except requests.RequestException as exc:
        print(f"[WARN] Detail fetch failed for {url}: {exc}")
        return game

def get_next_page_url(soup, current_url):
    # Follow a visible "next" / pagination link if available.
    for a in soup.find_all("a", href=True):
        label = clean(a).lower()
        rel = " ".join(a.get("rel", [])).lower()
        if label in {"next", ">", "»", "›"} or "next" in rel:
            return absolute(a["href"])
    return ""

def scrape():
    games, seen = [], set()
    page_url = LISTING_URL

    while page_url and len(games) < TARGET:
        print(f"[LIST] {page_url}")
        response = session.get(page_url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        page_games = parse_listing(response.text)
        for item in page_games:
            key = item["game_code"] or item.get("detail_url")
            if key in seen:
                continue
            seen.add(key)
            games.append(item)
            if len(games) >= TARGET:
                break

        next_url = get_next_page_url(soup, page_url)
        # If the site uses numbered pages without a next link, stop safely.
        if not next_url or next_url == page_url or not page_games:
            break
        page_url = next_url
        time.sleep(DELAY_SECONDS)

    if not games:
        raise RuntimeError(
            "No game entries were parsed. The site markup may have changed; "
            "inspect the listing HTML and update parse_listing()."
        )

    enriched = []
    for index, game in enumerate(games[:TARGET], start=1):
        print(f"[DETAIL] {index}/{min(len(games), TARGET)} {game['game_name']}")
        enriched.append(parse_detail(game))
        time.sleep(DELAY_SECONDS)

    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(enriched)

    print(f"\nSaved {len(enriched)} records to {OUT}")
    if len(enriched) < TARGET:
        print(f"[NOTE] Only {len(enriched)} entries were found; check pagination/markup.")

if __name__ == "__main__":
    scrape()
