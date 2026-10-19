# DICE News

A news website simulator for online behavioral experiments, built with [oTree](https://otree.readthedocs.io/en/latest/).

## Background

[DICE](https://github.com/Howquez/DICE) (Digital In-Context Experiments) is a platform for simulating social media feeds in controlled experiments. [DICE Lite](https://github.com/Howquez/DICE-lite) and [DICE TikTok](https://github.com/Howquez/DICE-tiktok) are standalone versions for researchers who prefer working directly with code.

DICE News applies the same idea to news websites. Participants see the front page of a (fictitious) online newspaper, loosely modelled on the mobile layout of major news sites: a masthead, a topic bar, a large lead story, teasers in several layouts, and display ads. Clicking a teaser opens the full article. The browser's back and forward buttons move between the front page and articles, just like on a real news site.

## What researchers can use it for

- **Misinformation and source credibility** — mix true and false stories, or vary outlet branding, and measure which articles people open and how long they read them
- **Advertising effects** — study attention to display ads placed between editorial content
- **News selection and exposure** — compare which stories are opened depending on position, layout, headline wording, or images
- **Headline and teaser experiments** — vary kickers, headlines, or teasers across conditions while keeping the article text constant

Like the other DICE versions, DICE News integrates with survey platforms (Qualtrics, SoSci Survey, etc.) via a redirect at the end. Participant IDs are passed as URL parameters so you can link reading behavior to survey responses.

## What it measures

Tracking events are streamed to the server while participants browse (via oTree's live pages), so data is not lost if a participant reloads the page or the connection drops. There are two exports (Data → custom exports in the oTree admin).

**`custom_export`: one row per participant × feed item**

| Field | Description |
|-------|-------------|
| `sequence_position` | Position of the item on the front page |
| `item_type` | `article` or `ad` |
| `teaser_dwell_seconds` | Seconds the teaser (or ad) was visible on the front page (at least `dwell_threshold` % of it on screen; paused while an article is open or the tab is hidden) |
| `n_opens` | How often the article was opened |
| `reading_seconds` | Total seconds the article was open (tab-hidden time excluded) |
| `reading_active_seconds` | Like `reading_seconds`, but the clock also stops `idle_seconds` after the last scroll, mouse, key, or touch activity |
| `max_scroll_pct` | Deepest point of the article that was on screen (0–100) |
| `ad_clicked` | Whether the ad was clicked (ads only) |

Device type, touch capability, and screen resolution are included in each row.

**`custom_export_events`: the raw event log**, one row per event (`page_load`, `device`, `dwell`, `open`, `close`, `ad_click`, `nav`) with client and server timestamps. `nav` events record the browser's back/forward buttons (`back`, `forward`) and attempts to leave the front page with the back button (`back_blocked`).

## Browser navigation

- Opening an article adds a browser history entry. The browser's back button (or the swipe-back gesture on phones) returns to the front page; forward reopens the article. The in-page **Back** buttons do the same.
- Pressing back on the front page does **not** leave the study: participants stay on the front page and see a short notice telling them to click **Continue** at the bottom.
- Reloading the page keeps all events recorded so far; the participant returns to the front page.

## Getting started

### Quickest path: download the `.otreezip`

If you just want to run the experiment as-is or make small changes to the CSV and templates, create a `.otreezip` with `otree zip` and upload it to [oTree Hub](https://www.otreehub.com/).

### Running locally

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
otree devserver
```

Open http://localhost:8000 and start the **News** session. DICE News requires oTree 6.

## Configuration

Session settings live in `settings.py` (`SESSION_CONFIG_DEFAULTS`):

| Setting | Description |
|---------|-------------|
| `data_path` | Path or URL of the CSV with your stimuli (local file, GitHub raw URL, Google Sheet, or Google Drive link) |
| `delimiter` | CSV delimiter (Google Sheets are always read as comma-separated) |
| `condition_col` | Name of the column that assigns items to conditions |
| `masthead` | Name of the news outlet shown in the header |
| `news_topics` | Topics shown in the topic bar (decorative) |
| `dwell_threshold` | Percent of a teaser that must be visible to count as viewed |
| `idle_seconds` | Seconds without activity after which active reading time stops counting |
| `survey_link`, `url_param` | Survey to redirect to at the end, and the URL parameter that carries the participant ID |
| `redirect_delay` | Milliseconds before the automatic redirect |
| `title`, `full_name`, `eMail`, `study_name` | Shown on the intro, consent, and debrief pages |

## The stimuli CSV

See `DICE/static/data/sample_news.csv` for an example (semicolon-delimited).

| Column | Required | Description |
|--------|----------|-------------|
| `doc_id` | yes | Unique integer id |
| `text` | yes | Article body; line breaks become paragraphs |
| `condition` | yes | Condition the item belongs to (participants are assigned to conditions in rotation) |
| `datetime` | yes | Publication date, e.g. `19.10.26 07:45` |
| `headline` | | Headline (defaults to the first sentence of `text`) |
| `teaser` | | Short summary shown on the front page and as the article's lede (defaults to the beginning of `text`) |
| `kicker` | | Short label above the headline, shown in red |
| `section` | | Section of the paper (e.g. Politics) |
| `media`, `alt_text` | | Image URL and its description (also shown as the caption in the article) |
| `username` | | Author ("By …"); for ads, the advertiser's name |
| `replies` | | Number of comments shown on the teaser |
| `layout` | | `standard` (image above text), `compact` (small image on the right), `overlay` (headline on top of the image), or `lead` (large). The first item on the page is always shown as the lead |
| `premium` | | `1` adds a small red "+" badge (like paywalled articles) |
| `sponsored` | | `1` turns the row into a display ad: the image is shown in a grey "Advertisement" box and links to `target` |
| `target` | | URL an ad links to |
| `sequence` | | Fixed position on the front page; items without a position are shuffled for each participant |

## License

See [LICENSE](LICENSE).
