import os
from datetime import datetime, date
import time
import logging
import statistics
from threading import Thread

from lib import util
from models.hft_chartdata import ChartData

CONTRACT_NR = 1

def print_and_log(string):
    logging.info(string)
    print(string)

class HftMonitor:

    def __init__(self, ticker, remote):
        # price variables to be substituted by:
        self.chart_data = ChartData()
        
        # Positions
        self.position = 0
        self.confirmed_position = 0 # set by IB

        # for internal count or backtesting
        self.order_price = 0
        # self.confirmed_price = 0
        self.pnl = 0
        self.nr_of_trades = 0

        # Orders
        self.active_order_id = None
        
        # general variables
        self.ticker = ticker.upper()
        self.contract = util.get_contract(self.ticker)

        self.remote = remote


    def price_change(self, tickType, price, price_time):
        if price <= 0:
            print_and_log(f"Returned 0 or under 0 price: '{price}', for ticker {self.ticker}")
            return

        # bid price = 1
        # ask price = 2
        # last traded price = 4

        if tickType == 4:
            self.chart_data.add_price(price, price_time)

            # if self.chart_data.action[0] == "notify" and price_time == 0:
            #     self.sound_notify()

            if self.chart_data.notification[0] == "state_changed":
                print_and_log(self.chart_data.notification[1])
                print_and_log("o             o")
                print_and_log(self.chart_data.state_str())
                print_and_log("\n\n\n")

            # Debugging purposes
            if self.chart_data.state in (2, 3):
                print_and_log(self.chart_data.state_str())
                print_and_log("\n\n\n")

            if self.chart_data.action[0] == "buy":
                self.position = CONTRACT_NR
                self.order_price = self.chart_data.action[1]
                self.nr_of_trades += 1

                if self.confirmed_position == 0 and not self.active_order(): # be sure!
                    # remote.place_order(self, "BUY", CONTRACT_NR, self.chart_data.action[1])
                    pass

                print_and_log(f"Order to buy at {self.chart_data.action[1]}")
                print_and_log("o             o")
                print_and_log(self.chart_data.state_str())
                print_and_log("\n\n\n")

            elif self.chart_data.action[0] == "sell":
                self.position = -CONTRACT_NR
                self.order_price = self.chart_data.action[1]
                self.nr_of_trades += 1

                if self.confirmed_position == 0 and not self.active_order(): # be sure!
                    # remote.place_order(self, "SELL", CONTRACT_NR, self.chart_data.action[1])
                    pass

                print_and_log(f"Order to sell at {self.chart_data.action[1]}")
                print_and_log("o             o")
                print_and_log(self.chart_data.state_str())
                print_and_log("\n\n\n")
            
            elif self.chart_data.action[0] == "close":
                if self.position == CONTRACT_NR:
                    self.pnl += self.chart_data.action[1] - self.order_price
                elif self.position == -CONTRACT_NR:
                    self.pnl += self.order_price - self.chart_data.action[1]
                self.nr_of_trades += 1
                
                if self.confirmed_position == CONTRACT_NR and not self.active_order(): # be sure!
                    # remote.place_order(self, "SELL", CONTRACT_NR)
                    pass
                elif self.confirmed_position == -CONTRACT_NR and not self.active_order(): # be sure!
                    # remote.place_order(self, "BUY", CONTRACT_NR)
                    pass

                print_and_log(f"Order to close at {self.chart_data.action[1]}")
                print_and_log("o              o")
                print_and_log(self.chart_data.state_str())
                print_and_log("o              o")
                print_and_log(f"P&L: {self.pnl}")
                print_and_log(f"Nr of trades {self.nr_of_trades}")
                print_and_log("\n\n\n")
            
    # All position querying should be done with self.confirmed_position once the system is executing orders

    def order_change(self, order_id, status, remaining):
        if status == "Filled":
            self.active_order_id = None
            # self.confirmed_price = self.order_price
        elif status == "Cancelled":
            self.active_order_id = None
        else:
            # get the order id after placing the order so
            # it is managed only on remote
            self.active_order_id = order_id
        self.confirmed_position = remaining

        print_and_log(f"Remaining (current positions): {self.confirmed_position}")
        if abs(self.confirmed_position) > CONTRACT_NR:
            print_and_log("PROBLEM!! MORE THAN {CONTRACT_NR} CONTRACTS")
            self.sound_notify()


    def close(self):
        self.chart_data.close()

    
    # Private

    def sound_notify(self):
        Thread(target = lambda: os.system("mpv --really-quiet /home/bruno/Downloads/Goat-sound-effect.mp3")).start()

    def active_order(self):
        self.active_order_id is not None
