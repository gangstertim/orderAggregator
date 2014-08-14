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
from prettytable import PrettyTable
from datetime import datetime, timedelta

with open('restaurantList.txt') as f:
    restaurants = dict((r.lower(), rest[0].lower()) for rest in json.load(f) for r in rest)

app = Flask(__name__)
db  = redis.StrictRedis()
    
class OrderBot(object):
    def __init__(self):
        self.bot_prefix           = 'orderbot'
        self.rest_prefix          = '%s:orders:' % self.bot_prefix
        self.user_prefix          = '%s:users:' % self.bot_prefix
        self.administrative_users = db.smembers('%s:admins' % self.bot_prefix)
        self.no_restaurant_found  = {}
        self.previous_order_found = {}
        self.fmap = {
            'add'   : self.orderadd,
            'list'  : self.orderlist,
            'status': self.orderstatus,
            'help'  : self.orderhelp,
            '?'     : self.orderhelp
        }
        self.fmap2 = {
            'yes'   : self.orderconfirm,
            'y'     : self.orderconfirm,
            'no'    : self.orderdeny,
            'n'     : self.orderdeny
        }

    def __call__(self, user, post):
        if len(post) > 1 and re.match(r'@?%s' % self.bot_prefix, post[0]) and post[1] in self.fmap:
            return self.fmap[post[1]](user, post)
        elif len(post) == 1 and post[0] in self.fmap2:
            return self.fmap2[post[0]](user)
        return ""

    def hash_restaurant(self, r): return self.rest_prefix + r

    def hash_user(self, u): return self.user_prefix + u

    def add_order(self, user, restaurant, entree, overwrite=False):
        resthash = self.hash_restaurant(restaurant)
        userhash = self.hash_user(user)
        if db.exists(userhash):
            # user already placed order
            if overwrite:
                db.hdel(self.hash_restaurant(db.get(userhash)), user)
            else:
                r = db.get(userhash)
                self.previous_order_found[user] = (restaurant, entree)
                return "@%s you have previously placed an order to %s today.  Would you like to replace that order? Please reply yes (y) or no (n)." % (user, r)
        d = datetime.now()
        db.hset(resthash, user, entree)
        db.set(userhash, restaurant)
        exptime = datetime(d.year, d.month, d.day) + timedelta(1)
        db.expireat(resthash, exptime)
        db.expireat(userhash, exptime)
        return "@%s, your order to %s was added successfully" % (user, restaurant)
    
    def orderadd(self, user, post):
        if user in self.no_restaurant_found:
            return '@%s, you cannot add an order until you confirm whether or not you would like to add your previous order of %s to the miscellaneous category.  Please reply yes (y) or no (n).' % (user, ': '.join(self.no_restaurant_found[user]))
        elif user in self.previous_order_found:
            return '@%s, you cannot add an order until you confirm whether or not you would like to replace your previous with %s.  Please reply yes (y) or no (n).' % (user, ': '.join(self.previous_order_found[user]))
        try:
            [rest, entree] = [s.strip() for s in post[2].split(':', 1)]
        except ValueError:
            return ""
        if not rest in restaurants:
            self.no_restaurant_found[user] = (rest, entree)
            return '@%s, %s is not one of our usual restaurants.  Should we save your order in the "Miscellaneous Restaurant" list? Yes/No' % (user, rest)
        return self.add_order(user, restaurants[rest], entree)

    def orderlist(self, user, post):
        if user in self.administrative_users:
            rest = post[2]
            table = PrettyTable(["Name", "Restaurant", "Order"])
            table.align["Name"] = 'l'
            table.align["Restaurant"] = 'l'
            table.align["Order"] = 'l'

            if rest == 'all':
                keys = db.keys(self.rest_prefix + '*')
                title = 'All Orders'
                for resthash in keys:
                    rest = resthash.replace(self.rest_prefix, "", 1)
                    order_hash = db.hgetall(resthash)
                    for name, order in order_hash.iteritems():
                        table.add_row((name, rest, order))
                return "*%s*\n```%s```" % (title, str(table))
            else:
                if rest in restaurants:
                    rest = restaurants[rest]
                    title = rest
                    resthash = self.hash_restaurant(rest)
                    order_hash = db.hgetall(resthash)
                    for name, order in order_hash.iteritems():
                        table.add_row((name, rest, order))
                    return "*%s*\n```%s```" % (title, str(table))
            
            return "Nobody has ordered from a restaurant called %s" % rest
        return ""

    def orderstatus(self, user, post):
        if db.exists(self.hash_user(user)):
            curr_rest = db.get(self.hash_user(user))
            curr_order = db.hget(self.hash_restaurant(curr_rest), user)
            if curr_rest == "miscellaneous":
                [curr_rest, curr_order] = [x.strip() for x in curr_order.split(':', 1)]
            return "@%s your current order is `%s` from `%s`" % (user, curr_order, curr_rest)
        else:
            return "@%s, you have not yet ordered today" % user

    def orderhelp(self, user, post):
        helptext = 'Order with this format: `orderBot: add: restaurant: order`. For example: `orderBot: add: Mizu: Lunch Special, Spicy Tuna Roll, Yellowtail Roll, Salmon Roll, special instructions "Label Jim, extra spicy"`.  To see if/what you have ordered, simply type `orderBot: status`.'
        if user in self.administrative_users:
            helptext += '  To view all orders placed to a specific restaurant, type `orderBot: list: restaurantname` or `orderBot: list: all` to see all orders that have been placed.'
        return helptext

    def orderconfirm(self, user):
        if user in self.previous_order_found:
            r = self.add_order(user, *self.previous_order_found[user], overwrite=True)
            del self.previous_order_found[user]
            return r
        elif user in self.no_restaurant_found:
            r = self.add_order(user, 'miscellaneous', ': '.join(self.no_restaurant_found[user]))
            del self.no_restaurant_found[user]
            return r
        return ""
        
    def orderdeny(self, user):
        if user in self.previous_order_found:
            del self.previous_order_found[user]
            return "Okay @%s, I won't overwrite your order. Feel free to place a new one." % user
        elif user in self.no_restaurant_found:
            del self.no_restaurant_found[user]
            return "Okay @%s, I won't add your order. Feel free to place a new one." % user
        return ""

def payload(text): return {"channel": "#seamless-thursday",
                           "username": "OrderBot", "text": text,
                           "icon_emoji": ":fatbot:", 'link_names': 1}
def post_message(message):
    if message:
        return json.dumps(payload(message))
    return message

@app.route('/', methods=['POST'])
def main():
    post = [s.strip() for s in request.form['text'].lower().strip().split(':', 2)]
    user = request.form['user_name']
    return post_message(orderbot(user, post))
    
if __name__ == '__main__':
    orderbot = OrderBot()
    args = Schema({'--host': Use(str), '--port': Use(int), '--debug': Use(bool)}).validate(docopt(__doc__))
    app.run(host=args['--host'], port=args['--port'], debug=args['--debug'])