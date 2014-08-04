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

app     = Flask(__name__)
prefix  = 'orderbot'
exptime = 60*60*24*2 # Two days
db      = redis.StrictRedis()
special_user_orders = {}   #orders which don't match regular restaurants and are pending classification


with open('restaurantList.txt') as f:
    restaurants = json.load(f)

restaurants = [[r.lower() for r in rest] for rest in restaurants] # Convert to lowercase

def payload(text): return {"channel": "#seamless-thursday", "username": "OrderBot", "text": text, "icon_emoji": ":seamless:"}

@app.route('/', methods=['POST'])
def save_order():
    post  = request.form['text'].lower().strip()
    user  = request.form['user_name']
    order = re.match(r'%s\s*?:(.+?):(.+)' % prefix, post)

    if re.match(r'%s[,.:\- ;]help' % prefix, post):
        return post_message('Order with this format: ```orderBot: restaurant: order```.  For example, ```orderBot: Mizu: Lunch Special, Spicy Tuna Roll, Yellowtail Roll, Salmon Roll, special instructions "Label Jim, extra spicy"'

    elif order:
        restaurant = order.group(1).strip()
        entree     = order.group(2).strip()
        for r in restaurants:
            if restaurant in r:
                db.rpush('orders:%s' % r[0], '%s: %s' % (user, entree))
                db.expire('orders:%s' % r[0], exptime)
                return post_message("%s your order to %s was added successfully" % (user, r[0]))

        special_user_orders[user] = (restaurant, entree)
        return post_message("%s, %s is not one of our usual restaurants.  Should we save your order in the \"Miscellaneous Restaurant\" list? Yes/No" % (user, restaurant))
    return ""

def post_message(message):
    return json.dumps(payload(message))

if __name__ == '__main__':
    args = Schema({'--host': Use(str), '--port': Use(int), '--debug': Use(bool)}).validate(docopt(__doc__))
    app.run(host=args['--host'], port=args['--port'], debug=args['--debug'])
