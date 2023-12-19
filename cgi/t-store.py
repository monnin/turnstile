# apt install python3-flask

"""
t-store - "Internet-facing side" front-end to transferring files via the web (and via Turnstile)
"""

import flask
import werkzeug

import datetime
import random
import os
import time
import re
import urllib
import pam

XFER_DIR = "/nfs/xfer-data/active"
XFER_LOG_DIR = "/nfs/xfer-data/log"

URL_SIZE  = 5

# https://stackoverflow.com/questions/29773528/python-requests-isnt-giving-me-the-same-html-as-my-browser-is
# Fake a Chrome Browser
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.77 Safari/537.36"


app = flask.Flask(__name__)
app.debug = False

def load_key():
    # Use something like this to create a key
    #    openssl rand -base64 30 > .randkey
    # or pwgen 30 1 > .randkey

    f = open("/home/xfer/.randkey")
    app.secret_key = f.readline()
    f.close()

#
#    Use secure_filename to remove extra "unsafe" characters, but
#    first remove any possible directories
#

def sanitize_filename(filename, defaultname="transferred.file"):
    """ create a safe destination filename (without any directories) """

    # Remove any directories
    if "/" in filename:
        filename = filename.split("/")[-1]

    if "\\" in filename:
        filename = filename.split("\\")[-1]

    filename = werkzeug.utils.secure_filename(filename)

    if (filename is None) or (filename == ""):
        filename = defaultname

    return filename

#
#----------------------------------------------------------------------
#
def logit(user,mesg):
    now = str(datetime.datetime.now())

    try:
        addr = flask.request.access_route[-1]
    except RuntimeError:
        addr = "<unknown>"

    f = open(XFER_LOG_DIR + "/access.log","a")

    s = " ".join([now,addr,user,mesg])

    f.write(s + "\n")

    f.close()


#
#--------------------------------------------------------------
#
# save_meta - keep a "one-stop" single file with all of the metadata about the
#            transfer (including things like "code" and "filename" that
#            can be inferred)
#
def save_meta(code,sourcename,destname,method):
    email = flask.session["username"]

    f = open(os.path.join(XFER_DIR,code,".meta"), "w")

    f.write("Time:     " + str(datetime.datetime.now()) + "\n")
    f.write("Who:      " + email + "\n")
    f.write("From:     " + sourcename + "\n")
    f.write("Method:   " + method + "\n")
    f.write("ID:       " + code + "\n")
    f.write("Dst Name: " + destname + "\n")
    f.close()

    logit(email,"created folder " + code +
          " from '" + sourcename + "' to '" + destname + "' via " +
          method)

#
#----------------------------------------------------------------------
#
def create_rand_dir():
    ok = False

    # Try randomly created directories until finding one that doesn't exist
    while (not ok):
        num = random.randint(1,10**URL_SIZE)
        code = str(num).zfill(URL_SIZE)
        new_dir = os.path.join(XFER_DIR, code)

        if not os.path.isdir(new_dir):
            try:
                os.mkdir(new_dir)
                ok = True

            except OSError as e:
                ok = False

        if not ok:
            # Make sure that too many files doesn't peg the CPU
            time.sleep(0.5)       

    return (code, new_dir)

#
#----------------------------------------------------------------------
#
def check_login():
    if "username" not in flask.session:
        return flask.redirect(flask.url_for('login'))

    return None
#
#----------------------------------------------------------------------
#

def success_page(code, datatype):
    return flask.render_template('success.html',
            code=code, datatype=datatype,
            indexurl=flask.url_for('index'))   


def save_headers(code, headerdata):
    f = open(os.path.join(XFER_DIR, code, ".headers"), "w")
    for (key,val) in headerdata.items():
        f.write(key + ": " + val + "\n")
    f.close()

#
#----------------------------------------------------------------------
#
@app.route("/xfer/textupload", methods=["POST"])
def textupload():
    s = check_login()
    if s is not None: return s

    (code, new_dir) = create_rand_dir()

    text = flask.request.form["sourcetext"]
   
    numlines = len(text.split())

    f = open(os.path.join(new_dir, "input.txt"), "w")
    f.write(text)
    f.close()

    save_meta(code,"n/a","input.txt","textbox")
    save_headers(code, { 'Content-Type': 'text/plain' } )

    return success_page(code, "text")


