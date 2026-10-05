#!/usr/bin/env python3
"""Fetch @glorysdj tweets from Nitter RSS.

Uses the Nitter RSS feed (no Twitter account needed). Tries multiple Nitter
instances with fallback. Writes tweets.json in the shape the frontend
(index.html) expects.
"""
import html
import json
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

SCREEN_NAME = os.environ.get("TWEET_SCREEN_NAME", "glorysdj")
MAX_TWEETS = int(os.environ.get("TWEET_MAX", "20"))
TIMEOUT = 25
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) tweets-fetcher/1.0"}

# Nitter instances, tried in order. RSS works on kareem.one.
INSTANCES = [
    "nitter.kareem.one",
    "nitter.tiekoetter.com",
    "nitter.net",
    "xcancel.com",
    "nitter.poast.org",
    "nitter.space",
    "lightbrd.com",
    "nitter.moomoo.me",
    "nitter.privacydev.net",
    "nitter.luiker.org",
    "nitter.holo-mix.com",
    "nitter.qwik.space",
]


def http_get(url: str) -> bytes:
    req = Request(url, headers=UA)
    with urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


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
    for instance in INSTANCES:
        try:
            tweets = fetch_via_rss(instance)
            if tweets:
                write_json(tweets, f"nitter-rss:{instance}")
                print(f"OK: fetched {len(tweets)} tweets from {instance}")
                return 0
            print(f"WARN: {instance} RSS empty, trying next", file=sys.stderr)
        except (URLError, TimeoutError, OSError, ET.ParseError) as e:
            print(f"WARN: {instance} RSS failed ({e}), trying next", file=sys.stderr)

    print("ERROR: all Nitter instances failed (RSS).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
