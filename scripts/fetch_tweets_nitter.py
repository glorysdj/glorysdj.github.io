#!/usr/bin/env python3
"""Fetch @glorysdj tweets from Nitter, with timeline pagination.

Primary: scrape the Nitter HTML timeline and follow the ?cursor= "show more"
links to collect up to MAX_TWEETS.
Fallback: if HTML parsing yields nothing, use the RSS feed (~20 tweets).

No Twitter account needed. Tries multiple Nitter instances with fallback.
Writes tweets.json in the same shape the frontend (index.html) expects.
"""
import html
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import URLError

SCREEN_NAME = os.environ.get("TWEET_SCREEN_NAME", "glorysdj")
MAX_TWEETS = int(os.environ.get("TWEET_MAX", "100"))
TIMEOUT = 25
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) tweets-fetcher/1.0"}

# Nitter instances, tried in order.
INSTANCES = [
    "nitter.kareem.one",   # known-good from last run
    "nitter.net",
    "xcancel.com",
    "nitter.poast.org",
    "nitter.tiekoetter.com",
    "nitter.space",
    "lightbrd.com",
    "nitter.moomoo.me",
    "nitter.privacydev.net",
    "nitter.luiker.org",
    "nitter.holo-mix.com",
    "nitter.qwik.space",
]

# --- HTML timeline parsing -------------------------------------------------

RE_TWEET_BLOCK = re.compile(r'<div class="timeline-item[^"]*">(.*?)(?=<div class="timeline-item|<a class="show-more|</div>\s*</div>\s*</div>)', re.S)
RE_TEXT = re.compile(r'<div class="tweet-content media-body"[^>]*>(.*?)</div>', re.S)
RE_STATUS_HREF = re.compile(r'href="(/[^/]+/status/\d+[^"]*)"', re.S)
RE_DATE = re.compile(r'<time datetime="([^"]+)"', re.S)
RE_RETWEET = re.compile(r'icon-container retweet.*?tweet-stat-count">(\d+)</span>', re.S)
RE_LIKE = re.compile(r'icon-container like.*?tweet-stat-count">(\d+)</span>', re.S)
RE_CURSOR = re.compile(r'class="show-more"[^>]*href="[^"]*\?cursor=([^"&]+)"', re.S)
RE_CURSOR_ALT = re.compile(r'\?cursor=([A-Za-z0-9]+)', re.S)


def http_get(url: str) -> bytes:
    req = Request(url, headers=UA)
    with urlopen(req, timeout=TIMEOUT) as resp:
        print(f"DEBUG: GET {url} -> HTTP {resp.status}")
        return resp.read()


def clean_text(raw: str) -> str:
    # strip inner tags (links, line breaks) then unescape entities
    raw = re.sub(r'<br\s*/?>', '\n', raw)
    raw = re.sub(r'<[^>]+>', '', raw)
    return html.unescape(raw).strip()


def parse_timeline_page(page: str, instance: str):
    """Return (tweets, next_cursor) for one timeline page."""
    tweets = []
    blocks = RE_TWEET_BLOCK.findall(page)
    if not blocks:
        blocks = re.split(r'(?=<div class="tweet-content media-body")', page)
    for block in blocks:
        m_text = RE_TEXT.search(block)
        if not m_text:
            continue
        text = clean_text(m_text.group(1))
        m_href = RE_STATUS_HREF.search(block)
        href = m_href.group(1) if m_href else ""
        url = f"https://{instance}{href}" if href.startswith("/") else href
        if url:
            url = url.replace(f"https://{instance}", "https://x.com", 1)
        m_date = RE_DATE.search(block)
        date_iso = m_date.group(1) if m_date else ""
        m_rt = RE_RETWEET.search(block)
        m_like = RE_LIKE.search(block)
        tweets.append({
            "id": href.rsplit("/", 1)[-1].split("#")[0] if href else "",
            "date": date_iso,
            "text": text,
            "url": url,
            "retweets": int(m_rt.group(1)) if m_rt else None,
            "likes": int(m_like.group(1)) if m_like else None,
            "views": None,
        })
    m_cur = RE_CURSOR.search(page) or RE_CURSOR_ALT.search(page)
    next_cursor = m_cur.group(1) if m_cur else None
    return tweets, next_cursor


