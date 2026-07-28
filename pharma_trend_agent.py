#!/usr/bin/env python3
"""
Pharma Trend Digest Agent — multi-topic version

Tracks whatever topics are defined in sources.yaml. Each topic gets its
own section in the output digest. Sources per topic: a shared pool of
RSS items (pharma news + journals), PubMed, targeted web search, and
manually-submitted LinkedIn posts.

TO SWITCH WHAT YOU'RE TRACKING: edit the `topics` list in sources.yaml.
No code changes needed for keyword-based topics. Open-ended topics (no
fixed vocabulary, e.g. "new trends in drug discovery") use a
`search_prompt` instead of `keywords` and rely entirely on web search.

Every factual claim in the output is required to carry a source link —
this is enforced in the synthesis prompts below, not just requested.

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


def fetch_rss_pool(feeds, cutoff):
    """Pull the shared pool of RSS items once — filtered per topic later.

    NOTE: RSS feeds only ever expose their most recent items, typically
    the last few weeks, regardless of the cutoff passed in here. See the
    long note in sources.yaml for why.
    """
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
    """Real date-range search — this genuinely reaches back `days_back` days."""
    cutoff = days_back_cutoff(days_back)
    date_str = cutoff.strftime("%Y/%m/%d")
    search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        "db": "pubmed",
        "term": f"{query} AND ({date_str}[PDAT] : 3000[PDAT])",
        "retmax": 20,
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
    lines = [
        l for l in text.splitlines()
        if not l.strip().startswith(("<!--", "-->"))
    ]
    return "\n".join(lines).strip()


def clear_linkedin_submissions():
    LINKEDIN_PATH.write_text(
        "<!--\n"
        "Paste LinkedIn posts or links here this month — full text, a link,\n"
        "plus your own note on why it matters and which topic it belongs to.\n"
        "The agent reads this file on its monthly run and folds relevant\n"
        "posts into that topic's section, then clears it automatically so\n"
        "it's ready for next month.\n"
        "-->\n"
    )


def filter_for_topic(rss_items, pubmed_items, keywords):
    keywords_lower = [k.lower() for k in keywords]
    all_items = rss_items + pubmed_items
    return [
        item
        for item in all_items
        if any(
            k in f"{item['title']} {item['summary']}".lower()
            for k in keywords_lower
        )
    ]


def research_topic(topic_name, keywords=None, search_prompt=None):
    """Targeted web search for one topic. Fills the gap RSS/PubMed can't
    reach, and is the ONLY source for open-ended topics with no fixed
    keyword vocabulary to filter on.

    Every finding is required to carry a source URL — the prompt below
    enforces this, and instructs the model to drop any finding it can't
    attach a real link to, rather than include it unsourced.
    """
    client = anthropic.Anthropic()

    if search_prompt:
        instructions = search_prompt.strip()
    else:
        kw_text = ", ".join(keywords)
        instructions = (
            f"Search the web for significant recent developments (last "
            f"30-60 days) related to: {kw_text}. Look for things like new "
            f"deals or partnerships, funding rounds, FDA approvals or "
            f"trial results, capacity expansions, and notable technical "
            f"or scientific advances. Focus on findings that aren't just "
            f"the obvious mainstream trade press headlines — dig a bit "
            f"for the less obvious signal."
        )

    prompt = f"""{instructions}

Do 4-6 targeted searches covering different angles — don't just repeat \
the same query.

For EVERY finding, you MUST include the source URL. Return a bullet \
list in this exact format:

- [Finding in 1-2 sentences] (Source: <url>)

If you can't find a real URL for something, do not include that \
finding at all — no source link means it does not go in the list. This \
is a hard requirement, not a suggestion."""

    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=1500,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def build_topic_section_prompt(topic_name, items, web_research_text, linkedin_text):
    items_block = "\n".join(
        f"- [{i['source']}] {i['title']} ({i['link']})" for i in items
    ) or "(no RSS/PubMed items matched this topic this period)"

    return f"""You are writing ONE section of a monthly pharma trend \
digest. This section covers: {topic_name}.

RSS/PUBMED ITEMS matching this topic (each already has a source link):
{items_block}

WEB RESEARCH for this topic (each finding includes its source link):
{web_research_text if web_research_text else "(no web research available for this topic)"}

LINKEDIN POSTS submitted this period (only use if actually relevant to {topic_name}):
{linkedin_text if linkedin_text else "(none submitted this period)"}

Write this section in the following structure. EVERY factual claim — \
every number, deal size, trial result, approval, or named development — \
must carry its source link directly next to it, in the format (Source: \
<url>). Never state a specific fact without the link right there; if \
you don't have a link for something, don't include that claim.

### Signal Items
2-4 items that actually matter for {topic_name} and why — not just \
what happened, but what it signals. Skip anything that's just noise.

### Quick Hits
One line each for everything else worth knowing.

If nothing this period rises to "signal" level for this topic, say so \
honestly rather than padding it out — a thin or partly-empty section \
is a valid and informative outcome, not a failure.
"""


def synthesize_topic_section(topic_name, items, web_research_text, linkedin_text):
    client = anthropic.Anthropic()
    prompt = build_topic_section_prompt(topic_name, items, web_research_text, linkedin_text)
    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def main():
    config = load_config()
    lookback_days = config.get("lookback_days", 365)
    cutoff = days_back_cutoff(lookback_days)

    rss_pool = fetch_rss_pool(config["rss_feeds"], cutoff)
    print(f"Collected {len(rss_pool)} raw RSS items before topic filtering")

    linkedin_text_all = load_linkedin_submissions()
    enable_web_search = config.get("enable_web_search", True)
    topics = config.get("topics", [])

    sections = []
    for topic in topics:
        name = topic["name"]
        keywords = topic.get("keywords")
        search_prompt = topic.get("search_prompt")

        print(f"\n--- Topic: {name} ---")

        if keywords:
            pubmed_query = "(" + " OR ".join(f'"{k}"' for k in keywords) + ")"
            pubmed_items = fetch_pubmed(pubmed_query, lookback_days)
            topic_items = filter_for_topic(rss_pool, pubmed_items, keywords)
            print(f"{len(topic_items)} RSS/PubMed items matched")
        else:
            topic_items = []
            print("Open-ended topic — no keyword filter, web search only")

        web_research_text = ""
        if enable_web_search:
            print("Running web search for this topic...")
            web_research_text = research_topic(
                name, keywords=keywords, search_prompt=search_prompt
            )
        else:
            print("Web search disabled, skipping")

        section_body = synthesize_topic_section(
            name, topic_items, web_research_text, linkedin_text_all
        )
        sections.append(f"## {name}\n\n{section_body}")

    DIGEST_DIR.mkdir(exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    digest_path = DIGEST_DIR / f"digest-{today}.md"
    full_digest = (
        f"# Pharma Trend Digest — {today}\n\n"
        + "\n\n---\n\n".join(sections)
        + "\n"
    )
    digest_path.write_text(full_digest)

    clear_linkedin_submissions()
    print(f"\nDigest written to {digest_path}")


if __name__ == "__main__":
    main()
