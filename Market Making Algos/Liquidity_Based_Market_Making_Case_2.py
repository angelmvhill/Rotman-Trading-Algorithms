import os
import functools
import operator
import itertools
from time import sleep
import signal
import requests
import pandas as pd
#import pandas_ta as ta
import re
import json

# this class definition allows printing error messages and stopping the program
class ApiException(Exception):
    pass

# this signal handler allows for a graceful shutdown when CTRL+C is pressed
def signal_handler(signum, frame):
    global shutdown
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    shutdown = True

# set your API key to authenticate to the RIT client
API_KEY = {'X-API-Key': 'KZJ94OPT'}
shutdown = False

# this helper method returns the current 'tick' of the running case
def get_tick(session):
    resp = session.get('http://localhost:9999/v1/case')
    if resp.status_code == 401:
        raise ApiException('Error getting tick: The API key provided in this Python code must match that in the RIT client')
    case = resp.json()
    return case['tick']

# this helper method returns the last close price for the given security, one tick ago
def ticker_close(session, ticker):
    payload = {'ticker': ticker, 'limit': 1}
    resp = session.get('http://localhost:9999/v1/securities/history', params=payload)
    if resp.status_code == 401:
        raise ApiException('The API key provided in this Python code must match that in the RIT client (please refer to the API hyperlink in the client toolbar and/or the RIT – User Guide – REST API Documentation.pdf)')
    ticker_history = resp.json()
    if ticker_history:
        return ticker_history[0]['close']
    else:
        raise ApiException('Response error. Unexpected JSON response.')

def calc_spread_cushion(order_books_stats):
    bid_vol = order_books_stats['Cumulative Vol Bid']
    ask_vol = order_books_stats['Cumulative Vol Ask']

    reduction_factor = 20
    price_cushion_factor = (bid_vol - ask_vol) / ask_vol / reduction_factor

    return price_cushion_factor

# this function submits a buy order
def buy_order(session, ticker, quantity, price, price_cushion):
    buy_param = {'ticker': ticker, 'type': 'LIMIT', 'quantity': quantity, 'action': 'BUY', 'price': price + (price * price_cushion)}
    session.post('http://localhost:9999/v1/orders', params = buy_param)

# this function submits a sell order
def sell_order(session, ticker, quantity, price, price_cushion):
    buy_param = {'ticker': ticker, 'type': 'LIMIT', 'quantity': quantity, 'action': 'SELL', 'price': price + (price * price_cushion)}
    session.post('http://localhost:9999/v1/orders', params = buy_param)

# this function fetches the bid and ask prices of a given ticker
def ticker_bid_ask(session, ticker):
    payload = {'ticker': ticker}
    resp = session.get('http://localhost:9999/v1/securities/book', params=payload)
    if resp.ok:
        book = resp.json()
        return [book['bids'][0]['price'], book['asks'][0]['price']]
    raise ApiException('Error getting bid / ask: The API key provided in this Python code must match that in the RIT client') 

# this helper method gets all the orders of a given type (OPEN/TRANSACTED/CANCELLED)
def get_orders(session, status):
    payload = {'status': status}
    resp = session.get('http://localhost:9999/v1/orders', params=payload)
    if resp.status_code == 401:
        raise ApiException('The API key provided in this Python code must match that in the RIT client (please refer to the API hyperlink in the client toolbar and/or the RIT – User Guide – REST API Documentation.pdf)')
    orders = resp.json()
    return orders

# this function calculates a smooth moving average for n periods
def mov_avg(session, price):
    array = []
    array.append(price)

    sum = 0
    sma_period = 12

    for idx, i in reversed(list(enumerate(array))):
        if idx > len(array) - 13:
            sum += i

    mov_avg_num = sum/sma_period

    if len(array) > 12:
        del array[:-11]

    if len(array) > 12:
        del array[:-11]

    return mov_avg_num

# this function liquidates the entire portfolio
def liquidate_portfolio():
    pass

# this function fetches the position size for a given ticker
def get_position(session, ticker):
    positions = session.get('http://localhost:9999/v1/securities', params={'ticker': ticker})
    position = positions.json()[0]['position']
    return position

