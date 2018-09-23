import sys
sys.path.append('/home/bruno/ib_api/9_73/IBJts/source/pythonclient')

from threading import Thread, Lock
import logging
import time
import json

from ibapi.wrapper import EWrapper
from ibapi.client import EClient
from ibapi.contract import *
from ibapi.common import *
from ibapi.order import *

from lib import util
from models.monitor import Monitor


class IBHft(EClient, EWrapper):

    def __init__(self, tickers=[], input_file=""):
        EClient.__init__(self, wrapper = self)

        self.monitors = []
        self.tickers = tickers

        # state variables
        self.req_id_to_monitor_map = {} # Only parent monitors
        self.order_id_to_monitor_map = {} # Parent and children monitors

        # tws variables
        self.current_req_id = 0
        self.current_order_id = None

        # threading variables
        self.place_order_lock = Lock()

        # Used in load (not live) mode or test orders
        self.active_order = {} # dict by monitor
        self.remaining = {} # dict by monitor
        self.current_tick_time = {} # dict by tick
        self.current_tick_price = {} # dict by tick

        self.live_mode = True if input_file == "" else False
        if self.live_mode:
            self.connect("127.0.0.1", 7497, 0)
            self.run()
            self.wait_for_readiness()
        else:
            self.input_file = input_file
            self.tickers = [util.file_from_path(input_file)]
            self.wait_for_readiness()

            self.test_thread = Thread(target = self.connectAck)
            self.test_thread.start()
            self.test_thread.join()


    def connectAck(self):
        """ callback signifying completion of successful connection """
        # tickers = ["GCQ8"]
        for ticker in self.tickers:
            monitor = Monitor(ticker, self)
            monitor.create_children(1)

            next_req_id = self.get_next_req_id()
            self.req_id_to_monitor_map[next_req_id] = monitor
            self.request_market_data(next_req_id, monitor.ticker)
            
            self.monitors.append(monitor)


    def request_market_data(self, req_id, ticker):
        if self.live_mode:
            self.reqMktData(req_id, util.get_contract(ticker), "", False, False, [])
        else:
            with open(self.input_file, "r") as f:
                data = json.load(f)

            for time, price in data:
                self.current_tick_time[ticker] = time
                self.current_tick_price[ticker] = price
                self.tickPrice(self.current_req_id, 4, price, {})
            
            for req_id, monitor in self.req_id_to_monitor_map.items():
                monitor.close()


    def tickPrice(self, reqId, tickType, price:float, attrib):
        super().tickPrice(reqId, tickType, price, attrib)

        if price <= 0:
            logging.info(f"Returned 0 or under 0 price: '{price}', for ticker {self.ticker}")
            return

        # tickType:
        # bid price = 1
        # ask price = 2
        # last traded price = 4

        monitor = self.req_id_to_monitor_map[reqId]
        if self.live_mode:
            time = time.time()
            self.current_tick_time[monitor.ticker] = time
            self.current_tick_price[monitor.ticker] = price
            monitor.price_change(tickType, price, time)
        else:
            self.transmit_order(monitor, price=price)
            for child_monitor in monitor.child_test_monitors:
                self.transmit_order(child_monitor, price=price)
            monitor.price_change(tickType, price, self.current_tick_time[monitor.ticker])


    def wait_for_readiness(self):
        if self.live_mode:
            for i in range(120):
                if self.current_order_id is not None:
                    break
                else:
                    time.sleep(1)

            if self.current_order_id is not None:
                print("IB Ready")
            else:
                # raise exception ?
                print("IB was not reported ready after 120 seconds")
        else:
            self.current_order_id = 0


    # callback to client.reqIds(-1)
    # def nextValidId(self, orderId:int):
    #     super().nextValidId(orderId)
    #     self.current_order_id = orderId

    # App functions
    def get_next_order_id(self):
        self.current_order_id += 1
        return self.current_order_id

    def get_next_req_id(self):
        self.current_req_id += 1
        return self.current_req_id


    # Orders
    def place_order(self, monitor, action, quantity, price=0, order_id=None, test=False):
        with self.place_order_lock:
            order = Order()
            if price == 0:
                order.orderType = "MKT"
            else:    
                order.orderType = "LMT"
                order.lmtPrice = price
            order.totalQuantity = quantity
            order.action = action # "BUY"|"SELL"

            if order_id is None:
                order_id = self.get_next_order_id()
                if monitor in self.order_id_to_monitor_map.values():
                    assert False
                self.order_id_to_monitor_map[order_id] = monitor

            if not self.live_mode or test:
                self.orderStatus(order_id, "Submitted", 1, self.remaining.get(monitor, 0), 0, 0, 0, 0, 0, "")
                self.transmit_order(monitor, order)
            else:
                self.placeOrder(order_id, util.get_contract(monitor.ticker), order)


    def cancel_order(self, order_id, test=False):
        if not self.live_mode or test:
            monitor = self.order_id_to_monitor_map[order_id]
            self.orderStatus(order_id, "Cancelled", 1, self.remaining.get(monitor, 0), 0, 0, 0, 0, 0, "")
            self.active_order[monitor] = None
        else:
            self.cancelOrder(order_id)


    def orderStatus(self, orderId, status, filled,
                    remaining, avgFillPrice, permId,
                    parentId, lastFillPrice, clientId,
                    whyHeld):
        super().orderStatus(orderId, status, filled, remaining, avgFillPrice, permId, parentId, 
            lastFillPrice, clientId, whyHeld)

        monitor = self.order_id_to_monitor_map[orderId]
        if status == "Filled" or status == "Cancelled":
            self.order_id_to_monitor_map.pop(orderId)
        if self.live_mode:
            monitor.order_change(orderId, status, remaining, lastFillPrice, time.time())
        else:
            monitor.order_change(orderId, status, remaining, lastFillPrice, self.current_tick_time[monitor.ticker])

    
    def openOrder(self, orderId, contract, order,
                  orderState):
        super().openOrder(orderId, contract, order, orderState)

        # self.order_id_to_monitor_map[orderId].order_change()

    
    # ++++++++++++++ PRIVATE +++++++++++++++++++

    # Only for load mode
    def transmit_order(self, monitor, order=None, price=0):
        if order is None:
            # lmt order created before, assigned to self.active_order and executing based on price parameter
            if self.active_order.get(monitor) is None:
                return
            if self.active_order[monitor].action == "BUY":
                if price <= self.active_order[monitor].lmtPrice:
                    self.remaining[monitor] = self.remaining.get(monitor, 0) + self.active_order[monitor].totalQuantity
                    self.orderStatus(self.monitor_to_order_id_map(monitor), "Filled", 1, self.remaining[monitor], price, 0, 0, price, 0, "")
                    self.active_order[monitor] = None
            elif self.active_order[monitor].action == "SELL":
                if price >= self.active_order[monitor].lmtPrice:
                    self.remaining[monitor] = self.remaining.get(monitor, 0) - self.active_order[monitor].totalQuantity
                    self.orderStatus(self.monitor_to_order_id_map(monitor), "Filled", 1, self.remaining[monitor], price, 0, 0, price, 0, "")
                    self.active_order[monitor] = None
        elif (order.orderType == "MKT") or (order.orderType == "LMT" and order.lmtPrice == self.current_tick_price[monitor.ticker]):
            if order.action == "BUY":
                self.remaining[monitor] = self.remaining.get(monitor, 0) + order.totalQuantity
                self.orderStatus(self.monitor_to_order_id_map(monitor), "Filled", 1, self.remaining[monitor],
                    self.current_tick_price[monitor.ticker], 0, 0, self.current_tick_price[monitor.ticker], 0, "")
            elif order.action == "SELL":
                self.remaining[monitor] = self.remaining.get(monitor, 0) - order.totalQuantity
                self.orderStatus(self.monitor_to_order_id_map(monitor), "Filled", 1, self.remaining[monitor],
                    self.current_tick_price[monitor.ticker], 0, 0, self.current_tick_price[monitor.ticker], 0, "")
        else:
            # Order is lmt, so just assigning for later execution
            self.active_order[monitor] = order


    def monitor_to_order_id_map(self, monitor):
        for order_id, dmonitor in self.order_id_to_monitor_map.items():
            if monitor == dmonitor:
                return order_id


    def keyboardInterrupt(self):
        self.clear_all()


    def clear_all(self):
        print("Clearing all...")
        
        for req_id, monitor in self.req_id_to_monitor_map.items():
            self.cancelMktData(req_id)
            monitor.close()
            time.sleep(3)
        self.disconnect()

        print("Finished clearing.")