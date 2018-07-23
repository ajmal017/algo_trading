import time
from threading import Thread
import logging
import json

import pygal

import gvars
from lib import util

# State objects can be used to return data and decide in this class whether to change state
# or just return direct information and get this class to ask if should change or not
from models.states.breaking import Breaking
from models.states.range import Range
from models.states.trending import Trending
from models.cycle import Cycle

STATE = {"random_walk": 0, "in_range": 1, "breaking_up": 2, "breaking_down": 3, "trending_up": 4, "trending_down": 5}
HEIGHT = {"max": 1, "mid": 0, "min": -1}
# ACTION = {"buy": 1, "sell": 2, "close": 3, "notify": 4}

class ChartData:
    def __init__(self, ticker):

        self.ticker = ticker
        self.prm = get_initial_parameters_for_ticker(ticker)
        
        # Data
        self.data = []
        self.state = STATE["random_walk"]

        self.cycles = []
        
        # Not in use now because it is a property
        # self.ls = None
        
        self.notification = ("", None)
        self.action = ("", None) # tuple with: (action, price)

        
        # self.timed_prices = []

        # self.timer_active = True
        # self.timer = Thread(target = self.timed_work)
        # self.timer.start()


    def add_price(self, price, price_time):
        self.notification = ("", None)
        self.action = ("", None)
        cdp = ChartDataPoint()
        cdp.price = price
        cdp.time = price_time
        if len(self.data) > 0:
            if self.data[-1].price == price:
                return
            self.data[-1].duration = cdp.time - self.data[-1].time

        self.data.append(cdp)
        
        self.set_last_height_and_trend()

        self.find_and_set_state()


    def set_last_height_and_trend(self):
        if len(self.data) == 0:
            return
        if len(self.data) == 1:
            self.data[-1].trend = 1 # Arbitrary, could be -1
            return

        if self.data[-1].price > self.data[-2].price:
            new_trend = round((self.data[-1].price - self.data[-2].price) / self.prm["TICK_PRICE"])
            if self.data[-2].trend > 0:
                self.data[-1].trend = self.data[-2].trend + new_trend
                self.data[-2].height = HEIGHT["mid"]
            else:
                self.data[-1].trend = new_trend
                self.data[-2].height = HEIGHT["min"]
        else: # They can not be equal
            new_trend = round((self.data[-2].price - self.data[-1].price) / self.prm["TICK_PRICE"])
            if self.data[-2].trend < 0:
                self.data[-1].trend = self.data[-2].trend - new_trend
                self.data[-2].height = HEIGHT["mid"]
            else:
                self.data[-1].trend = -new_trend
                self.data[-2].height = HEIGHT["max"]

    
    def find_and_set_state(self):

        if self.state_is("random_walk"):
            
            self.set_range()
        
        elif self.state_is("in_range"):

            self.last_range.price_changed()
            rng = self.last_range
            
            if rng.max_price < self.last_price() <= rng.max_price + self.prm["BREAKING_RANGE_VALUE"]:
                self.ls = Breaking("up", self)
                self.set_state("breaking_up")

            elif rng.min_price - self.prm["BREAKING_RANGE_VALUE"] <= self.last_price() < rng.min_price:
                self.ls = Breaking("down", self)
                self.set_state("breaking_down")

            elif ((self.last_price() > rng.max_price + self.prm["BREAKING_RANGE_VALUE"]) or 
                            (self.last_price() < rng.min_price - self.prm["BREAKING_RANGE_VALUE"])):
                self.set_state("random_walk")


        elif self.state_is("breaking_up"):

            rng = self.last_range

            if ((self.last_price() > rng.max_price + self.prm["BREAKING_RANGE_VALUE"]) or
                            (self.last_price() < rng.min_price)):
                self.set_state("random_walk")
                return

            if rng.min_price <= self.last_price() <= (rng.max_price - self.prm["TICK_PRICE"]):
                self.set_state("in_range")
                return

            self.ls.price_changed()

            if (self.ls.breaking_price_changes >= self.prm["MIN_BREAKING_PRICE_CHANGES"] and
                            self.last_price() > self.ls.mid_price and self.ls.duration_ok):
                # self.transaction_price = round(self.last_price() - 1 * self.prm["TICK_PRICE"], 2)
                self.ls = Trending('up', self)
                self.action = ("buy", self.last_price())
                self.set_state('trending_up')


        elif self.state_is("breaking_down"):

            rng = self.last_range

            if ((self.last_price() < rng.min_price - self.prm["BREAKING_RANGE_VALUE"]) or
                            (self.last_price() > rng.max_price)):
                self.set_state("random_walk")
                return

            elif (rng.min_price + self.prm["TICK_PRICE"]) <= self.last_price() <= rng.max_price:
                self.set_state("in_range")
                return

            self.ls.price_changed()

            if (self.ls.breaking_price_changes >= self.prm["MIN_BREAKING_PRICE_CHANGES"] and
                            self.last_price() < self.ls.mid_price and self.ls.duration_ok):
                # self.transaction_price = round(self.last_price() + 1 * self.prm["TICK_PRICE"], 2)
                self.ls = Trending('down', self)
                self.action = ("sell", self.last_price())
                self.set_state('trending_down')


        elif self.state_is("trending_up"):

            self.ls.price_changed()

            if self.ls.trending_stop():
                self.action = ("close", self.last_price()) # CLOSE POSITION SIGNAL (SELL) # last_price is added for backtesting purposes
                self.cycles[-1].pnl = self.last_price() - self.ls.transaction_price
                self.set_state("random_walk")

        elif self.state_is("trending_down"):

            self.ls.price_changed()

            if self.ls.trending_stop():
                self.action = ("close", self.last_price()) # CLOSE POSITION SIGNAL (BUY) # last_price is added for backtesting purposes
                self.cycles[-1].pnl = self.ls.transaction_price - self.last_price()
                self.set_state("random_walk")
        

    def set_range(self):
        min_price = self.last_price()
        max_price = self.last_price()
        max_range_value = self.prm["MAX_RANGE_VALUE"]
        outside_duration = 0
        start_time = 0
        for cdp in reversed(self.data):
            if cdp.price > max_price:

                if cdp.price - min_price <= max_range_value:
                    max_price = cdp.price
                    outside_duration = 0
                else:
                    outside_duration += cdp.duration
                    if outside_duration > self.prm["MIN_RANGE_TIME"] / 20.0:
                        break

            elif cdp.price < min_price:

                if max_price - cdp.price <= max_range_value:
                    min_price = cdp.price
                    outside_duration = 0
                else:
                    outside_duration += cdp.duration
                    if outside_duration > self.prm["MIN_RANGE_TIME"] / 20.0:
                        break

            else: # Inside max and min
                outside_duration = 0
            
            if self.last_time() - cdp.time > self.prm["MIN_RANGE_TIME"]:
                start_time = cdp.time
                # max_range_value = max_price - min_price # in the case we want to consider thiner ranges

        if start_time > 0:
            self.ls = Range(self, min_price, max_price, start_time)
            self.set_state("in_range")


    def set_state(self, state):
        if self.state != STATE[state]:
            self.notification = ("state_changed", f"State changed from {self.state} to {STATE[state]}")
            self.state = STATE[state]

    
    def state_is(self, state):
        return self.state == STATE[state]


    def last_cdp(self):
        if len(self.data) == 0:
            return ChartDataPoint()
        return self.data[-1]

    def last_price(self):
        return self.last_cdp().price

    def last_time(self):
        return self.last_cdp().time

    @property
    def last_range(self):
        for state in reversed(self.cycles[-1].states):
            if type(state) is Range:
                return state


    # ------ Cycles ------------
    # Last State
    @property
    def ls(self):
        return self.cycles[-1].last_state()
    
    # add_state(self, state)
    @ls.setter
    def ls(self, value):
        if len(self.cycles) == 0 or self.cycles[-1].closed():
            self.cycles.append(Cycle())
        self.cycles[-1].add_state(value)
    # --------------------------


    
    # the_time could be a specific time or an amount of time since now
    def data_since(self, time_or_duration):
        data_since = []
        for cdp in reversed(self.data):
            data_since.append(cdp)
            if cdp.time == time_or_duration:
                break
            elif self.last_time() - cdp.time > time_or_duration:
                data_since.pop() # patch because of adding the element first
                break
        data_since.reverse()
        assert len(data_since) < len(self.data)
        return data_since

    
    def time_up_down_since(self, the_time, price):
        time_up = 0
        time_equal = 0
        time_down = 0
        for cdp in self.data_since(the_time):
            if cdp.price > price:
                time_up += cdp.duration
            elif cdp.price == price:
                time_equal += cdp.duration
            else:
                time_down += cdp.duration
        return (time_up, time_equal, time_down)


    def min_max_since(self, time_ago):
        data_portion = self.data_since(time_ago)
        return (min(data_portion, key=lambda cdp: cdp.price),
                max(data_portion, key=lambda cdp: cdp.price))


    def timed_prices(self, time_ago=0):
        data = self.data if time_ago == 0 else self.data_since(time_ago)
        timed_prices = []
        initial_time = data[0].time
        interval = 0
        i = 1
        while i < len(data):
            if data[i].time - initial_time >= interval:
                timed_prices.append(data[i-1].price)
                interval += 60
            else:
                i += 1
        return timed_prices

    
    def close(self):
        self.timer_active = False
        self.output_chart()
        self.save_data()


    def state_str(self):
        if len(self.data) < 2:
            return ""
        output = (
            f"Prev =>  P: {self.data[-2].price} - D: {self.data[-2].duration} | Current: P {self.data[-1].price}\n"
            f"state: {self.state}\n"
            f"action: {self.action}\n"
        )
        if len(self.cycles) > 0:
            for state in self.cycles[-1].states:
                output += state.state_str()
        return output


    def output_chart(self):
        initial_time = self.data[0].time

        chart = pygal.XY()
        chart.add('Prices',  list(map(lambda cdp: (cdp.time - initial_time, cdp.price), self.data)))

        chart.show_dots = True
        chart.render_to_file(f"{gvars.TEMP_DIR}/{self.ticker}_timed_prices.svg")


    def save_data(self):
        if self.test_mode():
            return
        mapped_data = list(map(lambda cdp: (cdp.time, cdp.price), self.data))
        file_name = f"{gvars.TEMP_DIR}/{self.ticker}_live_{time.strftime('%Y-%m-%d|%H-%M')}.json"
        with open(file_name, "w") as f:
            json.dump(mapped_data, f)


    def test_mode(self):
        return util.contract_type(self.ticker) != "FUT"


    # def timed_work(self):
    #     sec = 0
    #     while self.timer_active:
    #         if len(self.data) > 0 and sec % 60 == 0:
    #             if len(self.timed_prices) > 120:
    #                 self.timed_prices.pop(0)
    #             self.timed_prices.append(self.last_price())
    #         sec += 1
    #         time.sleep(1)


