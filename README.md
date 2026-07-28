# Pharma Trend Digest Agent

Monthly digest on ADC + broader drug discovery/CDMO/manufacturing trends.
Sources: Fierce Pharma, Endpoints News, STAT News, Nature Biotechnology,
Nature Reviews Drug Discovery, Cell, Science (via RSS), PubMed, and
LinkedIn posts you paste in manually.

## What it does, in order

1. Pulls the last ~year from every RSS feed in `sources.yaml` (in practice,
   RSS only ever shows a feed's most recent items — usually the last few
   weeks — regardless of this setting; see the comment in `sources.yaml`)
2. Pulls the last year from PubMed matching the configured query (this one
   genuinely reaches back a year, since PubMed has real date-range search)
3. Reads whatever you've pasted into `linkedin_manual.md`
4. Runs 5-8 targeted web searches to fill the gap RSS/PubMed can't reach —
   deals, funding, approvals, capacity expansions that might not be in a
   feed yet (skip this by setting `enable_web_search: false` in
   `sources.yaml` if you want to stay on the cheaper path — see Cost below)
5. Filters everything against your ADC + broad keyword list
6. Sends the filtered set to Claude to synthesize into a digest
   (Signal Items / Quick Hits / Pattern Watch)
7. Writes `digests/digest-YYYY-MM-DD.md` and commits it to the repo
8. Clears `linkedin_manual.md` so it's ready for next month

## Cost

Rough estimate per monthly run, at current Claude Sonnet 5 pricing:

- RSS + PubMed + synthesis only: ~$0.05–0.07
- With the web search step enabled (default): ~$0.30–0.50

Either way, at monthly cadence this is a few dollars a year at most —
not something to worry about unless you're running it far more often
than monthly.

## One-time setup

1. Create a new GitHub repo, push these files into it.
2. In the repo: **Settings → Secrets and variables → Actions → New
   repository secret**. Name it `ANTHROPIC_API_KEY`, paste your
   Anthropic API key as the value.
3. That's it — the workflow in `.github/workflows/weekly-digest.yml`
   runs automatically on the 1st of every month. You'll find each month's digest in
   the `digests/` folder in the repo.

## During the month

Whenever you see a LinkedIn post worth including, open
`linkedin_manual.md` in the repo (or clone locally) and paste it in —
full text, a link, whatever's fastest. It gets folded into the next
run and then cleared.

## Running it manually / testing it

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key_here
python pharma_trend_agent.py
```

Check the console output — it'll warn you if any RSS feed fails to
parse (publishers change feed URLs occasionally; when that happens,
just find the new URL and update it in `sources.yaml`).

You can also trigger the GitHub Actions run manually anytime: go to
the **Actions** tab → **Monthly Pharma Trend Digest** → **Run workflow**.

## Tuning it

- **Change the filter**: edit `modality_keywords` and `broad_keywords`
  in `sources.yaml`. No code changes needed.
- **Add/remove sources**: edit `rss_feeds` in `sources.yaml`.
- **Change the digest structure**: edit `build_digest_prompt()` in
  `pharma_trend_agent.py`.
- **Change the schedule**: edit the `cron` line in
  `.github/workflows/weekly-digest.yml` ([crontab.guru](https://crontab.guru)
  helps with the syntax).
