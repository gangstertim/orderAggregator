#!/usr/bin/python

'''

Usage: orderCollector.py [--debug] [-p <port>] [-H <host>]

Options:
  -p, --port=<port>    The port number on which to run Flask [default: 5000]
  -H, --host=<host>    The host to listen to [default: 127.0.0.1]
  --debug              Flag to determine debug mode [default: False]

'''

import re, json, redis, requests
from docopt import docopt
from schema import Use, Schema
from flask import Flask, request
from prettytable import PrettyTable
from datetime import datetime, timedelta

def payload(text): return {"channel": "#seamless-thursday",
                           "username": "OrderBot", "text": text,
                           "icon_emoji": ":seamless:", 'link_names': 1}
def post_message(message):
    if message:
        return json.dumps(payload(message))
    return message
def hash_restaurant(r): return 'orders:%s' % r
def hash_user(u): return 'orderbot:users:%s' % u

def add_order(user, restaurant, entree, overwrite=False):
    resthash = hash_restaurant(restaurant)
    userhash = hash_user(user)
    if db.exists(userhash):
        # user already placed order
        if overwrite:
            db.hdel(db.get(userhash), user)
        else:
            r = db.get(userhash)
            previous_order_found[user] = (restaurant, entree)
            return post_message("@%s you have previously placed an order to %s today.  Would you like to replace that order? Please reply yes (y) or no (n)." % (user, r))
    d = datetime.now()
    db.hset(resthash, user, entree)
    db.set(userhash, restaurant)
    exptime = datetime(d.year, d.month, d.day) + timedelta(1)
    db.expireat(resthash, exptime)
    db.expireat(userhash, exptime)
    return "@%s, your order to %s was added successfully" % (user, restaurant)
    
class Command(object):
    prefix = 'orderbot'
    def __init__(self, command):
        self.command = command
    def __eq__(self, other):
        if isinstance(other, Command):
            return self.command == other.command
        elif isinstance(other, list):
            return bool(len(other) > 1 and Command.prefix == other[0]
                        and re.match(self.command, other[1], flags=re.I))
        else:
            return False
    def __str__(self):
        return self.command

class OrderAdd(Command):
    def __init__(self):
        super(OrderAdd, self).__init__(r"add")
    def __call__(self, user, post):
        if user in no_restaurant_found:
            return '@%s, you cannot add an order until you confirm whether or not you would like to add your previous order of %s to the miscellaneous category.  Please reply yes (y) or no (n).' % (user, ': '.join(no_restaurant_found[user]))
        elif user in previous_order_found:
            return '@%s, you cannot add an order until you confirm whether or not you would like to replace your previous with %s.  Please reply yes (y) or no (n).' % (user, ': '.join(previous_order_found[user]))
        [rest, entree] = [s.strip() for s in post[2].split(':', 1)]
        if not rest in restaurants:
            no_restaurant_found[user] = (rest, entree)
            return '@%s, %s is not one of our usual restaurants.  Should we save your order in the "Miscellaneous Restaurant" list? Yes/No' % (user, rest)
        return add_order(user, restaurants[rest], entree)

class OrderList(Command):
    def __init__(self):
        super(OrderList, self).__init__(r"list")
    def __call__(self, user, post):
        if user in administrative_users:
            rest = post[2]
            table = PrettyTable(["Name", "Restaurant", "Order"])
            table.align["Name"] = 'l'
            table.align["Restaurant"] = 'l'
            table.align["Order"] = 'l'

            if rest == 'all':
                keys = db.keys('orders:*')
                title = 'All Orders'
                for resthash in keys:
                    rest = resthash[7:]
                    order_hash = db.hgetall(resthash)
                    for name, order in order_hash.iteritems():
                        table.add_row((name, rest, order))
                return "*%s*\n```%s```" % (title, str(table))
            else:
                if rest in restaurants:
                    rest = restaurants[rest]
                    title = rest
                    resthash = hash_restaurant(rest)
                    order_hash = db.hgetall(resthash)
                    for name, order in order_hash.iteritems():
                        table.add_row((name, rest, order))
                    return "*%s*\n```%s```" % (title, str(table))
            
            return "Nobody has ordered from a restaurant called %s" % rest
        return ""

class OrderStatus(Command):
    def __init__(self):
        super(OrderStatus, self).__init__(r"status")
    def __call__(self, user, post):
        if db.exists(hash_user(user)):
            curr_rest = db.get(hash_user(user))
            curr_order = db.hget(hash_restaurant(curr_rest), user)
            if curr_rest == "miscellaneous":
                [curr_rest, curr_order] = [x.strip() for x in curr_order.split(':', 1)]
            return "@%s your current order is `%s` from `%s`" % (user, curr_order, curr_rest)
        else:
            return "@%s, you have not yet ordered today" % user

class OrderHelp(Command):
    def __init__(self):
        super(OrderHelp, self).__init__(r"help|\?")
    def __call__(self, user, post):
        return 'Order with this format: `orderBot: add: restaurant: order`. For example: `orderBot: add: Mizu: Lunch Special, Spicy Tuna Roll, Yellowtail Roll, Salmon Roll, special instructions "Label Jim, extra spicy"`.  To see if/what you have ordered, simply type `orderBot: status`'

class OrderConfirm(Command):
    def __init__(self):
        super(OrderConfirm, self).__init__(r"yes|y|no|n")
    def __eq__(self, other):
        if isinstance(other, list):
            return bool(len(other) == 1 and re.match(self.command, other[0], flags=re.I))
        else:
            return super(OrderConfirm, self).__eq__(other)
    def __call__(self, user, post):
        reply = post[0]
        if reply in ['yes','y']:
            if user in no_restaurant_found:
                r = add_order(user, 'miscellaneous', ': '.join(previous_order_found[user]))
                del no_restaurant_found[user]
                return r
            elif user in previous_order_found:
                r = add_order(user, *previous_order_found[user], overwrite=True)
                del previous_order_found[user]
                return r
        elif reply in ['no','n']:
            if user in no_restaurant_found:
                del no_restaurant_found[user]
                return "Okay @%s, I won't add your order. Feel free to place a new one." % user
            elif user in previous_order_found:
                del previous_order_found[user]
                return "Okay @%s, I won't overwrite your order. Feel free to place a new one." % user
        return ""


app                  = Flask(__name__)
db                   = redis.StrictRedis()
commands             = [OrderStatus(), OrderList(), OrderConfirm(), OrderHelp(), OrderAdd()]
no_restaurant_found  = {}
previous_order_found = {}
administrative_users = frozenset(['stephanie.musal', 'ldonaghy', 'dseminara', 'tim'])

with open('restaurantList.txt') as f:
    restaurants = dict((r.lower(), rest[0].lower()) for rest in json.load(f) for r in rest)        

@app.route('/', methods=['POST'])
def main():
    post = [s.strip() for s in request.form['text'].lower().strip().split(':', 2)]
    user = request.form['user_name']
    response = ""
    try:
        i = commands.index(post)
    except ValueError:
        pass
    else:
        response = post_message(commands[i](user, post))
        
    return response
    
if __name__ == '__main__':
    args = Schema({'--host': Use(str), '--port': Use(int), '--debug': Use(bool)}).validate(docopt(__doc__))
    app.run(host=args['--host'], port=args['--port'], debug=args['--debug'])