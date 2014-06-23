import os
import hashlib
import hmac
import logging
import json
import time
import urllib2
import datetime
import xml.etree.ElementTree as ET
import re
import random

import webapp2
import jinja2

#from google.appengine.ext import db
from google.appengine.api import memcache

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir),
                               autoescape = True)

# create a password manager
password_mgr = urllib2.HTTPPasswordMgrWithDefaultRealm()

# Add the username and password.
username_file = open("bibles.org_username.txt", "r") # The service used to get Bible verses requires a username
username = username_file.read()
password = "X"
password_mgr.add_password(None, "https://bibles.org", username, password)

handler = urllib2.HTTPBasicAuthHandler(password_mgr)

# create "opener" (OpenerDirector instance)
opener = urllib2.build_opener(handler)

# use the opener to fetch a URL
#opener.open(a_url)

# Install the opener.
# Now all calls to urllib2.urlopen use our opener.
urllib2.install_opener(opener)


# Load data
with open('data/opening_sentences.json', 'r') as opening_sentences_json_data:
    opening_sentences = json.load(opening_sentences_json_data)

with open('data/antiphons.json', 'r') as antiphons_json_data:
    antiphons = json.load(antiphons_json_data)

with open('data/canticles.json', 'r') as canticles_json_data:
    canticles = json.load(canticles_json_data)

with open('data/collect.json', 'r') as collect_json_data:
    collects = json.load(collect_json_data)

with open('data/mission.json', 'r') as mission_json_data:
    mission_prayer = json.load(mission_json_data)

with open('data/closing_sentences.json', 'r') as closing_json_data:
    closing_sentences = json.load(closing_json_data)

with open('data/confession.json', 'r') as confession_json_data:
    confession = json.load(confession_json_data)

def render_str(template, **params):
    t = jinja_env.get_template(template)
    return t.render(params)

class BaseHandler(webapp2.RequestHandler):
    def write(self, *a, **kw):
        self.response.out.write(*a, **kw)

    def render_str(self, template, **params):
        #params['user'] = self.user
        t = jinja_env.get_template(template)
        return t.render(params)

    def render(self, template, **kw):
        self.write(self.render_str(template, **kw))

    def render_json(self, d):
        json_txt = json.dumps(d)
        self.response.headers['Content-Type'] = 'application/json; charset=UTF-8'
        self.write(json_txt)

    def set_secure_cookie(self, name, val):
        cookie_val = make_secure_val(val)
        self.response.headers.add_header(
            'Set-Cookie',
            '%s=%s; Path=/' % (name, cookie_val))

    def read_secure_cookie(self, name):
        cookie_val = self.request.cookies.get(name)
        return cookie_val and check_secure_val(cookie_val)


def get_todays_readings(date, update = False):
    """Get's today's readings- a dictionary of lists of Bible references
    update will refresh the cache"""

    if date is None:
        # Should offset for PST
        date = time.strftime("%Y-%m-%d", time.gmtime(time.time()- time.timezone))

    readings_date = "readings_" + date
    readings = memcache.get(readings_date)
    logging.debug(readings_date)
    if readings is None or update:
        try:
            # ESV api runs in US/Central time, but can return dates if requested
            url = urllib2.urlopen("http://www.esvapi.org/v2/rest/readingPlanInfo?key=IP&reading-plan=bcp&date=%s" % (date))
            xml_text = url.read()
            root = ET.fromstring(xml_text)
            morning_psalm = root.findall("./info/psalm-1")[0].text
            logging.info(morning_psalm)
            morning_psalms = split_psalm(morning_psalm)

            evening_psalm_list = root.findall("./info/psalm-2")
            if len(evening_psalm_list) > 0:
                evening_psalm = evening_psalm_list[0].text
                evening_psalms = split_psalm(evening_psalm)
            else:
                evening_psalms = morning_psalms

            ot_reading = root.findall("./info/ot")[0].text
            nt_reading = root.findall("./info/nt")[0].text
            gospel_reading = root.findall("./info/gospel")[0].text

            season = root.findall("./info/liturgical/season")[0].text

            readings = {"morn_psalm" : morning_psalms,
                        "even_psalm" : evening_psalms,
                        "readings" : [ot_reading, nt_reading, gospel_reading],
                        "season" : season}

            memcache.set(readings_date, readings)
        except:
            logging.error("Unable to get readings from esvapi.org")

            memcache.delete(readings_date)

            readings = {"morn_psalm": [1], "even_psalm": [1], "readings": ["Gen. 1:1", "Gen. 1:1", "Gen. 1:1"], "season": "At any Time"}
    return readings

