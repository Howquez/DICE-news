from otree.api import *
import pandas as pd
import numpy as np
import re
import time
import itertools
import urllib.parse
import json


doc = """
Mimic a news website (front page with teasers and full articles) with DICE.
"""


class C(BaseConstants):
    NAME_IN_URL = 'DICE'
    PLAYERS_PER_GROUP = None
    NUM_ROUNDS = 1

    CONSENT_TEMPLATE = "DICE/T_Consent.html"
    ITEM_NEWS = "DICE/T_Item_News.html"

    LAYOUTS = ['standard', 'lead', 'compact', 'overlay']
    EVENT_KINDS = ['page_load', 'device', 'dwell', 'open', 'close', 'ad_click', 'nav']


class Subsession(BaseSubsession):
    feed_conditions = models.StringField(doc='indicates the feed conditions participants are assigned to')


class Group(BaseGroup):
    pass


class Player(BasePlayer):
    feed_condition = models.StringField(doc='indicates the feed condition a player is randomly assigned to')
    sequence = models.StringField(doc='prints the sequence of news items based on doc_id')

    touch_capability = models.BooleanField(doc="indicates whether a participant uses a touch device to access survey.",
                                           blank=True)
    device_type = models.StringField(doc="indicates the participant's device type based on screen width.",
                                     blank=True)
    screen_resolution = models.StringField(doc="indicates the participant's screen resolution, i.e., width x height.",
                                           blank=True)


class Event(ExtraModel):
    """One row per tracking event sent from the news page (see static/js/news.js)."""
    player = models.Link(Player)
    uid = models.StringField(doc='client-generated id, used to drop duplicates after reconnects or reloads')
    kind = models.StringField(doc='page_load, device, dwell, open, close, ad_click, or nav')
    doc_id = models.IntegerField(doc='feed item the event refers to (if any)')
    value = models.FloatField(doc='dwell: seconds in viewport; close: reading seconds (tab-hidden time excluded)')
    active_value = models.FloatField(doc='close: reading seconds, additionally excluding idle time')
    scroll_pct = models.FloatField(doc='close: deepest point scrolled to in the article (0-100)')
    info = models.StringField(doc='free text, e.g. navigation type or device details')
    client_ms = models.FloatField(doc='milliseconds since the page was loaded (client clock)')
    page_load = models.StringField(doc='id of the page load the event belongs to (a reload starts a new one)')
    server_time = models.FloatField(doc='unix time when the server received the event')


# FUNCTIONS -----
def creating_session(subsession):
    # Load and preprocess data once but shuffle and assign for each player
    df = read_feed(path=subsession.session.config['data_path'], delim=subsession.session.config['delimiter'])
    processed_items = preprocessing(df, subsession.session.config)

    # Check if the file contains any conditions and assign groups to it
    condition = 'condition'
    if condition in processed_items.columns:
        feed_conditions = itertools.cycle(processed_items[condition].unique())
        subsession.feed_conditions = ', '.join(processed_items[condition].unique())

    for player in subsession.get_players():
        items = processed_items.copy()

        # Assign a condition to the player if conditions are present
        if condition in items.columns:
            player.feed_condition = next(feed_conditions)
            items = items[items[condition] == player.feed_condition]

        # Fill missing sequence values with random ranks that are not taken yet
        ranks = np.arange(1, len(items) + 1)
        available_ranks = ranks[~np.isin(ranks, items['sequence'].dropna())]
        np.random.shuffle(available_ranks)
        missing_indices = items['sequence'].isnull()
        items.loc[missing_indices, 'sequence'] = available_ranks[:sum(missing_indices)]

        items.sort_values(by='sequence', inplace=True)
        items.reset_index(drop=True, inplace=True)

        player.participant.news_items = items
        player.sequence = ', '.join(map(str, items['doc_id'].tolist()))


def read_feed(path, delim):
    if re.match(r'^https?://\S+', path):
        if 'github' in path:
            items = pd.read_csv(path, sep=delim)
        elif 'docs.google.com/spreadsheets' in path:
            sheet_id = path.split('/d/')[1].split('/')[0]
            gid = '0'
            if 'gid=' in path:
                gid = path.split('gid=')[1].split('&')[0].split('#')[0]
            export_url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}'
            items = pd.read_csv(export_url, sep=',')
        elif 'drive.google.com' in path:
            if '/uc?' in path:
                items = pd.read_csv(path, sep=delim)
            else:
                file_id = path.split('/')[-2]
                download_url = f'https://drive.google.com/uc?id={file_id}'
                items = pd.read_csv(download_url, sep=delim)
        else:
            raise ValueError("Unrecognized URL format")
    else:
        items = pd.read_csv(path, sep=delim)
    return items


def is_url(s):
    return bool(re.match(r'^https?:\/\/', str(s)))


