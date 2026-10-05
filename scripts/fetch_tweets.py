#!/usr/bin/env python3
"""Fetch @glorysdj's latest tweets via twscrape and write tweets.json.

Requires env vars:
  TWITTER_USERNAME, TWITTER_PASSWORD  (a Twitter account, ideally without 2FA)
  TWITTER_EMAIL, TWITTER_EMAIL_PASSWORD (optional, for 2FA recovery)
  TWEET_SCREEN_NAME (default: glorysdj)
  TWEET_LIMIT (default: 100)
  OUT_FILE (default: tweets.json)
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

import twscrape as tw

SCREEN_NAME = os.environ.get("TWEET_SCREEN_NAME", "glorysdj")
LIMIT = int(os.environ.get("TWEET_LIMIT", "100"))
OUT = os.environ.get("OUT_FILE", "tweets.json")


def _utc_iso(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


async def main():
    username = os.environ.get("TWITTER_USERNAME", "")
    password = os.environ.get("TWITTER_PASSWORD", "")
    if not username or not password:
        print("TWITTER_USERNAME / TWITTER_PASSWORD not set", file=sys.stderr)
        sys.exit(2)

    api = tw.API()
    await api.pool.add_account(
        username=username,
        password=password,
        email=os.environ.get("TWITTER_EMAIL", ""),
        email_password=os.environ.get("TWITTER_EMAIL_PASSWORD", ""),
    )
    result = await api.pool.login_all()
    if result.get("success", 0) == 0:
        print(
            "Login failed. Check credentials; the account must NOT have 2FA enabled "
            "for unattended runs.",
            file=sys.stderr,
        )
        sys.exit(1)

    user = await api.user_by_login(SCREEN_NAME)
    if user is None:
        print(f"User @{SCREEN_NAME} not found", file=sys.stderr)
        sys.exit(1)

    tweets = []
    async for tweet in api.user_tweets(user.id, limit=LIMIT):
        tweets.append(
            {
                "id": str(tweet.id),
                "date": _utc_iso(tweet.date),
                "text": tweet.rawContent,
                "url": tweet.url or f"https://twitter.com/{SCREEN_NAME}/status/{tweet.id}",
                "retweets": tweet.retweetCount,
                "likes": tweet.likeCount,
                "views": tweet.viewCount,
            }
        )

    data = {
        "screen_name": SCREEN_NAME,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(tweets),
        "tweets": tweets,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(tweets)} tweets to {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
