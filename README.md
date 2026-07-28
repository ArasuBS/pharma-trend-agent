# Pharma Trend Digest Agent

Monthly, multi-topic digest. Tracks whatever topics you define — by
default: ADC, Bispecifics, Cell Line Development, NAMs (organoids /
patient-derived organoids / organ-on-chip), and New Trends in Drug
Discovery (new gene editing tools, assays, biophysical instruments,
etc.). Sources: Fierce Pharma, Endpoints News, STAT News, Nature
Biotechnology, Nature Reviews Drug Discovery, Cell, Science (via RSS),
PubMed, targeted web search per topic, and LinkedIn posts you paste in
manually.

**Every factual claim in the output carries a source link.** This is
enforced in the prompts, not just requested — if the model can't find
a real link for something, it's instructed to drop that claim rather
than state it unsourced. Verify anything you plan to act on or repeat
by clicking through to the source — treat the digest as a well-organized
starting point for that, not a final answer.

## Switching topics

Open `sources.yaml`, edit the `topics` list at the bottom. Two kinds:

- **Keyword-based** — give a `keywords` list. Used to filter RSS/PubMed
  and to focus that topic's web search. Example:
  ```yaml
  - name: "Radioligand Therapy"
    keywords:
      - radioligand therapy
      - targeted alpha therapy
      - radiopharmaceutical
  ```
- **Open-ended** — no fixed vocabulary to filter on (like "new trends,"
  where you don't know the tool's name in advance). Give a
  `search_prompt` instead of `keywords`, and it relies entirely on web
  search.

Delete a topic, add one, rename one, change its keywords — that's the
whole process. No code changes needed either way.

## What it does, in order

1. Pulls the shared RSS pool (all feeds in `sources.yaml`) once
2. For each topic in the `topics` list:
   - Filters the RSS pool against that topic's keywords (keyword-based
     topics only)
   - Runs a PubMed search scoped to that topic's keywords, genuinely
     reaching back the full `lookback_days` window (confirmed 365 days
     by default — PubMed supports real date-range search)
   - Runs a targeted web search for that topic (if `enable_web_search`
     is on) — for open-ended topics, this is the *only* source
   - Reads whatever's in `linkedin_manual.md` and includes anything
     relevant to that topic
   - Synthesizes everything into a Signal Items / Quick Hits section,
     every claim carrying a source link
3. Stitches all topic sections into one digest, writes
   `digests/digest-YYYY-MM-DD.md`, commits it to the repo
4. Clears `linkedin_manual.md` so it's ready for next month

## The RSS/PubMed distinction — read this once

- **PubMed**: real date-range search. `lookback_days: 365` genuinely
  reaches back a year.
- **RSS feeds** (news sites and journals): only ever expose each
  publisher's most recent items, typically the last few weeks. This is
  a property of RSS as a format, not something any setting here can
  change. `lookback_days` still applies to RSS filtering, but in
  practice it won't matter much — the feed simply won't have a year of
  items sitting there to filter through.

## Cost

Rough estimate per monthly run, at current Claude Sonnet 5 pricing,
with the default 5 topics:

- Web search (per topic) + section synthesis (per topic): roughly
  $0.30–0.65 total for all 5 topics combined
- With `enable_web_search: false`: closer to $0.10–0.15 total (PubMed +
  RSS + synthesis only — open-ended topics will come back empty,
  since they have no other source to draw on)

Either way, at monthly cadence this is a few dollars a year at most.

## One-time setup

1. Create a new GitHub repo, push these files into it.
2. In the repo: **Settings → Secrets and variables → Actions → New
   repository secret**. Name it `ANTHROPIC_API_KEY`, paste your
   Anthropic API key as the value.
3. That's it — the workflow in `.github/workflows/weekly-digest.yml`
   runs automatically on the 1st of every month. Each month's digest
   lands in the `digests/` folder in the repo.

## During the month

Whenever you see a LinkedIn post worth including, open
`linkedin_manual.md` in the repo and paste it in — full text, a link,
and a note on which topic it belongs to. It gets folded into the
relevant topic's section on the next run, then cleared.

## Running it manually / testing it

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key_here
python pharma_trend_agent.py
```

Check the console output — it'll warn you if any RSS feed fails to
parse (publishers change feed URLs occasionally; when that happens,
just find the new URL and update it in `sources.yaml`), and it prints
progress per topic so you can see what matched and what didn't.

You can also trigger the GitHub Actions run manually anytime: go to
the **Actions** tab → **Monthly Pharma Trend Digest** → **Run workflow**.

## Tuning it

- **Switch topics**: edit the `topics` list in `sources.yaml` — see
  "Switching topics" above.
- **Add/remove RSS sources**: edit `rss_feeds` in `sources.yaml`.
- **Turn off web search** (cheaper, less coverage): set
  `enable_web_search: false` in `sources.yaml`.
- **Change a section's structure**: edit
  `build_topic_section_prompt()` in `pharma_trend_agent.py`.
- **Change the schedule**: edit the `cron` line in
  `.github/workflows/weekly-digest.yml` ([crontab.guru](https://crontab.guru)
  helps with the syntax).