def format_dates(df):
    """Parse dates (European 'dd.mm.yy HH:MM' first, then pandas' flexible parser) and format them."""
    parsed = pd.to_datetime(df['datetime'], errors='coerce', format='%d.%m.%y %H:%M')
    mask = parsed.isna()
    if mask.any():
        parsed[mask] = pd.to_datetime(df.loc[mask, 'datetime'], errors='coerce')
    df['datetime'] = parsed.fillna(pd.Timestamp.now())
    # e.g. "October 17, 2026, 2:03 PM"
    df['date_long'] = df['datetime'].apply(
        lambda d: f"{d:%B} {d.day}, {d.year}, {d.hour % 12 or 12}:{d:%M %p}")
    return df


def fill_text_columns(df):
    """Make sure all optional text columns exist and contain strings."""
    for col in ['headline', 'teaser', 'kicker', 'section', 'username', 'media', 'alt_text', 'target', 'text']:
        if col not in df.columns:
            df[col] = ''
        df[col] = df[col].fillna('').astype(str)
    return df


def fill_numeric_columns(df):
    """Make sure all optional numeric columns exist and are integers."""
    for col in ['replies', 'premium', 'sponsored']:
        if col not in df.columns:
            df[col] = 0
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
    if 'sequence' not in df.columns:
        df['sequence'] = np.nan
    df['sequence'] = pd.to_numeric(df['sequence'], errors='coerce')
    return df


def prepare_teasers(df):
    """Derive headlines and teasers from the article text where they are missing; normalise layouts."""
    plain_text = df['text'].str.replace(r'<[^>]+>', '', regex=True).str.strip()

    missing = df['headline'].str.strip() == ''
    df.loc[missing, 'headline'] = plain_text[missing].str.split(r'(?<=[.!?])\s', n=1, regex=True).str[0]

    missing = df['teaser'].str.strip() == ''
    df.loc[missing, 'teaser'] = plain_text[missing].apply(
        lambda s: s if len(s) <= 200 else s[:200].rsplit(' ', 1)[0] + ' …')

    if 'layout' not in df.columns:
        df['layout'] = 'standard'
    df['layout'] = df['layout'].fillna('standard').astype(str).str.strip().str.lower()
    df.loc[~df['layout'].isin(C.LAYOUTS), 'layout'] = 'standard'
    return df


def prepare_media(df):
    """Clean image URLs and set the pic_available flag."""
    df['media'] = df['media'].str.replace("'|,", '', regex=True).str.strip()
    df['pic_available'] = df['media'].apply(is_url)
    return df


def prepare_body(df):
    """Line breaks in the article body become paragraphs."""
    df['text'] = df['text'].str.replace(r'\\n|\r?\n', '</p><p>', regex=True)
    return df


def preprocessing(df, config):
    """Orchestrate all preprocessing steps."""
    condition_col = config.get('condition_col')
    if condition_col and condition_col in df.columns and condition_col != 'condition':
        df.rename(columns={condition_col: 'condition'}, inplace=True)
    if 'condition' in df.columns:
        # Cast to string so it matches player.feed_condition (a StringField)
        df['condition'] = df['condition'].astype(str)

    df = format_dates(df)
    df = fill_text_columns(df)
    df = fill_numeric_columns(df)
    df = prepare_teasers(df)
    df = prepare_media(df)
    df = prepare_body(df)
    return df


def create_redirect(player):
    """Build the survey redirect URL with query parameters."""
    participant_id = player.participant.label or player.participant.code
    params = {player.session.config['url_param']: participant_id}

    completion_code = player.session.vars.get('completion_code')
    if completion_code is not None:
        params['cc'] = completion_code

    if player.feed_condition is not None:
        params['condition'] = player.feed_condition

    return player.session.config['survey_link'] + '?' + urllib.parse.urlencode(params)


