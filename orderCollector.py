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
from datetime import datetime, timedelta

app     = Flask(__name__)
prefix  = 'orderbot'
db      = redis.StrictRedis()
special_user_orders = {}   #orders which don't match regular restaurants and are pending classification
administrative_users = ['stephanie.musal', 'ldonaghy', 'dseminara', 'tim']

with open('restaurantList.txt') as f:
    restaurants = json.load(f)

restaurants = [[r.lower() for r in rest] for rest in restaurants] # Convert to lowercase

def payload(text): return {"channel": "#seamless-thursday", "username": "OrderBot", "text": text, "icon_emoji": ":seamless:", 'link_names': 1}
def snippet_payload(attachment): return {"channel": "#seamless-thursday", "username": "OrderBot", "icon_emoji": ":seamless:", "attachments": [
      {
         "fallback":"New open task [Urgent]: <http://url_to_task|Test out Slack message attachments>",
         "pretext":"New open task [Urgent]: <http://url_to_task|Test out Slack message attachments>",
         "color":"#D00000",
         "fields":[
            {
               "title":"Notes",
               "value":"This is much easier than I thought it would be.",
               "short": False
            }
         ]
      }
   ], 'link_names': 1}

def add_order(user, restaurant, entree):
    # check for existence here?
    resthash = 'orders:%s' % restaurant
    userhash = 'orderbot:users:%s' % user
    d = datetime.now()
    db.hset(resthash, user, entree)
    db.set(userhash, resthash)
    exptime = int((datetime(d.year, d.month, d.day) + timedelta(1) - d).total_seconds())
    db.expire(resthash, exptime)
    db.expire(userhash, exptime)
    
def list_orders(restaurant):
    if restaurant == "all":
        pass
        #return all orders
    else:
        pass
        #return restaurant specific orders
        #orders = db.get(restaurant);

@app.route('/', methods=['POST'])
def save_order():
    post  = request.form['text'].lower().strip()
    user  = request.form['user_name']
    order = re.match(r'%s\s*?:(.+?):(.+)' % prefix, post)
    
    if user in special_user_orders:
        if post == "yes" or post == "y":
            add_order(user, "miscellaneous", ": ".join(special_user_orders[user]))
            temp = special_user_orders[user][0]
            del special_user_orders[user]
            return post_message("Great! @%s,  I'll add your order to %s under the category of miscellaneous restuarants" % (user, temp))
        elif post == "no" or post == "n":
            del special_user_orders[user]
            return post_message("Okay @%s, I won't add your order. Feel free to place a new one." % user)
        else:
            return post_message("I'm sorry @%s, I don't understand.  Do you want to add your order of `%s` to the miscellaneous restaurant `%s`?  Please answer yes or no." % (user, special_user_orders[user][1], special_user_orders[user][0]))
    
        
    elif re.match(r'%s[,.:\- ;]help' % prefix, post):
        return json.dumps(snippet_payload())
        #return post_message('Order with this format: `orderBot: restaurant: order` For example: `orderBot: Mizu: Lunch Special, Spicy Tuna Roll, Yellowtail Roll, Salmon Roll, special instructions "Label Jim, extra spicy"`')

    elif order:
        r = order.group(1).strip() # restaurant
        e = order.group(2).strip() # entree
        for restaurant in restaurants:
            if r in restaurant:
                add_order(user, restaurant[0], e)
                return post_message("@%s, your order to %s was added successfully" % (user, restaurant[0]))

        special_user_orders[user] = (r, e)
        return post_message('@%s, %s is not one of our usual restaurants.  Should we save your order in the "Miscellaneous Restaurant" list? Yes/No' % (user, r))
    
    elif user in administrative_users:
        #add list_orders logic
        pass

    return ""
def post_message(message):
    return json.dumps(payload(message))

if __name__ == '__main__':
    args = Schema({'--host': Use(str), '--port': Use(int), '--debug': Use(bool)}).validate(docopt(__doc__))
    app.run(host=args['--host'], port=args['--port'], debug=args['--debug'])
