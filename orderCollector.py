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

app                  = Flask(__name__)
prefix               = 'orderbot'
db                   = redis.StrictRedis()
no_restaurant_found  = {}
previous_order_found = {}
administrative_users = set(['stephanie.musal', 'ldonaghy', 'dseminara', 'tim'])
postURL              = 'https://slack.com/api/files.upload'

with open('token.txt') as t:
    token = t.read()
    
with open('restaurantList.txt') as f:
    restaurants = [[r.lower() for r in rest] for rest in json.load(f)] # Convert to lowercase

def payload(text): return {"channel": "#seamless-thursday", "username": "OrderBot", "text": text, "icon_emoji": ":seamless:", 'link_names': 1}
def order_list(filename, table): return {"token": token, "filename" : filename, "title": filename, "content": str(table), "channels": ["#seamless-thursday"]}
        
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
            previous_order_found[user] = (restaurant, entree)
            return post_message("@%s you have previously placed an order today.  Would you like to replace that order? Yes/No" % (user))
    d = datetime.now()
    db.hset(resthash, user, entree)
    db.set(userhash, restaurant)
    exptime = datetime(d.year, d.month, d.day) + timedelta(1)
    db.expireat(resthash, exptime)
    db.expireat(userhash, exptime)
    return post_message("@%s, your order to %s was added successfully" % (user, restaurant))
    
def list_orders(restaurant):
    if restaurant == "all":
        pass
        #return all orders
    else:
        pass
        #return restaurant specific orders
        #orders = db.get(restaurant);
        
def parse_order(user, order):
    r = order.group(1).strip() # restaurant
    e = order.group(2).strip() # entree
    for restaurant in restaurants:
        if r in restaurant:
            return add_order(user, restaurant[0], e)

    no_restaurant_found[user] = (r, e)
    return post_message('@%s, %s is not one of our usual restaurants.  Should we save your order in the "Miscellaneous Restaurant" list? Yes/No' % (user, r))

@app.route('/', methods=['POST'])
def save_order():
    post     = request.form['text'].lower().strip()
    user     = request.form['user_name']
    order    = re.match(r'%s\s*?:(.+?):(.+)' % prefix, post)
    response = ""
    
    
    if post in ["orderbot ?", "orderbot?", "orderbot: ?"]:
        if db.exists(hash_user(user)):
            curr_rest = db.get(hash_user(user))
            curr_order = db.hget(hash_restaurant(curr_rest), user)
            if curr_rest == "miscellaneous":
                [curr_rest, curr_order] = [x.strip() for x in curr_order.split(':', 1)]
            response = post_message("@%s your current order is `%s` from `%s`" % (user, curr_order, curr_rest))
        else:
            response = post_message("@%s, you have not yet ordered today" % user)
    elif user in no_restaurant_found:
        if post in ["yes","y"]:
            response = add_order(user, "miscellaneous", ": ".join(no_restaurant_found[user]))
            del no_restaurant_found[user]
        elif post in ["no","n"]:
            response = post_message("Okay @%s, I won't add your order. Feel free to place a new one." % user)
            del no_restaurant_found[user]
        else:
            response = post_message("I'm sorry @%s, I don't understand.  Do you want to add your order of `%s` to the miscellaneous restaurant `%s`?  Please answer yes (y) or no (n)." % (user, no_restaurant_found[user][1], no_restaurant_found[user][0]))
    elif user in previous_order_found:
        if post in ["yes","y"]:
            response = add_order(user, *previous_order_found[user], overwrite=True)
            del previous_order_found[user]
        elif post in ["no","n"]:
            response = post_message("Okay @%s, I won't overwrite your order. Feel free to place a new one." % user)
            del previous_order_found[user]
        else:
            response = post_message("I'm sorry @%s, I don't understand.  Do you want to change your order to %s?  Please answer yes (y) or no (n)." % (user, ': '.join(previous_order_found[user])))
    elif re.match(r'%s[,.:\- ;]help' % prefix, post):
        return post_message('Order with this format: `orderBot: restaurant: order` For example: `orderBot: Mizu: Lunch Special, Spicy Tuna Roll, Yellowtail Roll, Salmon Roll, special instructions "Label Jim, extra spicy"`.  To see if/what you have ordered, simply type `orderBot: ?`')
    elif order:
        response = parse_order(user, order)
    
    elif user in administrative_users:
        #orderbot, list orders from [restaurant]
        #orderbot, list all orders
        pattern = re.match(r'%s,? list all orders\s*?(?:from)?(.*)' % prefix, post)
        
        if pattern:
            table = PrettyTable(["Name", "Restaurant", "Order"])
            table.align["Name"] = 'l'
            table.align["Restaurant"] = 'l'
            table.align["Order"] = 'l'
            
            rest = pattern.group(1).strip()
            if rest:
                filename = rest + ".txt"
                resthash = hash_restaurant(rest)
                order_hash = db.hgetall(resthash)
                for name, order in order_hash.iteritems():
                    x.add_row((name, rest, order))
            else:
                keys = db.keys("orders:*")
                filename = "All Orders.txt"
                for resthash in keys:
                    rest = resthash[7:]
                    order_hash = db.hgetall(resthash)
                    for name, order in order_hash.iteritems():
                        table.add_row((name, rest, order))
            
            requests.post(postURL, data=json.dumps(order_list(filename, table)))
            response = post_message("Please check the uploaded file in the sidebar of this channel for the order list!")
            
        
    return response
    
def post_message(message):
    return json.dumps(payload(message))

if __name__ == '__main__':
    args = Schema({'--host': Use(str), '--port': Use(int), '--debug': Use(bool)}).validate(docopt(__doc__))
    app.run(host=args['--host'], port=args['--port'], debug=args['--debug'])
