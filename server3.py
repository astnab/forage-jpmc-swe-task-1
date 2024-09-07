################################################################################
#
#  Permission is hereby granted, free of charge, to any person obtaining a
#  copy of this software and associated documentation files (the "Software"),
#  to deal in the Software without restriction, including without limitation
#  the rights to use, copy, modify, merge, publish, distribute, sublicense,
#  and/or sell copies of the Software, and to permit persons to whom the
#  Software is furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included in
#  all copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
#  OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
#  FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#  DEALINGS IN THE SOFTWARE.

import csv
# from BaseHTTPServer import BaseHTTPRequestHandler,HTTPServer
import http.server
import json
import operator
import os.path
import re
import threading
from datetime import timedelta, datetime
# from itertools import izip
from random import normalvariate, random
from socketserver import ThreadingMixIn

import dateutil.parser

################################################################################
#
# Config

# Sim params

REALTIME = True # simulates real-time data; otherwise, simulates historical data
SIM_LENGTH = timedelta(days=365 * 5) ## duration of simulation
MARKET_OPEN = datetime.today().replace(hour=0, minute=30, second=0) ## market start time

# Market parms
#       min  / max  / std
SPD = (2.0, 6.0, 0.1) ## parameter for market data simulation. spread
PX = (60.0, 150.0, 1) ## price
FREQ = (12, 36, 50) ## frequency

# Trades

OVERLAP = 4 ## generating order data


################################################################################
#
# Test Data

## def / define = define a function
## yield = pauses the function and allows it to continue, producing a sequence of values one at a time

def bwalk(min, max, std): 
    """ Generates a bounded random walk. """
    rng = max - min
    while True:
        max += normalvariate(0, std)
        # updates max value by adding normal variate and std
        yield abs((max % (rng * 2)) - rng) + min
        # nilai mutlak dari selisih antara sisa pembagian max dengan rng, membatasi nilai max dalam rentang dari min hingga max 


def market(t0=MARKET_OPEN):
    """ Generates a random series of market conditions,
        (time, price, spread).
    """
    # hours = variable jumlah jam perubahan waktu pasar
    for hours, px, spd in zip(bwalk(*FREQ), bwalk(*PX), bwalk(*SPD)):
       # zip menggabungkan bbrp iterable mjd satu iterable berisi tuples
        yield t0, px, spd
        t0 += timedelta(hours=abs(hours))
        # timedelta -> duration/time interval


def orders(hist):
    """ Generates a random set of limit orders (time, side, price, size) from
        a series of market conditions.
    """
    # iterating every element in hist, hist = a list/iterable of tuples. tuples = t, px, spd
    for t, px, spd in hist:
        stock = 'ABC' if random() > 0.5 else 'DEF'
        # if random() 0.5 then stock = ABC
        # side is like type of the order -> buy or sell
        # if random() > 0.5 maka side = sell and d = 2
        side, d = ('sell', 2) if random() > 0.5 else ('buy', -2)
        order = round(normalvariate(px + (spd / d), spd / OVERLAP), 2)
        # round -> rounding to 2 decimals
        # px (existing price) + spd/d (spread/d atau arah transaksi, meningkat/menurun)
        # normalvariate utk simulate harga order dan ukuran order dalam distribusi yang mirip dengan apa yang terjadi di dunia nyata
        size = int(abs(normalvariate(0, 100)))
        yield t, stock, side, order, size


################################################################################
#
# Order Book

def add_book(book, order, size, _age=10):
    """ Add a new order and size to a book, and age the rest of the book. """
    yield order, size, _age
    for o, s, age in book:
        ## iterate setiap order (terdiri atas o, s, age) di dalam book
        if age > 0:
            yield o, s, age - 1


