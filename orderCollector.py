#!/usr/bin/python

'''

Usage: orderCollector.py [--debug] [-p <port>] [-H <host>]

Options:
  -p, --port=<port>    The port number on which to run Flask [default: 5000]
  -H, --host=<host>    The host to listen to [default: 127.0.0.1]
  --debug              Flag to determine debug mode [default: False]

'''

import re, json, redis
from docopt import docopt
from schema import Use, Schema
from flask import Flask, request

app = Flask(__name__)

prefix = 'orderbot'

def payload(text): return {"channel": "#seamless-thursday", "username": "OrderBot", "text": text, "icon_emoji": ":seamless:"}

db = redis.StrictRedis()

@app.route('/', methods=['POST'])
def save_order():
    post  = request.form['text'].lower().strip()
    user  = request.form['user_name']
    order = re.match(r'%s\s*?:(.+?):(.+)' % prefix, post)
    if order:
        order.group(1).strip() # restaurant
        order.group(2).strip() # entree
        return post_message("")
    return ""

def post_message(message):
    return json.dumps(payload(message))

if __name__ == '__main__':
    args = Schema({'--host': Use(str), '--port': Use(int), '--debug': Use(bool)}).validate(docopt(__doc__))
    app.run(host=args['--host'], port=args['--port'], debug=args['--debug'])
