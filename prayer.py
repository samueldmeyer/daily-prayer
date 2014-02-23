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


# Daily readings in epiphany- work in progress
epiphany = [
    0, 1, 2, 3, 4,
    [
        0,1,2,3,4,
        {
            "morn_psalm": [88], "even_psalm": [91,92], "readings": ["Gen. 27:46-28:4,10-22", "Rom. 13:1-14", "John 8:33-47"]
                }, {
            "morn_psalm": [87, 90], "even_psalm": [136], "readings": ["Gen. 29:1-20", "Rom. 14:1-23", "John 8:47-59"]
        }
    ],
    [
        {
            "morn_psalm": [66, 67], "even_psalm": [19, 46], "readings": ["Gen. 29:20-35", "1 Tim. 3:14-4:10", "Mark 10:23-31"]
        }, {
            "morn_psalm": ["89:1-18"], "even_psalm": ["89:19-52"], "readings": ["Gen. 30:1-24", "1 John 1:1-10", "John 9:1-17"]
        }, {
            "morn_psalm": [97, 99], "even_psalm": [94], "readings": ["Gen. 31:1-24", "1 John 2:1-11", "John 9:18-41"]
        }, {
            "morn_psalm": ["101", "101:1-30"], "even_psalm": ["119:121-144"], "readings": ["Gen. 31:25-50", "1 John 2:12-17", "John 10:1-18"]
        }
    ]
]

def get_todays_readings(update = False):
    """Get's today's readings- a dictionary of lists of Bible references
    update will refresh the cache"""
    
    # ESV runs in US/Central time, but can return dates if requested
    url = urllib2.urlopen("http://www.esvapi.org/v2/rest/readingPlanInfo?key=IP&reading-plan=bcp")
    xml_text = url.read()
    
    readings = memcache.get("readings")
    if readings is None or update:
        try:
            root = ET.fromstring(xml_text)
            morning_psalm = root.findall("./info/psalm-1")[0].text
            logging.error(morning_psalm)
            morning_psalms = split_psalm(morning_psalm)
            
            evening_psalm = root.findall("./info/psalm-2")[0].text
            evening_psalms = split_psalm(evening_psalm)
            
            ot_reading = root.findall("./info/ot")[0].text
            nt_reading = root.findall("./info/nt")[0].text
            gospel_reading = root.findall(".info/gospel")[0].text
            
            readings = {"morn_psalm" : morning_psalms,
                        "even_psalm" : evening_psalms,
                        "readings" : [ot_reading, nt_reading, gospel_reading]}
            
            memcache.set("readings", readings)
        except:
            logging.error("Unable to get readings from esvapi.org")
            
            memcache.delete("readings")
            
            readings = {"morn_psalm": [1], "even_psalm": [1], "readings": ["Gen. 1:1", "Gen. 1:1", "Gen. 1:1"]}
    return readings
  
def split_psalm(reference):
    """splits pslams when multiple are included together"""
    # Example input: 'Ps. 33,108:1-6,7-13'
    reference = re.sub(r'Ps\. ', '', reference)
    if re.search(r',\d+,\d+:', reference):
        psalms = reference.split(',', 2)
    elif re.search(r'^[^,]*\d+,\d+:', reference):
        psalms = reference.split(',', 1)
    else:
        psalms = reference.split(',')
    return psalms
    
def get_bible_passage(reference):
    """gets the text of a Bible passage from Bibles.org"""
    
    display = memcache.get(reference)
    if display is None:
        logging.debug("https://bibles.org/v2/passages.js?version=eng-ESV&q[]=%s" % urllib2.quote(reference))
        url = urllib2.urlopen("https://bibles.org/v2/passages.js?version=eng-ESV&q[]=%s" % urllib2.quote(reference))
        
        json_text = url.read()
        try:
            json_response = json.loads(json_text)
            logging.debug(json_response)
            passages = json_response['response']['search']['result']['passages']
            html_text = ''.join([x['text'] for x in passages])
            verse_display = ', '.join([x['display'] for x in passages])
            copyright_display = json_response['response']['search']['result']['passages'][0]['copyright']
            version = json_response['response']['search']['result']['passages'][0]['version_abbreviation']
            fums = json_response['response']['meta']['fums_noscript']
            display = '<h2 class="old_style"><strong>' + verse_display + " (" + version +")</strong></h2>" + \
                html_text + '<br><span class = "copyright">' + copyright_display + "</span>" + fums
            memcache.set(reference, display)
        except:
            logging.error("Failed to get reading")
            display = "<p>Failed to get today's reading</p>"
    return display

def get_psalms(references):
    """references is a list of psalm references"""
    passages = [get_bible_passage("Psalm " + str(x)) for x in references]
    return " ".join(passages)

class MorningPrayer(BaseHandler):
    def get(self):
        todays_readings = get_todays_readings()
        readings_reference = todays_readings['readings']
        psalm_reference = todays_readings['morn_psalm']
        logging.error(psalm_reference)
        self.render('morning-prayer.html', reading1 = get_bible_passage(readings_reference[0]),
                    reading2 = get_bible_passage(readings_reference[1]),
                    reading3 = get_bible_passage(readings_reference[2]),
                    psalms = get_psalms(psalm_reference))

class UpdatePrayer(BaseHandler):
    def get(self):
        todays_readings = get_todays_readings(True)
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
