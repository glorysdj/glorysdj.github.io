#!/usr/bin/env python3
"""Fetch @glorysdj tweets from a Nitter instance RSS feed.

No Twitter account needed. Tries multiple Nitter instances with fallback.
Writes tweets.json in the same shape as the twscrape script so the
frontend (index.html) works unchanged.
"""
import json
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.request import Request, urlopen
from urllib.error import URLError

SCREEN_NAME = os.environ.get("TWEET_SCREEN_NAME", "glorysdj")

# Nitter instances, tried in order. First one that returns a valid RSS wins.
INSTANCES = [
    "nitter.net",
    "xcancel.com",
    "nitter.poast.org",
    "nitter.tiekoetter.com",
    "nitter.space",
    "lightbrd.com",
    "nitter.kareem.one",
    "nitter.moomoo.me",
    "nitter.privacydev.net",
    "nitter.luiker.org",
    "nitter.holo-mix.com",
    "nitter.qwik.space",
]

MAX_TWEETS = int(os.environ.get("TWEET_MAX", "200"))
TIMEOUT = 20


def fetch_rss(instance: str) -> bytes:
    url = f"https://{instance}/{SCREEN_NAME}/rss"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (tweets-fetcher)"})
    with urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def parse_rss(data: bytes, instance: str):
    root = ET.fromstring(data)
    tweets = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        # Normalize the link to the canonical x.com URL
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


def main():
    last_err = None
    for instance in INSTANCES:
        try:
            data = fetch_rss(instance)
            tweets = parse_rss(data, instance)
            if tweets:
                out = {
                    "screen_name": SCREEN_NAME,
                    "source": f"nitter:{instance}",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "count": len(tweets),
                    "tweets": tweets,
                }
                with open("tweets.json", "w", encoding="utf-8") as f:
                    json.dump(out, f, ensure_ascii=False, indent=2)
                print(f"OK: fetched {len(tweets)} tweets from {instance}")
                return 0
            last_err = f"{instance}: empty RSS"
            print(f"WARN: {instance} returned empty RSS, trying next", file=sys.stderr)
        except (URLError, ET.ParseError, TimeoutError, OSError) as e:
            last_err = f"{instance}: {e}"
            print(f"WARN: {instance} failed ({e}), trying next", file=sys.stderr)
    print(f"ERROR: all Nitter instances failed. Last: {last_err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
