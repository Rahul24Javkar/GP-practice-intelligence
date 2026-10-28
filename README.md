# GP Practice Intelligence & Outreach Engine

A Python-based prototype that collects publicly available information from GP practice websites, extracts structured practice details using Google Gemini, scores potential leads using local rules, generates outreach email drafts, and performs preliminary compliance checks. A Streamlit dashboard lets users review results and export CSV files.

> **Prototype status:** The current dataset contains two unique practice records from ten raw website text files. Gemini API availability affected extraction coverage during development. Scores are heuristic, outreach emails are drafts only, and compliance checks are preliminary—not legal advice or a compliance certification.

## Objectives

- Collect text from publicly accessible GP practice websites.
- Extract structured practice information with source evidence.
- Rank practices using a transparent, rule-based lead score.
- Create outreach email drafts for human review.
- Flag potential issues before outreach.
- Explore results in a dashboard and export CSV reports.

## Features

- **Website fetching:** Reads URLs from `urls.csv` and saves fetched page text under `data/raw/`.
- **AI-assisted extraction:** Uses Google Gemini to extract practice names, addresses, contact details, services, booking options, telehealth information, doctor counts, confidence, and evidence.
- **Lead scoring:** Uses local, rule-based logic in `score.py`.
- **Outreach drafting:** `outreach.py` generates email drafts. Drafts are not sent automatically.
- **Preliminary compliance screening:** `compliance.py` checks selected wording risks and missing information.
- **Streamlit dashboard:** Provides an overview, practice explorer, outreach drafts, compliance review, and CSV exports.

## Technology stack

- Python
- pandas
- Streamlit
- Google GenAI SDK / Gemini API
- python-dotenv
- CSV for local data storage

See `requirements.txt` for the Python dependencies.

## Project structure

```text
gp-practice-intelligence/
├── app.py
├── fetch.py
├── extract.py
├── score.py
├── outreach.py
├── compliance.py
├── urls.csv
├── requirements.txt
├── .env.example
├── .gitignore
├── prompts/
│   ├── extraction.txt
│   ├── outreach.txt
│   └── compliance.txt
└── data/
    ├── raw/
    │   └── *.txt
    ├── practices.csv
    ├── scored_practices.csv
    ├── outreach_drafts.csv
    ├── compliance_report.csv
    └── accuracy.json
```

Generated files may differ depending on which scripts have been run. A local backup such as `practices_backup.csv` may also exist; it is not required for the pipeline.

## Setup

### Requirements

- Python installed on your machine.
- A Google AI Studio API key for Gemini-powered extraction.
- Internet access for fetching websites and calling the Gemini API.

### 1. Create and activate a virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

### 3. Configure the API key

Copy `.env.example` to `.env` and set your API key:

```env
GEMINI_API_KEY=replace_with_your_own_key
```

Keep `.env` private. Do not commit API keys or secrets to source control. The local scoring, outreach, compliance, and dashboard scripts use the generated CSVs and do not require Gemini calls in the current implementation.

## Running the pipeline

Run commands from the project root with the virtual environment activated.

### 1. Fetch website text

```powershell
python fetch.py
```

The fetcher reads `urls.csv` and saves available website text files under `data/raw/`. A website may block automated requests, time out, redirect, or return insufficient text; check the logs and resulting files.

Only collect information that is publicly accessible and respect each website's terms, robots instructions, rate limits, and applicable law. Do not collect patient information.

### 2. Extract structured practice records

```powershell
python extract.py
```

This step uses Gemini to turn website text into structured records in `data/practices.csv`. The current extractor validates the response schema, checks quoted evidence against source text, saves successful records incrementally, skips source files already represented in the CSV, and stops the run when it detects a quota/rate-limit error.

Gemini can return transient `503` or `504` errors. A successful API key does not guarantee that a model is available or that quota remains. Retry later rather than repeatedly submitting requests when a quota error occurs.

### 3. Score leads

```powershell
python score.py
```

Reads `data/practices.csv` and writes `data/scored_practices.csv`. The score is based on locally defined rules and is not a validated prediction of a practice's purchasing intent.

### 4. Generate outreach drafts