def clear_order(order, size, book, op=operator.ge, _notional=0):
    """ Try to clear a sized order against a book, returning a tuple of
        (notional, new_book) if successful, and None if not.  _notional is a
        recursive accumulator and should not be provided by the caller.
    """
    # tuple unpacking -> take elements from book and divide into variables (top_order, top_size, age), lalu tail berisi book[1:] indeks pertama dan seterusnya
    (top_order, top_size, age), tail = book[0], book[1:]
    if op(order, top_order):
        # if order >= top_order = true
        _notional += min(size, top_size) * top_order
        # notional -> parameter accumulator (temp)
        sdiff = top_size - size
        # size difference
        if sdiff > 0:
            return _notional, list(add_book(tail, top_order, sdiff, age))
        elif len(tail) > 0:
            # len = length
            return clear_order(order, -sdiff, tail, op, _notional)


def clear_book(buy=None, sell=None):
    """ Clears all crossed orders from a buy and sell book, returning the new
        books uncrossed.
    """
    # loop yg berjalan jika buy/sell ada isinya
    while buy and sell:
        order, size, _ = buy[0]
        # ambil indeks pertama dari buy berisi o, s, _ itu age yg diabaikan
        new_book = clear_order(order, size, sell)
        # run clear_order function
        if new_book:
            sell = new_book[1]
            # renew daftar sell dgn return new_book
            buy = buy[1:]
            # renew daftar buy dgn delete buy[0]
        else:
            break
        # kalo clear_order ga return apa apa, lgsg break/loop berhenti
    return buy, sell


def order_book(orders, book, stock_name):
    """ Generates a series of order books from a series of orders.  Order books
        are mutable lists, and mutating them during generation will affect the
        next turn!
    """
    for t, stock, side, order, size in orders:
        # tuple berisi t (waktu), stock (nama saham), side (buy/sell), order (harga pesanan), size (ukuran pesanan)
        if stock_name == stock:
            # cek apakah argumen stock_name sama dgn stock di pesanan/orders
            new = add_book(book.get(side, []), order, size)
            # run add_book function
            # side = buy/sell
            # [] = default value jika side yg dikasih tdk ada di book
            
            book[side] = sorted(new, reverse=side == 'buy', key=lambda x: x[0])
            # jika side adalah 'buy', maka reverse diatur ke true, sehingga list akan diurutkan dari terbesar ke terkecil
            # jika side bukan 'buy', reverse diatur ke False, sehingga list diurutkan dari terkecil ke terbesar
            # key=lambda x: x[0] -> fungsi kunci yang digunakan untuk menentukan nilai yang akan digunakan untuk urutan
        bids, asks = clear_book(**book)
        yield t, bids, asks
        # bids = daftar order beli, menunjukkan berapa harga yang ingin dibayar dan seberapa banyak yang ingin dibeli
        # asks = daftar order jual, menunjukkan berapa harga yang ingin diterima dan seberapa banyak yang ingin dijual


################################################################################
#
# Test Data Persistence

def generate_csv():
    """ Generate a CSV of order history. """
    with open('test.csv', 'wb') as f:
        ## buka file test.scv dalam mode tulis binary (wb)
        writer = csv.writer(f)
        # csv.writer adalah bagian dari modul csv yang memudahkan penulisan data dalam format CSV
        for t, stock, side, order, size in orders(market()):
            if t > MARKET_OPEN + SIM_LENGTH:
                break
            writer.writerow([t, stock, side, order, size])
            # menulis baris data ke dalam file CSV, data yang ditulis adalah waktu, saham, sisi order, harga order, dan ukuran order


def read_csv():
    """ Read a CSV or order history into a list. """
    with open('test.csv', 'rt') as f:
        # rt mode baca teks
        for time, stock, side, order, size in csv.reader(f):
            # setiap baris dibaca sbg lima nilai: waktu (time), saham (stock), sisi order (side), harga order (order), dan ukuran order (size).
            yield dateutil.parser.parse(time), stock, side, float(order), int(size)
            # mengubah format waktu menjadi objek datetime dengan dateutil.parser.parse(time), mengonversi harga order ke tipe float, dan ukuran order ke tipe int


################################################################################
#
# Server

class ThreadedHTTPServer(ThreadingMixIn, http.server.HTTPServer):
    """ Boilerplate class for a multithreaded HTTP Server, with working
        shutdown.
    """
    allow_reuse_address = True

    def shutdown(self):
        """ Override MRO to shutdown properly. """
        self.socket.close()
        http.server.HTTPServer.shutdown(self)


