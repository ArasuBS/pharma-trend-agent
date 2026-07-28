# Pharma Trend Digest Agent

Weekly digest on ADC + broader drug discovery/CDMO/manufacturing trends.
Sources: Fierce Pharma, Endpoints News, STAT News, Nature Biotechnology,
Nature Reviews Drug Discovery, Cell, Science (via RSS), PubMed, and
LinkedIn posts you paste in manually.

## What it does, in order

1. Pulls the last 7 days from every RSS feed in `sources.yaml`
2. Pulls the last 7 days from PubMed matching the configured query
3. Reads whatever you've pasted into `linkedin_manual.md`
4. Filters everything against your ADC + broad keyword list
5. Sends the filtered set to Claude to synthesize into a digest
   (Signal Items / Quick Hits / Pattern Watch)
6. Writes `digests/digest-YYYY-MM-DD.md` and commits it to the repo
7. Clears `linkedin_manual.md` so it's ready for next week

## One-time setup

1. Create a new GitHub repo, push these files into it.
2. In the repo: **Settings → Secrets and variables → Actions → New
   repository secret**. Name it `ANTHROPIC_API_KEY`, paste your
   Anthropic API key as the value.
3. That's it — the workflow in `.github/workflows/weekly-digest.yml`
   runs automatically every Monday. You'll find each week's digest in
   the `digests/` folder in the repo.

## During the week

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
the **Actions** tab → **Weekly Pharma Trend Digest** → **Run workflow**.

## Tuning it

- **Change the filter**: edit `modality_keywords` and `broad_keywords`
  in `sources.yaml`. No code changes needed.
- **Add/remove sources**: edit `rss_feeds` in `sources.yaml`.
- **Change the digest structure**: edit `build_digest_prompt()` in
  `pharma_trend_agent.py`.
- **Change the schedule**: edit the `cron` line in
  `.github/workflows/weekly-digest.yml` ([crontab.guru](https://crontab.guru)
  helps with the syntax).
