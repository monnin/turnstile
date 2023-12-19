# apt install python3-flask

"""
t-retrieve - "Isolated-cluster side" front-end to transferring files via the web (and via Turnstile)
"""


import flask

import datetime
import os
import sys
import time

sys.path.append(os.path.dirname(os.path.realpath(__file__)) + "/../lib")

import usbUDP
import usb_comm

XFER_DIR = "/xfer-data"
URL_SIZE  = 5
XFER_LOG = os.path.dirname(os.path.realpath(__file__)) + \
        "/../var/log/access.log"

my_client = None


app = flask.Flask(__name__)
app.debug = True

def logit(user,mesg):
    now = str(datetime.datetime.now())

    try:
        addr = flask.request.access_route[-1]
    except RuntimeError:
        addr = "<unknown>"

    f = open(XFER_LOG, "a")

    s = " ".join([now,addr,user,mesg])

    f.write(s + "\n")

    f.close()




#
#--------------------------------------------------------------
#
def get_filename(code):
    setup_turnstile_client()

    filename = None

    directory = XFER_DIR + "/" + code
    files = my_client.client_ls(directory)

    if files is not None:
        # Find the first filename that does not begin with a period (".")
        for one_file in files:
            if (filename is None) and (one_file[0] != "."):
                filename = one_file

    if filename is not None:
        filename = directory + "/" + filename

    return filename

#
#   Retrieve the contents of a .headers file
#   (which will be in lines with a key:val format)
#
def get_headers(code, filename=".headers"):
    setup_turnstile_client()

    headers = {}

    # Make sure there is at least the content type
    headers['Content-Type'] = 'application/octet-stream'

    fullpath = os.path.join(XFER_DIR,code,filename)
    content = my_client.client_get_file(fullpath)

    if content is not None:
        content = content.decode()

        for line in content.split("\n"):
            # Ignore the empty (last) line
            if line != "":
                (key,val) = line.split(":",1)

                val = val.strip()
                key = key.strip()

                headers[key] = val

    return headers

#
#----------------------------------------------------------------------
#
def retrieve_code(code):
    if code.isnumeric():
        code = code.zfill(URL_SIZE)

    filename = get_filename(code)

    if filename is None:
        return flask.render_template('retrieve.html',
                extratext="Code '" + code + "'not found")

    else:
        headers = get_headers(code)

        headers["Content-Disposition"] = "inline; filename=\"" + \
                    os.path.basename(filename) + "\""

        if "Content-Length" not in headers:
            file_stat = my_client.client_stat_path(filename)

            if file_stat is not None:
                headers['Content-Length'] = file_stat[2]  # Size

        #meta    = get_headers(code,".meta")

        return flask.Response(
                        my_client.client_get_file_yield(filename, as_bytes=True),
                        headers=headers)

#
@app.route('/r/<code>')
@app.route('/r/<code>/')
def retrieve(code):
    setup_turnstile_client()

    if my_client is not None:
        resp = retrieve_code(code)

    else:
        resp = flask.render_template('retrieve.html',
                extratext="No response from the server, please try again later")

    return resp


#
#----------------------------------------------------------------------
#
@app.route('/r', methods=["GET", "POST"])
def index():
    if flask.request.method == "POST":
        if "code" in flask.request.form:
            return retrieve( flask.request.form["code"] )
        else:
            return flask.render_template('retrieve.html')
    else:
        return flask.render_template('retrieve.html')


@app.route('/')
def mainpage():
    return flask.redirect(flask.url_for('index'))

#
#----------------------------------------------------------------------
#
def setup_turnstile_client():
    global my_client

    # Only setup the connection once
    if my_client is None:
        # Create a (connectionless) connection to the relay
        my_client = usb_comm.Client(usbUDP.usbUDP(), 30)

    # Now see if the server is alive
    if my_client.client_verify_server() is None:
        my_client = None

#
#----------------------------------------------------------------------
#


if __name__ == '__main__':
    app.run(host='0.0.0.0',ssl_context='adhoc', port=8880)