def route(path):
    """ Decorator for a simple bottle-like web framework.  Routes path to the
        decorated method, with the rest of the path as an argument.
    """

    def _route(f):
        setattr(f, '__route__', path)
        return f

    return _route


def read_params(path):
    """ Read query parameters into a dictionary if they are parseable,
        otherwise returns None.
    """
    query = path.split('?')
    if len(query) > 1:
        query = query[1].split('&')
        return dict(map(lambda x: x.split('='), query))


def get(req_handler, routes):
    """ Map a request to the appropriate route of a routes instance. """
    for name, handler in routes.__class__.__dict__.items():
        if hasattr(handler, "__route__"):
            if None != re.search(handler.__route__, req_handler.path):
                req_handler.send_response(200)
                req_handler.send_header('Content-Type', 'application/json')
                req_handler.send_header('Access-Control-Allow-Origin', '*')
                req_handler.end_headers()
                params = read_params(req_handler.path)
                data = json.dumps(handler(routes, params)) + '\n'
                req_handler.wfile.write(bytes(data, encoding='utf-8'))
                return


def run(routes, host='0.0.0.0', port=8080):
    """ Runs a class as a server whose methods have been decorated with
        @route.
    """

    class RequestHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args, **kwargs):
            pass

        def do_GET(self):
            get(self, routes)

    server = ThreadedHTTPServer((host, port), RequestHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    print('HTTP server started on port 8080')
    while True:
        from time import sleep
        sleep(1)
    server.shutdown()
    server.start()
    server.waitForThread()


################################################################################
#
# App

ops = {
    'buy': operator.le,
    'sell': operator.ge,
}


class App(object):
    """ The trading game server application. """

    def __init__(self):
        self._book_1 = dict()
        self._book_2 = dict()
        self._data_1 = order_book(read_csv(), self._book_1, 'ABC')
        self._data_2 = order_book(read_csv(), self._book_2, 'DEF')
        self._rt_start = datetime.now()
        self._sim_start, _, _ = next(self._data_1)
        self.read_10_first_lines()

    @property
    def _current_book_1(self):
        for t, bids, asks in self._data_1:
            if REALTIME:
                while t > self._sim_start + (datetime.now() - self._rt_start):
                    yield t, bids, asks
            else:
                yield t, bids, asks

    @property
    def _current_book_2(self):
        for t, bids, asks in self._data_2:
            if REALTIME:
                while t > self._sim_start + (datetime.now() - self._rt_start):
                    yield t, bids, asks
            else:
                yield t, bids, asks

    def read_10_first_lines(self):
        for _ in iter(range(10)):
            next(self._data_1)
            next(self._data_2)

    @route('/query')
    def handle_query(self, x):
        """ Takes no arguments, and yields the current top of the book;  the
            best bid and ask and their sizes
        """
        try:
            t1, bids1, asks1 = next(self._current_book_1)
            t2, bids2, asks2 = next(self._current_book_2)
        except Exception as e:
            print("error getting stocks...reinitalizing app")
            self.__init__()
            t1, bids1, asks1 = next(self._current_book_1)
            t2, bids2, asks2 = next(self._current_book_2)
        t = t1 if t1 > t2 else t2
        print('Query received @ t%s' % t)
        return [{
            'id': x and x.get('id', None),
            'stock': 'ABC',
            'timestamp': str(t),
            'top_bid': bids1 and {
                'price': bids1[0][0],
                'size': bids1[0][1]
            },
            'top_ask': asks1 and {
                'price': asks1[0][0],
                'size': asks1[0][1]
            }
        },
            {
                'id': x and x.get('id', None),
                'stock': 'DEF',
                'timestamp': str(t),
                'top_bid': bids2 and {
                    'price': bids2[0][0],
                    'size': bids2[0][1]
                },
                'top_ask': asks2 and {
                    'price': asks2[0][0],
                    'size': asks2[0][1]
                }
            }]


################################################################################
#
# Main

if __name__ == '__main__':
    if not os.path.isfile('test.csv'):
        print("No data found, generating...")
        generate_csv()
    run(App())