@app.route("/xfer/urlupload", methods=["POST"])
def urlupload():
    s = check_login()
    if s is not None: return s

    url = flask.request.form["urlname"]

    headers = {}
   
    req = urllib.request.Request(url, None, headers)

    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Accept", "text/html,application/xhtml+xml;q=0.8,application/xml;q=0.8,*/*;q=0.7")
    req.add_header("Accept-Language", "en-US,en;q=0.8,*;q=0.1")

    r = urllib.request.urlopen(req)

    if (r.status >= 200) and (r.status <= 299):
        (code, new_dir) = create_rand_dir()

        content = r.read()

        # Get the final name (if different because of redirects)

        url = r.url
        # Get only the last part of the URL
        new_name = url.rsplit("/",1)[-1]

        # Now ignore any GET options
        new_name = new_name.split("?",1)[0]

        # https://stackoverflow.com/questions/31804799/how-to-get-pdf-filename-with-python-requests

        # Look for a better filename
        if 'Content-Disposition' in r.headers:
            dispo = r.headers['Content-Disposition']

            print("Found disposition", dispo)
            alt_name = re.findall("filename=(.+)", disp)[0]

            if alt_name is not None:
                new_name = sanitize_filename(alt_name)

        f = open(os.path.join(new_dir, new_name), "wb")
        f.write(content)
        f.close()
       
        save_headers(code, r.headers)
        save_meta(code,url,new_name,"web url")

        return success_page(code, "url")

    else:
        return flask.render_template('urlfailed.html',
            url=url,
            reason=str(r.status_code) + "\n" + "\n" + r.text,
            indexurl=flask.url_for('index'))

@app.route("/xfer/fileupload", methods=["POST"])
def fileupload():
    s = check_login()

    if s is not None:
        return s

    if 'file' in flask.request.files:

        rfile = flask.request.files['file']

        (code, new_dir) = create_rand_dir()

        new_name = sanitize_filename(rfile.filename)
        new_name = os.path.join(new_dir, new_name)
   
        rfile.save(new_name)

        save_meta(code,rfile.filename,new_name,"file upload")
        save_headers(code, { 'Content-Type': 'application/octet-stream' } )

        return success_page(code, "file")
    else:
        print("files['file'] - Not found")
        print(dict(flask.request.files))

        return flask.render_template('filefailed.html',
            indexurl=flask.url_for('index'))

#
#----------------------------------------------------------------------
#

#
@app.route('/xfer')
def index():
    s = check_login()
    if s is not None: return s

    logit("<unknown>", "User accessing main page")

    return flask.render_template('index.html',
                user=flask.session["username"],
                logouturl=flask.url_for("logout"),
                urlupload=flask.url_for("urlupload"),
                textupload=flask.url_for("textupload"),
                fileupload=flask.url_for("fileupload"))
#
#----------------------------------------------------------------------
#

# https://stackoverflow.com/questions/26313894/flask-login-using-linux-system-credentials
@app.route('/xfer/login', methods=['GET', 'POST'])
def login():

    if flask.request.method == "POST":
        user   = flask.request.form["username"]
        passwd = flask.request.form["password"]

        p = pam.pam()

        if p.authenticate(user,passwd):
            logit(user, "Logged in via PAM")
            flask.session["username"] = user

            return flask.redirect(flask.url_for("index"))

        else:
            logit(user, "Login attempt failed in via PAM, code=" +
                  str(p.code) + ", reason=" + p.reason)

            return flask.render_template('login.html',
                     user=user, mesg="Login failed")
       

    else:
        logit("<unknown>", "Logging in via PAM")
        return flask.render_template('login.html', user="", mesg="")


@app.route('/xfer/logout')
def logout():
    if "username" in flask.session:
        who = flask.session["username"]
    else:
        who = "<unknown>"

    logit(who,"Logging out")

    flask.session.pop('username', None)

    return flask.redirect(flask.url_for('index'))


@app.route('/')
def mainpage():
    return flask.redirect(flask.url_for('index'))

#
#----------------------------------------------------------------------
#

load_key()
if __name__ == '__main__':
    app.run(host='0.0.0.0',ssl_context='adhoc')