```powershell
python outreach.py
```

Reads scored practice data and writes `data/outreach_drafts.csv`. Drafts are for human review and are not automatically emailed.

### 5. Run preliminary compliance checks

```powershell
python compliance.py
```

Reads outreach drafts and writes `data/compliance_report.csv`. The checks flag selected wording patterns and missing information; they do not establish legal compliance.

### 6. Launch the dashboard

```powershell
python -m streamlit run app.py
```

Open the local URL printed by Streamlit (usually `http://localhost:8501`). Keep the terminal running while using the dashboard. Use the dashboard's **Refresh data** control after regenerating CSV outputs.

## Output files

| File | Purpose |
|---|---|
| `data/raw/*.txt` | Text captured from individual website pages |
| `data/practices.csv` | Structured extracted practice records and evidence |
| `data/scored_practices.csv` | Practice records with lead scores, tiers, and score reasons |
| `data/outreach_drafts.csv` | Unsent outreach email drafts and related lead fields |
| `data/compliance_report.csv` | Preliminary review statuses and flags |
| `data/accuracy.json` | Local accuracy-related output, if produced by the current workflow |

Some output files may not exist until the corresponding script has run.

## Dashboard

The Streamlit dashboard contains:

- **Overview:** Record counts, average score, lead-tier distribution, and highest-scoring practices.
- **Practice explorer:** Search and filter records and inspect available fields and scoring reasons.
- **Outreach drafts:** Review draft recipients, subjects, and email bodies.
- **Compliance review:** Inspect preliminary flags and review statuses.
- **Exports:** Download CSV results for further analysis.

## AI and scoring approach

Gemini is used to extract structured information from website text. The extraction prompt and schema guide the expected fields; source evidence is retained where available and checked against captured text.

Lead scoring is performed locally with explicit rules, such as whether online booking or telehealth is listed, the number of services, available doctor-count information, contact details, and extraction confidence. These are prototype heuristics and should be reviewed and calibrated before business decisions are made.

Outreach drafts should refer only to verified information and should not assert unverified operational problems, capabilities, savings, clinical benefits, or compliance claims.

## Privacy, responsible use, and limitations

- Use only publicly available practice/business information relevant to the project.
- Do not collect, store, or process patient data.
- Publicly listed contact information does not automatically mean unsolicited outreach is permitted. Verify applicable Australian privacy, spam, marketing, and other legal requirements before contacting any practice.
- Keep outreach as draft-only until a person has reviewed the content, recipient, purpose, and permission to contact.
- Compliance screening is a lightweight set of local checks. It may miss risky wording or flag harmless wording and is not legal advice.
- Lead scores are heuristic, not validated commercial predictions.
- Extracted fields may be incomplete or incorrect. Check source evidence and confirm important details before relying on them.
- Website access, page structure, model availability, and API quotas can affect results.
- The current prototype has two unique practice records from ten raw website text files. Some Gemini requests failed due to model availability or quota limits, so the dataset is not comprehensive.
- Do not present current results as a complete or representative dataset of Sydney GP practices.

## Security

- Never commit `.env`, API keys, access tokens, or other secrets.
- Keep `.env.example` as a placeholder-only template.
- Review `.gitignore` before publishing the repository.
- Before committing generated data, confirm that it is appropriate to share and contains no sensitive or unintended information.

## Future improvements

- Add source URL, fetch timestamp, and evidence snippets to every displayed record.
- Improve duplicate detection using normalized practice name, address, and phone.
- Add tests for parsing, schema validation, scoring, duplicate handling, and CSV persistence.
- Add stronger extraction retry/backoff and a selectable single-URL processing mode.
- Add measured extraction-quality evaluation against manually verified examples.
- Improve compliance checks with human-reviewed rules and jurisdiction-specific review.
- Track draft generation method and distinguish AI-generated drafts from local template fallbacks.
- Expand coverage only after verifying sources, access permissions, and data quality.

## Disclaimer

This project is a prototype for learning and demonstration. It does not provide legal advice, certify compliance, make clinical decisions, or send outreach emails automatically. Verify source information and applicable requirements before using outputs operationally.