class ChartDataPoint:
    def __init__(self):
        self.price = 0
        self.time = 0
        self.duration = 0
        self.height = 0 # min - mid - max
        self.trend = 0 # distance from min or max
        # self.slope = 0


def get_initial_parameters_for_ticker(ticker):
    prm = {}
    if ticker[0:2] == "GC":
        prm["TICK_PRICE"] = 0.10
        prm["MAX_RANGE_VALUE"] = 5 * prm["TICK_PRICE"]
        prm["BREAKING_RANGE_VALUE"] = 3 * prm["TICK_PRICE"]
        prm["MIN_TRENDING_BREAK_VALUE"] = 2 * prm["TICK_PRICE"]
    elif ticker[0:2] == "CL":
        prm["TICK_PRICE"] = 0.01
        prm["MAX_RANGE_VALUE"] = 8 * prm["TICK_PRICE"]
        prm["BREAKING_RANGE_VALUE"] = 4 * prm["TICK_PRICE"]
        prm["MIN_TRENDING_BREAK_VALUE"] = 3 * prm["TICK_PRICE"]
    elif ticker[0:2] == "NG":
        prm["TICK_PRICE"] = 0.001
        prm["MAX_RANGE_VALUE"] = 8 * prm["TICK_PRICE"]
        prm["BREAKING_RANGE_VALUE"] = 4 * prm["TICK_PRICE"]
        prm["MIN_TRENDING_BREAK_VALUE"] = 3 * prm["TICK_PRICE"]
    elif ticker[0:2] == "ES":
        prm["TICK_PRICE"] = 0.25
        prm["MAX_RANGE_VALUE"] = 5 * prm["TICK_PRICE"]
        prm["BREAKING_RANGE_VALUE"] = 3 * prm["TICK_PRICE"]
        prm["MIN_TRENDING_BREAK_VALUE"] = 2 * prm["TICK_PRICE"]
    elif ticker[0:3] == "EUR":
        prm["TICK_PRICE"] = 0.00005
        prm["MAX_RANGE_VALUE"] = 4 * prm["TICK_PRICE"]
        prm["BREAKING_RANGE_VALUE"] = 2 * prm["TICK_PRICE"]
        prm["MIN_TRENDING_BREAK_VALUE"] = 2 * prm["TICK_PRICE"]

    prm["MIN_RANGE_TIME"] = 450 # seconds
    # prm["MAX_TIME_OUTSIDE_OF RANGE"] = prm["MIN_RANGE_TIME"] / 20 # 5% of the time
    
    prm["MIN_BREAKING_PRICE_CHANGES"] = 4 # times
    prm["UP_DOWN_RATIO"] = 1.0

    prm["TRENDING_BREAK_TIME"] = 60 # secs

    return prm