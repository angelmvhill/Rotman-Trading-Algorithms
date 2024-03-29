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

# this function submits a buy order
def buy_order(session, ticker, quantity, price, price_cushion):
    buy_param = {'ticker': ticker, 'type': 'LIMIT', 'quantity': quantity, 'action': 'BUY', 'price': price + (price * price_cushion)}
    session.post('http://localhost:9999/v1/orders', params = buy_param)

# this function submits a sell order
def sell_order(session, ticker, quantity, price, price_cushion):
    buy_param = {'ticker': ticker, 'type': 'LIMIT', 'quantity': quantity, 'action': 'SELL', 'price': price + (price * price_cushion)}
    session.post('http://localhost:9999/v1/orders', params = buy_param)

# this function liquidates the entire portfolio
def liquidate_portfolio():
    pass

# this function fetches the position size for a given ticker
def get_position(session, ticker):
    positions = session.get('http://localhost:9999/v1/securities', params={'ticker': ticker})
    position = positions.json()[0]['position']
    return position

# this is the main method containing the actual order routing logic
def main():

    with requests.Session() as s:
        # add the API key to the session to authenticate during requests
        s.headers.update(API_KEY)
        t = 'ALGO'
        # get the current time of the case
        tick = get_tick(s)

        refining_iteration = 0

        while 0 <= tick <= 601:

            quantity = 30

            # RENT STORAGE
            for i in range(3):
                s.post('http://localhost:9999/v1/leases', params = {'ticker': 'CL-STORAGE', 'from': 'CONTAINER'})
                sleep(.25)

            print('rent storage')

            # BUY OIL
            # for i in range(10):
            s.post('http://localhost:9999/v1/orders', params = {'ticker': 'CL', 'type': 'MARKET', 'quantity': 30, 'action': 'BUY'})
            sleep(.25)
            print('buy oil')


            # OIL FUTURE
            get_cl_1f = s.get('http://localhost:9999/v1/securities', params = {'ticker': 'CL-1F'})
            cl_1f_price = get_cl_1f.json()[0]['ask']

            if cl_1f_price > 0:
                s.post('http://localhost:9999/v1/orders', params = {'ticker': 'CL-1F', 'type': 'MARKET', 'quantity': 30, 'action': 'SELL'})
            else:
                s.post('http://localhost:9999/v1/orders', params = {'ticker': 'CL-2F', 'type': 'MARKET', 'quantity': 30, 'action': 'SELL'})
            print('oil future')

            # securities = s.get('http://localhost:9999/v1/securities')
            # oil_future = securities.json()[3]['ticker']
            # # print(oil_future)

            # if oil_future == 'CL-1F':
            #     s.post('http://localhost:9999/v1/orders', params = {'ticker': 'CL-1F', 'type': 'MARKET', 'quantity': quantity, 'action': 'SELL'})
            # ### THIS LINE IS NOT WORKING (BELOW)
            # # can we choose when to buy and sell the future to lock in profit???
            # else:
            #     s.post('http://localhost:9999/v1/orders', params = {'ticker': 'CL-2F', 'type': 'MARKET', 'quantity': quantity, 'action': 'SELL'})

            # USE REFINERY
            leases = s.get('http://localhost:9999/v1/leases')

            refinery_id = -1

            for i in leases.json():
                if i['ticker'] == 'CL-REFINERY':
                    refinery_id = i['id']

            print(refinery_id)

            if refinery_id == -1:
                s.post('http://localhost:9999/v1/leases', params = {'ticker': 'CL-REFINERY', 'from': 'REFINERY'})
                sleep(.2)

            leases = s.get('http://localhost:9999/v1/leases')
            for i in leases.json():
                if i['ticker'] == 'CL-REFINERY':
                    refinery_id = i['id']

            s.post(f'http://localhost:9999/v1/leases/{refinery_id}?from1=CL&quantity1={quantity}')
            print('use refinery')

            print(f'{refinery_id} (storage ID) is being cancelled...')

            leases = s.get('http://localhost:9999/v1/leases')

            storage_id = -1

            for i in leases.json():
                if i['ticker'] == 'CL-STORAGE':
                    storage_id = i['id']
                    print(f'{storage_id} (storage ID) is being cancelled...')
                    s.delete(f'http://localhost:9999/v1/leases/{storage_id}')
                    sleep(.25)

            print('cancel storage')

            # GET RB AND HO POSITIONS
            ho_position = 0
            rb_position = 0

            while ho_position == 0 or rb_position == 0:
                ho = s.get('http://localhost:9999/v1/securities', params={'ticker': 'HO'})
                if ho.json()[0]['position'] != 0.0:
                    ho_position = ho.json()[0]['position']
                rb = s.get('http://localhost:9999/v1/securities', params={'ticker': 'RB'})
                if rb.json()[0]['position'] != 0.0:
                    rb_position = rb.json()[0]['position']
                print('getting RB and HO position')
                sleep(1)

            # SELL HO, RB, AND FUTURES CONTRACT
            cl_1f = s.get('http://localhost:9999/v1/securities', params={'ticker': 'CL-1F'})
            cl_1f_position = cl_1f.json()[0]['position']
            cl_2f = s.get('http://localhost:9999/v1/securities', params={'ticker': 'CL-2F'})
            cl_2f_position = cl_2f.json()[0]['position']
            print('get futures position')

            if cl_1f_position < 0.0:
                s.post('http://localhost:9999/v1/orders', params={'ticker': 'CL-1F', 'type': 'MARKET', 'quantity': -cl_1f_position, 'action': 'BUY'})
            if cl_2f_position < 0.0:
                s.post('http://localhost:9999/v1/orders', params={'ticker': 'CL-2F', 'type': 'MARKET', 'quantity': -cl_2f_position, 'action': 'BUY'})
            print('sell futures')

            # SELL RB AND HO
            s.post('http://localhost:9999/v1/orders', params={'ticker': 'RB', 'type': 'MARKET', 'quantity': rb_position, 'action': 'SELL'})
            # sleep(.1)
            s.post('http://localhost:9999/v1/orders', params={'ticker': 'HO', 'type': 'MARKET', 'quantity': ho_position, 'action': 'SELL'})
            print('sell HO and RB')

            refining_iteration += 1
            if refining_iteration == 25:
                s.delete(f'http://localhost:9999/v1/leases/{refinery_id}')
                break

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    main()