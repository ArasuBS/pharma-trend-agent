#!/usr/bin/env python3
"""
Pharma Trend Digest Agent

Pulls ADC + broad drug-discovery/CDMO/manufacturing news from RSS feeds
(pharma news + journals), PubMed, and manually-submitted LinkedIn posts.
Synthesizes it all into a weekly digest using Claude, writes it to
digests/digest-<date>.md, commits it to the repo.

Run manually:  python pharma_trend_agent.py
Run on schedule: see .github/workflows/weekly-digest.yml
"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests
import yaml
import anthropic

ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "sources.yaml"
LINKEDIN_PATH = ROOT / "linkedin_manual.md"
DIGEST_DIR = ROOT / "digests"


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def days_back_cutoff(days):
    return datetime.now(timezone.utc) - timedelta(days=days)


def fetch_rss_items(feeds, cutoff):
    items = []
    for name, url in feeds.items():
        try:
            parsed = feedparser.parse(url)
        except Exception as e:
            print(f"[warn] failed to parse {name}: {e}")
            continue
        if parsed.bozo and not parsed.entries:
            print(f"[warn] {name} returned no entries — feed URL may have changed")
        for entry in parsed.entries:
            published = entry.get("published_parsed") or entry.get("updated_parsed")
            if published:
                pub_dt = datetime(*published[:6], tzinfo=timezone.utc)
                if pub_dt < cutoff:
                    continue
            items.append(
                {
                    "source": name,
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "summary": entry.get("summary", ""),
                }
            )
    return items


def fetch_pubmed(query, days_back):
    cutoff = days_back_cutoff(days_back)
    date_str = cutoff.strftime("%Y/%m/%d")
    search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        "db": "pubmed",
        "term": f"{query} AND ({date_str}[PDAT] : 3000[PDAT])",
        "retmax": 30,
        "retmode": "json",
    }
    try:
        r = requests.get(search_url, params=params, timeout=20)
        r.raise_for_status()
        ids = r.json()["esearchresult"]["idlist"]
    except Exception as e:
        print(f"[warn] PubMed search failed: {e}")
        return []
    if not ids:
        return []

    summary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    params = {"db": "pubmed", "id": ",".join(ids), "retmode": "json"}
    try:
        r = requests.get(summary_url, params=params, timeout=20)
        r.raise_for_status()
        result = r.json()["result"]
    except Exception as e:
        print(f"[warn] PubMed summary fetch failed: {e}")
        return []

    items = []
    for pid in ids:
        doc = result.get(pid, {})
        if not doc:
            continue
        items.append(
            {
                "source": "PubMed",
                "title": doc.get("title", ""),
                "link": f"https://pubmed.ncbi.nlm.nih.gov/{pid}/",
                "summary": "",
            }
        )
    return items


def load_linkedin_submissions():
    if not LINKEDIN_PATH.exists():
        return ""
    text = LINKEDIN_PATH.read_text()
    # Strip the instructional comment block if nothing else was added
    lines = [l for l in text.splitlines() if not l.strip().startswith(("<!--", "-->"))]
    return "\n".join(lines).strip()


def clear_linkedin_submissions():
    LINKEDIN_PATH.write_text(
        "<!--\n"
        "Paste LinkedIn posts or links here during the week — full text, a link\n"
        "plus your own note on why it matters, whatever's fastest for you.\n"
        "The agent reads this file on its weekly run and folds it into that\n"
        "week's digest, then clears it automatically so it's ready for next week.\n"
        "-->\n"
    )


def filter_relevant(items, modality_keywords, broad_keywords):
    keywords = [k.lower() for k in modality_keywords + broad_keywords]
    filtered = []
    for item in items:
        text = f"{item['title']} {item['summary']}".lower()
        if any(k in text for k in keywords):
            filtered.append(item)
    return filtered


def build_digest_prompt(items, linkedin_text):
    items_block = "\n".join(
        f"- [{i['source']}] {i['title']} ({i['link']})" for i in items
    ) or "(no items cleared the relevance filter this week)"

    return f"""You are helping build a weekly pharma trend digest focused on \
ADC (antibody-drug conjugates) and the broader drug discovery / CDMO / \
manufacturing space.

Below is raw material collected this week: news headlines, journal \
articles, and manually submitted LinkedIn posts.

RAW ITEMS:
{items_block}

MANUALLY SUBMITTED LINKEDIN POSTS:
{linkedin_text if linkedin_text else "(none submitted this week)"}

Produce a digest in this exact structure:

## Signal Items (3-5)
The items that actually matter and why — not just what happened, but \
what it signals for the ADC / drug-discovery / CDMO space. Skip \
anything that's just noise.

## Quick Hits
One line each for everything else worth knowing but not deep-dive worthy.

## Pattern Watch
One paragraph connecting dots — is there a theme forming across \
multiple items this week (recurring player, recurring technology \
angle, recurring deal type)?

Keep it direct and specific, no generic filler language. If nothing \
this week rises to "signal" level, say so honestly rather than \
padding it out.
"""


def synthesize_digest(items, linkedin_text):
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    prompt = build_digest_prompt(items, linkedin_text)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def main():
    config = load_config()
    cutoff = days_back_cutoff(7)

    rss_items = fetch_rss_items(config["rss_feeds"], cutoff)
    pubmed_items = fetch_pubmed(config["pubmed"]["query"], config["pubmed"]["days_back"])
    all_items = rss_items + pubmed_items
    print(f"Collected {len(all_items)} raw items before filtering")

    relevant_items = filter_relevant(
        all_items, config["modality_keywords"], config["broad_keywords"]
    )
    print(f"{len(relevant_items)} items passed the relevance filter")

    linkedin_text = load_linkedin_submissions()
    digest_body = synthesize_digest(relevant_items, linkedin_text)

    DIGEST_DIR.mkdir(exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    digest_path = DIGEST_DIR / f"digest-{today}.md"
    digest_path.write_text(f"# Pharma Trend Digest — {today}\n\n{digest_body}\n")

    clear_linkedin_submissions()
    print(f"Digest written to {digest_path}")


if __name__ == "__main__":
    main()
