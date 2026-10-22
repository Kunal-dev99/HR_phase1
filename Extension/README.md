# Sales Nav List Exporter

A tiny Chrome extension that exports the people shown in your **LinkedIn Sales
Navigator** search results to a CSV — in *list mode*, the lower-risk way.

It reads only the data already rendered on your results pages (name, headline,
title, company, location, connection degree, profile URL) and **never opens
individual profiles**. Profile visits are what trip LinkedIn's bot detection;
reading the list you're already looking at is far quieter.

## Install (Load unpacked)

1. Unzip this folder somewhere permanent.
2. Open Chrome → `chrome://extensions/`
3. Turn on **Developer mode** (top-right).
4. Click **Load unpacked** and select this folder.
5. Pin the extension if you like (puzzle-piece icon → pin).

## Use

1. Go to `https://www.linkedin.com/sales/search/people`, run your search,
   apply filters.
2. Click the extension icon.
3. Enter the **Source consultant** (stamped on every row), set **Max pages**
   and the per-page **delay range** (keep it human — 4–8s+).
4. Press **Start**. It scrolls each page, grabs the rows, turns the page,
   and repeats. The counter updates live; you can close the popup and the run
   keeps going.
5. Press **Download CSV** when you're happy (works mid-run too).
6. **Clear collected** resets the buffer for a fresh search.

## Output columns (v1.6 — Oracle-project shape)

The first 15 columns match the Oracle project's **Tab 1** header exactly and in
order, so the CSV drops straight into the project:

`First Name, Last Name, LinkedIn URL, Company, Seniority, Job Title,
Job Classification, Location, City, Country, Department, Sector,
Source: Consultant Name, Oracle Product, Degree of Connection`

…followed by four **helper** columns the project uses but that aren't part of
the final sheet:

`Full Name, Headline, About, Sales Nav URL`

### What the extractor fills vs. leaves blank

Derived locally from what's already on the row (no extra requests):

- **City / Country** — parsed from Location. `Swindon, England, United Kingdom`
  → City `Swindon`, Country `United Kingdom`. Region words
  (England/Scotland/Wales/NI) normalise to *United Kingdom* and are never used
  as a city. A bare country → country only, city blank. A city is never guessed
  from a country.
- **Job Classification** — Anil's rule, six checks in order (first match wins):
  1) Architect → *Influencer* (always). 2) Director / VP / General Manager / C-suite
  → *Signatory*. 3) Head of / Head / Manager / Owner / Product Lead / Delivery Lead
  → *Decision Maker*. 4) Analyst → *Can help identify stakeholders* (always). 5) Functional /
  Techno-Functional / SME / Expert / Principal / Lead → *Influencer*. 6) everything else
  (plain Consultant, Developer, Engineer, Specialist, Tester, Trainer, DBA, Admin) →
  *Can help identify stakeholders*. Key splits: Director/VP=Signatory but Head/Manager=
  Decision Maker; Functional Consultant=Influencer but plain/Technical Consultant=Can help;
  SME=Influencer but Specialist=Can help; Analyst always=Can help; Architect always=Influencer.
- **Department** — Finance / HR / Procurement / Supply Chain / IT / Projects,
  from the title; blank if not clear.
- **Seniority** — C-Suite / Director / VP / Head / Principal / Manager / Lead /
  Senior / Mid, from the title.

Left **blank on purpose** — these need web research, which the Oracle project
does (the extractor never guesses them):

- **Sector**
- **Oracle Product**

**LinkedIn URL** holds the public `/in/` link if it happens to be visible in the
row, otherwise the cookie-based Sales Navigator URL. **Sales Nav URL** (helper)
always keeps that cookie link as a stable key, so the later public-URL resolver
pass can match rows back even after LinkedIn URL is overwritten.

UTF-8 with a BOM, so it opens cleanly in Excel.

## Optional: resolve public URLs

The **Resolve public profile URLs** toggle opens each lead's "⋯ → View profile"
menu to read the public `/in/` link. It's slower and higher-detection (one menu
open per lead) — leave it OFF for normal fast crawls and run the dedicated
URL-resolver pass later instead.

## Staying safe

- Keep delays generous and spread big lists (1k+) across multiple days.
- Don't run other LinkedIn automation at the same time.
- Lower your daily volume on newer or recently-restricted accounts.
- This reads data you can already see, but bulk extraction is against
  LinkedIn's User Agreement — the risk is to your own account. Use judgment.

## If it stops finding rows

LinkedIn occasionally changes its markup. The script keys off
`data-anonymize="..."` attributes, which are stable, but if a future update
breaks it, the selectors in `content.js` (`findRows`, `extract`) are the only
things that need adjusting.