def calc_easter(year = datetime.date.today().year):
    """Returns Easter as a date object.
    http://code.activestate.com/recipes/576517-calculate-easter-western-given-a-year/"""

    a = year % 19
    b = year // 100
    c = year % 100
    d = (19 * a + b - b // 4 - ((b - (b + 8) // 25 + 1) // 3) + 15) % 30
    e = (32 + 2 * (b % 4) + 2 * (c // 4) - d - (c % 4)) % 7
    f = d + e - 7 * ((a + 11 * d + 22 * e) // 451) + 114
    month = f // 31
    day = f % 31 + 1
    return datetime.date(year, month, day)

def calc_after_ascension(day = datetime.date.today(), year = datetime.date.today().year):
    return day >= calc_easter(year) + datetime.timedelta(days = 40)

def split_psalm(reference):
    """splits pslams when multiple are included together"""
    # Example input: 'Ps. 33,108:1-6,7-13'
    # Example input: 'Ps. 63:1-8,9-11,Ps. 98'
    if len(re.findall(r'Ps\.', reference)) > 1:
        psalms = reference.split(',Ps. ')
        psalms[0] = re.sub(r'Ps\. ', '', psalms[0])
    else:
        reference = re.sub(r'Ps\. ', '', reference)
        if re.search(r',\d+,\d+:', reference):
            psalms = reference.split(',', 2)
        elif re.search(r'^[^,]*\d+,\d+:', reference):
            psalms = reference.split(',', 1)
        else:
            psalms = reference.split(',')
    return psalms

def get_bible_passage(reference, translation='eng-ESV'):
    """gets the text of a Bible passage from Bibles.org.
    Returns a PassageInfo object."""

    passage_info = memcache.get(reference)
    if passage_info is None:
        if re.search(r'Philemon', reference):
            reference = re.sub('Philemon', 'Philemon 1:', reference)
        # See http://www.esvapi.org/v2/rest/readingPlanInfo?key=IP&reading-plan=bcp&date=2014-03-02 for apocrypha
        if re.search(r'Ecclus\.', reference):
            translation='eng-NABRE'
        logging.debug("https://bibles.org/v2/passages.js?version=%s&q[]=%s" \
            % (translation, urllib2.quote(reference)))
        url = urllib2.urlopen("https://bibles.org/v2/passages.js?version=%s&q[]=%s" \
            % (translation, urllib2.quote(reference)))

        json_text = url.read()
        try:
            json_response = json.loads(json_text)
            logging.debug(json_response)
            passages = json_response['response']['search']['result']['passages']
            html_text = ''.join([x['text'] for x in passages])
            verse_display = ', '.join([x['display'] for x in passages])
            passage = passages[0]
            copyright_display = passage['copyright']
            version = passage['version_abbreviation']
            fums = json_response['response']['meta']['fums']
            display = '<h2 class="old_style"><strong>%s (%s)</strong></h2>%s' \
                % (verse_display, version, html_text)
            passage_info = PassageInfo(display, copyright_display, fums)

            memcache.set(reference, passage_info)
        except:
            logging.error("Failed to get reading")
            passage_info = PassageInfo("<p>Failed to get today's reading</p>", "", "")
    return passage_info

def get_psalms(references):
    """references is a list of psalm references.
    Returns a list of PassageInfos"""
    passages = [get_bible_passage("Psalm " + str(x)) for x in references]
    return passages

def get_opening_sentences(season, day = None):
    """given a season (text), returns a dictionary with 'text' and 'verse"""
    #TODO: special case for Ascension day: it should be using Easter opening sentences
    if season in opening_sentences:
        season_list = opening_sentences[season]
    else:
        # Error handling: use 'At any Time' sentences if other is not available, or just use 'Praise the Lord!' if that fails
        season_list = opening_sentences.get('At any Time', ['Praise the Lord!'])
    return random.choice(season_list)

def get_antiphon(season, day = None):
    """given a season (and in the future a day), returns a string of the antiphon"""
    #TODO: bring in date for ascension calculation
    if season == "Easter":
        if calc_after_ascension():
            season_list = antiphons["Ascension Day until the Day of Pentecost"]
        else:
            season_list = antiphons["Easter Day until the Ascension"]
    elif season in antiphons:
        season_list = antiphons[season]
    else:
        season_list = antiphons.get('Other', ['Let us adore him.'])
    return random.choice(season_list)

def get_canticles(number = 2):
    """returns a list of canticles"""
    cant_list = random.sample(canticles.values(), number)
    for canticle in cant_list:
        with open(canticle['file'], 'r') as myfile:
            canticle["text"] = myfile.read()
    return cant_list

def get_invit_psalm(week = None):
    """returns a random invitatory psalm"""
    #TODO: add Christ_Passover during Easter week
    file_name = random.choice(["Jubilate.html", "Venite.html"])
    with open("templates/invit_psalm/" + file_name) as ipfile:
        invit_psalm = ipfile.read()
    return invit_psalm

def get_suffrages():
    """returns a random suffrage"""
    file_name = random.choice(["suffrages_A.html", "suffrages_B.html"])
    with open("templates/suffrages/" + file_name) as read_file:
        text = read_file.read()
    return text

def get_collects(n = 2):
    """returns a list of collects"""
    #TODO: sample from extra collects based on day of week, week, and special days
    return random.sample(collects['Any Time'], n)

def get_mission_prayer():
    """returns a prayer for mission"""
    #TODO: sample from extra collects based on day of week, week, and special days
    return random.choice(mission_prayer)

def get_closing_prayer():
    """returns a random closing prayer"""
    file_name = random.choice(["general_thanksgiving.html", "st_crysostom_prayer.html"])
    with open("templates/closing_prayer/" + file_name) as read_file:
        text = read_file.read()
    return text

class PassageInfo:
    # Holds text of a passage plus the copyright and fums information
    def __init__(self, text, copyright_display, fums):
        self.text = text
        self.copyright_display = copyright_display
        self.fums = fums

class MorningPrayer(BaseHandler):
    def get(self):
        todays_readings = get_todays_readings(self.request.get('date'))
        readings_reference = todays_readings['readings']
        psalm_reference = todays_readings['morn_psalm']
        opening = get_opening_sentences(todays_readings['season'])
        opening_sentences = opening['text']
        opening_verse = opening['verse']
        canticle0, canticle1 = get_canticles(2)
        reading0_info = get_bible_passage(readings_reference[0])
        reading1_info = get_bible_passage(readings_reference[1])
        reading2_info = get_bible_passage(readings_reference[2])
        psalm_info = get_psalms(psalm_reference)
        info_list = psalm_info + [reading0_info] + [reading1_info] + [reading2_info]
        copyright = set([passage.copyright_display for passage in info_list])
        copyright = "\n".join(copyright)
        fums = "\n".join([passage.fums for passage in info_list])
        self.render('morning-prayer.html', reading0 = reading0_info.text,
                    reading1 = reading1_info.text,
                    reading2 = reading2_info.text,
                    psalms = " ".join([psalm.text for psalm in psalm_info]),
                    opening_sentences = opening['text'],
                    opening_verse = opening['verse'],
                    season = todays_readings['season'],
                    antiphon = get_antiphon(todays_readings['season']),
                    canticle0 = canticle0, canticle1 = canticle1,
                    invit_psalm = get_invit_psalm(),
                    suffrages = get_suffrages(),
                    collects = get_collects(2),
                    mission_prayer = get_mission_prayer(),
                    closing_prayer = get_closing_prayer(),
                    closing_sentences = random.choice(closing_sentences),
                    confession = random.choice(confession),
                    copyright = copyright,
                    fums_script = fums
                    )

class UpdatePrayer(BaseHandler):
    def get(self):
        todays_readings = get_todays_readings(None, True)
        readings_reference = todays_readings['readings']
        psalm_reference = todays_readings['morn_psalm']
        get_bible_passage(readings_reference[0])
        get_bible_passage(readings_reference[1])
        get_bible_passage(readings_reference[2])
        get_psalms(psalm_reference)
        self.write("<p>Updated</p>")

class FrontPage(BaseHandler):
    def get(self):
        self.render('index.html')

app = webapp2.WSGIApplication([('/', FrontPage),
                               ('/prayer/morningprayer', MorningPrayer),
                               ('/tasks/updateprayers', UpdatePrayer)
                               ],
                              debug=True)