def get_order_book_stats(session, ticker, limit):

    orders = session.get('http://localhost:9999/v1/securities/book', params={'ticker': ticker, 'limit': limit})

    bids = orders.json()['bids']
    asks = orders.json()['asks']

    bid_cumulative_volume = 0
    bid_number_of_orders = 0

    ask_cumulative_volume = 0
    ask_number_of_orders = 0

    for i in bids:
        if i['trader_id'] == 'ANON':

            bid_cumulative_volume += 1
            bid_number_of_orders += i['quantity']

    for i in asks:
        if i['trader_id'] == 'ANON':

            ask_cumulative_volume += 1
            ask_number_of_orders += i['quantity']

    order_totals = {'Cumulative Vol Bid': bid_cumulative_volume,
            'Bid Num of Orders': bid_number_of_orders,
            'Cumulative Vol Ask': ask_cumulative_volume,
            'Ask Num of Orders': ask_number_of_orders,}

    bid_vol = order_totals['Cumulative Vol Bid']
    bid_order = order_totals['Bid Num of Orders']
    ask_vol = order_totals['Cumulative Vol Ask']
    ask_order = order_totals['Ask Num of Orders']
    return order_totals, bid_vol, bid_order, ask_vol, ask_order

# this is the main method containing the actual order routing logic
def main():

    with requests.Session() as s:
        # add the API key to the session to authenticate during requests
        s.headers.update(API_KEY)
        t = 'CNR'
        t1 = 'RY'
        t2 = 'AC'

        cnr_bid = ticker_bid_ask(s, t)
        cnr_bid = cnr_bid[0]
        cnr_ask = ticker_bid_ask(s, t)
        cnr_ask = cnr_ask[1]

        ry_bid = ticker_bid_ask(s, t)
        ry_bid = ry_bid[0]
        ry_ask = ticker_bid_ask(s, t)
        ry_ask = ry_ask[1]

        ac_bid = ticker_bid_ask(s, t)
        ac_bid = ac_bid[0]
        ac_ask = ticker_bid_ask(s, t)
        ac_ask = ac_ask[1]
        # get the current time of the case

        tick = get_tick(s)
       
        while 5 <= tick <= 300:
            tick = get_tick(s)
            orders = get_orders(s, 'OPEN')
            
            # fetch data via API to feed to algorithm
            
            resp = s.get('http://localhost:9999/v1/securities/book', params={'ticker': t, 'limit': 100})
            resp = s.get('http://localhost:9999/v1/securities/book', params={'ticker': t1, 'limit': 100})
            resp = s.get('http://localhost:9999/v1/securities/book', params={'ticker': t2, 'limit': 100})
            my_orders = 0
            
            lastorder = len(orders)
            close = ticker_close(s, t)
            close_1 = ticker_close(s, t1)
            close_2 = ticker_close(s, t2)
            sma = mov_avg(s, close)
            order_book_stats = get_order_book_stats(s, t, 100)
            order_book_stats_1 = get_order_book_stats(s, t1, 100)
            order_book_stats_2 = get_order_book_stats(s, t2, 100)
            
            bid_order = order_book_stats[1]
            bid_vol = order_book_stats[2]
            ask_vol = order_book_stats[4]
            ask_order = order_book_stats[3]

            bid_vol_1 = order_book_stats_1[2]
            ask_vol_1 = order_book_stats_1[4]

            bid_vol_2 = order_book_stats_2[2]
            ask_vol_2 = order_book_stats_2[4]

            algo_close = ticker_close(s, t)
            position = get_position(s, t)

            algo_close_1 = ticker_close(s, t1)
            position_1 = get_position(s, t1)
            
            algo_close_2 = ticker_close(s, t2)
            position_2 = get_position(s, t2)

            ask_bid_voldif = ask_vol - bid_vol
            ask_bid_voldif_1 = ask_vol_1 - bid_vol_1
            ask_bid_voldif_2 = ask_vol_2 - bid_vol_2

            print(ask_bid_voldif)
            bid_order_voldif = bid_vol - ask_vol

            if 15000 < ask_bid_voldif:
                spread = 0.03
                s.post('http://localhost:9999/v1/orders', params={'ticker': t, 'type': 'LIMIT', 'price': algo_close + (spread + 0.01), 'quantity': 500, 'action': 'SELL'})
                s.post('http://localhost:9999/v1/orders', params={'ticker': t, 'type': 'LIMIT', 'price': algo_close + (spread + 0.02), 'quantity': 500, 'action': 'SELL'})
                s.post('http://localhost:9999/v1/orders', params={'ticker': t, 'type': 'LIMIT', 'price': algo_close - (spread + 0.02), 'quantity': 750, 'action': 'BUY'})
                s.post('http://localhost:9999/v1/orders', params={'ticker': t, 'type': 'LIMIT', 'price': algo_close + (spread + 0.02), 'quantity': 500, 'action': 'SELL'})
                s.post('http://localhost:9999/v1/orders', params={'ticker': t, 'type': 'LIMIT', 'price': algo_close + (spread + 0.03), 'quantity': 500, 'action': 'SELL'})
                sleep(1.7)

                if position < -5000:
                    spread = 0.02
                elif len(orders) >= 16:
                    spread = 0.02
            
            if 15000 > ask_bid_voldif:
                spread = 0.03
                s.post('http://localhost:9999/v1/orders', params={'ticker': t, 'type': 'LIMIT', 'price': algo_close - (spread + 0.01), 'quantity': 500, 'action': 'BUY'})
                s.post('http://localhost:9999/v1/orders', params={'ticker': t, 'type': 'LIMIT', 'price': algo_close - (spread + 0.02), 'quantity': 500, 'action': 'BUY'})
                s.post('http://localhost:9999/v1/orders', params={'ticker': t, 'type': 'LIMIT', 'price': algo_close + (spread + 0.02), 'quantity': 750, 'action': 'SELL'})
                s.post('http://localhost:9999/v1/orders', params={'ticker': t, 'type': 'LIMIT', 'price': algo_close - (spread + 0.02), 'quantity': 500, 'action': 'BUY'})
                s.post('http://localhost:9999/v1/orders', params={'ticker': t, 'type': 'LIMIT', 'price': algo_close - (spread + 0.03), 'quantity': 500, 'action': 'BUY'})
                sleep(1.7)

                if position > 5000 :
                    spread = 0.02
                elif len(orders) >= 15:
                    spread = 0.02

            if 15000 < ask_bid_voldif_1:
                spread = 0.03
                s.post('http://localhost:9999/v1/orders', params={'ticker': t1, 'type': 'LIMIT', 'price': algo_close_1 + (spread + 0.01), 'quantity': 500, 'action': 'SELL'})
                s.post('http://localhost:9999/v1/orders', params={'ticker': t1, 'type': 'LIMIT', 'price': algo_close_1 + (spread + 0.02), 'quantity': 500, 'action': 'SELL'})
                s.post('http://localhost:9999/v1/orders', params={'ticker': t1, 'type': 'LIMIT', 'price': algo_close_1 - (spread + 0.02), 'quantity': 750, 'action': 'BUY'})
                s.post('http://localhost:9999/v1/orders', params={'ticker': t1, 'type': 'LIMIT', 'price': algo_close_1 + (spread + 0.02), 'quantity': 500, 'action': 'SELL'})
                s.post('http://localhost:9999/v1/orders', params={'ticker': t1, 'type': 'LIMIT', 'price': algo_close_1 + (spread + 0.03), 'quantity': 500, 'action': 'SELL'})
                sleep(1.7)

                if position_1 < -5000:
                    spread = 0.02
                elif len(orders) >= 16:
                    spread = 0.02
                
            
            if 15000 > ask_bid_voldif_1:
                spread = 0.03
                s.post('http://localhost:9999/v1/orders', params={'ticker': t1, 'type': 'LIMIT', 'price': algo_close_1 - (spread + 0.01), 'quantity': 500, 'action': 'BUY'})
                s.post('http://localhost:9999/v1/orders', params={'ticker': t1, 'type': 'LIMIT', 'price': algo_close_1 - (spread + 0.02), 'quantity': 500, 'action': 'BUY'})
                s.post('http://localhost:9999/v1/orders', params={'ticker': t1, 'type': 'LIMIT', 'price': algo_close_1 + (spread + 0.02), 'quantity': 750, 'action': 'SELL'})
                s.post('http://localhost:9999/v1/orders', params={'ticker': t1, 'type': 'LIMIT', 'price': algo_close_1 - (spread + 0.02), 'quantity': 500, 'action': 'BUY'})
                s.post('http://localhost:9999/v1/orders', params={'ticker': t1, 'type': 'LIMIT', 'price': algo_close_1 - (spread + 0.03), 'quantity': 500, 'action': 'BUY'})
                sleep(1.7)

                if position_1 > 5000 :
                    spread = 0.02
                elif len(orders) >= 15:
                    spread = 0.02

            if position <= -5000:
                
                s.post('http://localhost:9999/v1/orders', params={'ticker': t, 'type': 'LIMIT', 'price': algo_close, 'quantity': 750, 'action': 'BUY'})
                s.post('http://localhost:9999/v1/orders', params={'ticker': t, 'type': 'LIMIT', 'price': algo_close, 'quantity': 750, 'action': 'BUY'})
                s.post('http://localhost:9999/v1/orders', params={'ticker': t, 'type': 'LIMIT', 'price': algo_close, 'quantity': 750, 'action': 'BUY'})
                s.post('http://localhost:9999/v1/orders', params={'ticker': t, 'type': 'LIMIT', 'price': algo_close, 'quantity': 750, 'action': 'BUY'})
                s.post('http://localhost:9999/v1/orders', params={'ticker': t, 'type': 'LIMIT', 'price': algo_close, 'quantity': 750, 'action': 'BUY'})
                sleep(1)

            if position_1 <= -5000:
                
                s.post('http://localhost:9999/v1/orders', params={'ticker': t1, 'type': 'LIMIT', 'price': algo_close_1  , 'quantity': 750, 'action': 'BUY'})
                
                s.post('http://localhost:9999/v1/orders', params={'ticker': t1, 'type': 'LIMIT', 'price': algo_close_1 , 'quantity': 750, 'action': 'BUY'})
                
                s.post('http://localhost:9999/v1/orders', params={'ticker': t1, 'type': 'LIMIT', 'price': algo_close_1 , 'quantity': 750, 'action': 'BUY'})
                s.post('http://localhost:9999/v1/orders', params={'ticker': t1, 'type': 'LIMIT', 'price': algo_close_1  , 'quantity': 750, 'action': 'BUY'})
                s.post('http://localhost:9999/v1/orders', params={'ticker': t1, 'type': 'LIMIT', 'price': algo_close_1  , 'quantity': 750, 'action': 'BUY'})
                sleep(1)

            if position >= 5000:
                                
                s.post('http://localhost:9999/v1/orders', params={'ticker': t, 'type': 'LIMIT', 'price': algo_close , 'quantity': 750, 'action': 'SELL'})
                
                s.post('http://localhost:9999/v1/orders', params={'ticker': t, 'type': 'LIMIT', 'price': algo_close , 'quantity': 750, 'action': 'SELL'})
                
                s.post('http://localhost:9999/v1/orders', params={'ticker': t, 'type': 'LIMIT', 'price': algo_close , 'quantity': 750, 'action': 'SELL'})
                s.post('http://localhost:9999/v1/orders', params={'ticker': t, 'type': 'LIMIT', 'price': algo_close , 'quantity': 750, 'action': 'SELL'})
                s.post('http://localhost:9999/v1/orders', params={'ticker': t, 'type': 'LIMIT', 'price': algo_close , 'quantity': 750, 'action': 'SELL'})
                sleep(1)

            if position_1 >= 5000:
                
                
                s.post('http://localhost:9999/v1/orders', params={'ticker': t1, 'type': 'LIMIT', 'price': algo_close_1 , 'quantity': 750, 'action': 'SELL'})
                s.post('http://localhost:9999/v1/orders', params={'ticker': t1, 'type': 'LIMIT', 'price': algo_close_1 , 'quantity': 750, 'action': 'SELL'})
                s.post('http://localhost:9999/v1/orders', params={'ticker': t1, 'type': 'LIMIT', 'price': algo_close_1 , 'quantity': 750, 'action': 'SELL'})
                s.post('http://localhost:9999/v1/orders', params={'ticker': t1, 'type': 'LIMIT', 'price': algo_close_1 , 'quantity': 750, 'action': 'SELL'})
                s.post('http://localhost:9999/v1/orders', params={'ticker': t1, 'type': 'LIMIT', 'price': algo_close_1 , 'quantity': 750, 'action': 'SELL'})
                sleep(1)
                
            order_len = len(orders)

            cnr_orders = []
            ac_orders = []
            ry_orders = []
            order_index = 0

            for i in orders:
                if orders[order_index]['ticker'] == 'CNR':
                    cnr_orders.append(orders[order_index])
                if orders[order_index]['ticker'] == 'RY':
                    ry_orders.append(orders[order_index])
                order_index += 1

            t = 'CNR'
            t1 = 'RY'
            t2 = 'AC'
            
            if len(cnr_orders) >= 20:
                                
                order_cancel_length = order_len - 12
                order_id_list = []

                for i in range(order_cancel_length):
                    int_i = int(i)
                    location = order_len - int_i - 1
                    int(location)
                    order_id = orders[location]['order_id']
                    order_id_list.append(order_id)

                s.post('http://localhost:9999/v1/commands/cancel', params={'all': 0, 'ticker': t, 'ids': order_id_list})

            if len(ry_orders) >= 20:
                                
                order_cancel_length = order_len - 12
                order_id_list = []

                for i in range(order_cancel_length):
                    int_i = int(i)
                    location = order_len - int_i - 1
                    int(location)
                    order_id = orders[location]['order_id']
                    order_id_list.append(order_id)

                s.post('http://localhost:9999/v1/commands/cancel', params={'all': 0, 'ticker': t1, 'ids': order_id_list})

                s.post('http://localhost:9999/v1/commands/cancel', params={'all': 0, 'ticker': t2, 'ids': order_id_list})

            print(len(cnr_orders), len(ac_orders), len(ry_orders))

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    main()