def fetch_via_html(instance: str):
    """Follow the timeline cursor until MAX_TWEETS or no more pages.
    Saves the first page (that parsed 0 tweets) to debug_nitter_first.html for debugging."""
    collected = []
    seen = set()
    cursor = None
    first_page = True
    for _page in range(0, 40):  # hard cap on pages
        url = f"https://{instance}/{SCREEN_NAME}"
        if cursor:
            url += f"?cursor={quote(cursor)}"
        page = http_get(url).decode("utf-8", "replace")
        tweets, cursor = parse_timeline_page(page, instance)
        if first_page and not tweets:
            # Save the page that returned 200 but parsed 0 tweets — unique file per instance
            try:
                fname = f"debug_{instance.replace('.', '_')}.html"
                with open(fname, "w", encoding="utf-8") as f:
                    f.write(page)
                print(f"DEBUG: saved {fname} ({len(page)} chars) — 0 tweets parsed")
            except Exception as e:
                print(f"DEBUG: failed to save HTML: {e}")
        first_page = False
        for t in tweets:
            key = t["id"] or t["url"] or t["text"][:64]
            if key in seen:
                continue
            seen.add(key)
            collected.append(t)
        if not cursor or len(collected) >= MAX_TWEETS:
            break
    return collected[:MAX_TWEETS]


# --- RSS fallback ----------------------------------------------------------

def fetch_via_rss(instance: str):
    url = f"https://{instance}/{SCREEN_NAME}/rss"
    data = http_get(url)
    root = ET.fromstring(data)
    tweets = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        if link:
            link = link.replace(f"https://{instance}", "https://x.com", 1)
        date_iso = ""
        if pub:
            try:
                date_iso = parsedate_to_datetime(pub).astimezone(timezone.utc).isoformat()
            except Exception:
                date_iso = pub
        if not title and not link:
            continue
        tweets.append({
            "id": link.rsplit("/", 1)[-1] if link else "",
            "date": date_iso,
            "text": title,
            "url": link,
            "retweets": None,
            "likes": None,
            "views": None,
        })
        if len(tweets) >= MAX_TWEETS:
            break
    return tweets


def write_json(tweets, source):
    out = {
        "screen_name": SCREEN_NAME,
        "source": source,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(tweets),
        "tweets": tweets,
    }
    with open("tweets.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


def main():
    # 1) Try HTML pagination on each instance until we get enough tweets.
    for instance in INSTANCES:
        try:
            tweets = fetch_via_html(instance)
            if tweets:
                write_json(tweets, f"nitter-html:{instance}")
                print(f"OK: fetched {len(tweets)} tweets via HTML from {instance}")
                return 0
            print(f"WARN: {instance} HTML returned no tweets, trying next", file=sys.stderr)
        except (URLError, TimeoutError, OSError, ET.ParseError) as e:
            print(f"WARN: {instance} HTML failed ({e}), trying next", file=sys.stderr)

    # 2) Fallback: RSS (fewer tweets, but more robust).
    for instance in INSTANCES:
        try:
            tweets = fetch_via_rss(instance)
            if tweets:
                write_json(tweets, f"nitter-rss:{instance}")
                print(f"OK (RSS fallback): fetched {len(tweets)} tweets from {instance}")
                return 0
            print(f"WARN: {instance} RSS empty, trying next", file=sys.stderr)
        except (URLError, TimeoutError, OSError, ET.ParseError) as e:
            print(f"WARN: {instance} RSS failed ({e}), trying next", file=sys.stderr)

    print("ERROR: all Nitter instances failed (HTML and RSS).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
