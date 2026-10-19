from os import environ

SESSION_CONFIGS = [
    dict(
        name='News',
        app_sequence=['DICE'],
        num_demo_participants=3,
    ),
]

# if you set a property in SESSION_CONFIG_DEFAULTS, it will be inherited by all configs
# in SESSION_CONFIGS, except those that explicitly override it.
# the session config can be accessed from methods in your apps as self.session.config,
# e.g. self.session.config['participation_fee']

SESSION_CONFIG_DEFAULTS = dict(
    real_world_currency_per_point=1.00,
    participation_fee=0,
    title = 'Dr.',
    full_name = 'Hauke Roggenkamp',
    eMail = 'Hauke.Roggenkamp@mtec.ethz.ch',
    study_name = 'A study about news',
    survey_link = 'https://unisg.qualtrics.com/jfe/form/SV_0DnMoLpM0VxjhrM',
    url_param = 'PROLIFIC_PID',
    completion_code = 'ABCDEF',
    data_path = "DICE/static/data/sample_news.csv",
    delimiter=';',
    condition_col='condition',
    masthead = 'THE WEEKLY',    # name of the (fictitious) news outlet
    news_topics = ['Politics', 'Society', 'Business', 'Culture', 'Science', 'Digital', 'Sports'],
    dwell_threshold = 50,       # percent of a teaser that must be visible to count as being viewed
    idle_seconds = 30,          # reading time stops counting after this many seconds without any activity
    redirect_delay = 3000,      # milliseconds — auto-redirect delay
)

PARTICIPANT_FIELDS = ['news_items', 'finished']
SESSION_FIELDS = ['prolific_completion_url']

# ISO-639 code
# for example: de, fr, ja, ko, zh-hans
LANGUAGE_CODE = 'en'

# e.g. EUR, GBP, CNY, JPY
REAL_WORLD_CURRENCY_CODE = 'USD'
USE_POINTS = False

ADMIN_USERNAME = 'admin'
# for security, best to set admin password in an environment variable
ADMIN_PASSWORD = environ.get('OTREE_ADMIN_PASSWORD')

DEMO_PAGE_INTRO_HTML = """ Welcome """

# Set your own secret key via OTREE_SECRET_KEY environment variable
SECRET_KEY = environ.get('OTREE_SECRET_KEY', '8744361096089')