def _as_float(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if np.isfinite(value) else None


def _as_int(value):
    value = _as_float(value)
    return int(value) if value is not None else None


def store_events(player, events):
    """Validate events sent by news.js and store them; returns the uids that are stored (incl. duplicates)."""
    stored = []
    known = {e.uid for e in Event.filter(player=player)}
    for event in events:
        if not isinstance(event, dict):
            continue
        uid = str(event.get('uid', ''))[:64]
        kind = event.get('kind')
        if not uid or kind not in C.EVENT_KINDS:
            continue
        if uid not in known:
            Event.create(
                player=player,
                uid=uid,
                kind=kind,
                doc_id=_as_int(event.get('doc_id')),
                value=_as_float(event.get('value')),
                active_value=_as_float(event.get('active_value')),
                scroll_pct=_as_float(event.get('scroll_pct')),
                info=str(event.get('info', ''))[:500],
                client_ms=_as_float(event.get('client_ms')),
                page_load=str(event.get('page_load', ''))[:64],
                server_time=time.time(),
            )
            known.add(uid)
            if kind == 'device':
                try:
                    device = json.loads(event.get('info') or '{}')
                except (TypeError, ValueError):
                    device = {}
                player.touch_capability = bool(device.get('touch'))
                player.device_type = str(device.get('device_type', ''))[:50]
                player.screen_resolution = str(device.get('screen_resolution', ''))[:50]
        stored.append(uid)
    return stored


# PAGES
class A_Intro(Page):
    form_model = 'player'


class B_Briefing(Page):
    form_model = 'player'


class C_Feed(Page):
    form_model = 'player'

    @staticmethod
    def vars_for_template(player: Player):
        items = player.participant.news_items.reset_index(drop=True)
        return dict(
            items=items.to_dict('index'),
            masthead=player.session.config['masthead'],
            news_topics=player.session.config['news_topics'],
        )

    @staticmethod
    def js_vars(player: Player):
        return dict(
            dwell_threshold=player.session.config['dwell_threshold'],
            idle_seconds=player.session.config['idle_seconds'],
        )

    @staticmethod
    def live_method(player: Player, data):
        events = data.get('events', []) if isinstance(data, dict) else []
        stored = store_events(player, events[:500])
        return {player.id_in_group: dict(ack=stored)}

    @staticmethod
    def before_next_page(player, timeout_happened):
        player.participant.finished = True

        completion_code = player.session.vars.get('completion_code')
        base_url = 'https://app.prolific.com/submissions/complete'
        if player.session.vars.get('prolific_completion_url') is not None:
            player.session.vars['prolific_completion_url'] = (
                f'{base_url}?cc={completion_code}' if completion_code else base_url
            )
        else:
            player.session.vars['prolific_completion_url'] = 'NA'


class D_Redirect(Page):

    @staticmethod
    def is_displayed(player):
        return len(player.session.config['survey_link']) > 0

    @staticmethod
    def vars_for_template(player: Player):
        return dict(link=create_redirect(player))

    @staticmethod
    def js_vars(player):
        return dict(
            link=create_redirect(player),
            redirect_delay=player.session.config.get('redirect_delay', 3000),
        )


class D_Debrief(Page):

    @staticmethod
    def is_displayed(player):
        return len(player.session.config['survey_link']) == 0


page_sequence = [A_Intro,
                 B_Briefing,
                 C_Feed,
                 D_Redirect,
                 D_Debrief]


# EXPORTS -----
def summarise_events(events):
    """Aggregate a player's events per doc_id."""
    summary = {}
    for e in events:
        if e.doc_id is None:
            continue
        s = summary.setdefault(e.doc_id, dict(dwell=0.0, opens=0, reading=0.0, active=0.0, scroll=None, ad=False))
        if e.kind == 'dwell' and e.value is not None:
            s['dwell'] += e.value
        elif e.kind == 'open':
            s['opens'] += 1
        elif e.kind == 'close':
            s['reading'] += e.value or 0
            s['active'] += e.active_value or 0
            if e.scroll_pct is not None:
                s['scroll'] = max(s['scroll'] or 0, e.scroll_pct)
        elif e.kind == 'ad_click':
            s['ad'] = True
    return summary


def custom_export(players):
    """One row per participant x feed item."""
    yield ['session', 'participant_code', 'participant_label', 'participant_in_session', 'condition',
           'doc_id', 'sequence_position', 'item_type', 'teaser_dwell_seconds', 'n_opens', 'reading_seconds',
           'reading_active_seconds', 'max_scroll_pct', 'ad_clicked',
           'device_type', 'touch_capability', 'screen_resolution']

    for p in players:
        if not p.sequence:
            continue
        doc_ids = [int(x.strip()) for x in p.sequence.split(',')]
        summary = summarise_events(Event.filter(player=p))
        try:
            items = p.participant.news_items
            sponsored = dict(zip(items['doc_id'].astype(int), items['sponsored'].astype(int)))
        except (AttributeError, KeyError, TypeError):
            sponsored = {}

        for position, doc_id in enumerate(doc_ids, start=1):
            s = summary.get(doc_id, dict(dwell=0.0, opens=0, reading=0.0, active=0.0, scroll=None, ad=False))
            is_ad = bool(sponsored.get(doc_id, 0))
            yield [
                p.session.code,
                p.participant.code,
                p.participant.label,
                p.id_in_group,
                p.feed_condition,
                doc_id,
                position,
                'ad' if is_ad else 'article',
                round(s['dwell'], 3),
                '' if is_ad else s['opens'],
                '' if is_ad else round(s['reading'], 3),
                '' if is_ad else round(s['active'], 3),
                '' if is_ad or s['scroll'] is None else round(s['scroll'], 1),
                s['ad'] if is_ad else '',
                p.field_maybe_none('device_type'),
                p.field_maybe_none('touch_capability'),
                p.field_maybe_none('screen_resolution'),
            ]


def custom_export_events(players):
    """Raw event log: one row per tracking event."""
    yield ['session', 'participant_code', 'participant_label', 'condition', 'page_load', 'client_ms',
           'server_time', 'kind', 'doc_id', 'value', 'active_value', 'scroll_pct', 'info']
    for p in players:
        for e in sorted(Event.filter(player=p), key=lambda e: (e.server_time or 0, e.client_ms or 0)):
            yield [
                p.session.code,
                p.participant.code,
                p.participant.label,
                p.feed_condition,
                e.page_load,
                e.client_ms,
                e.server_time,
                e.kind,
                e.doc_id,
                e.value,
                e.active_value,
                e.scroll_pct,
                e.info,
            ]
