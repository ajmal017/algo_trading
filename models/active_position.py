import gvars
class ActivePosition:
    def __init__(self, position, monitor):
        self.m = monitor
        self.p = position
        
        self.direction = self.p.direction()
        assert self.direction != 0
        self.up_trending_price = self.down_trending_price = self.m.last_price()
        self.transaction_time = self.m.last_time()
        self.density_data = self.m.action_density_data


    def close(self):
        self.append_results()


    def price_change(self):
        if self.m.last_price() > self.up_trending_price:
            self.up_trending_price = self.m.last_price()
        elif self.m.last_price() < self.down_trending_price:
            self.down_trending_price = self.m.last_price()


    def reached_minimum(self):
        if self.direction * (self.m.last_price() - self.density_data.anti_trend_tuple[0]) < 0:
            return True
        else:
            return False


    def reached_maximum(self):
        if self.direction * (self.m.last_price() - self.density_data.trend_tuple[1]) >= 0:
            return True
        else:
            return False

    
    def trending_stopped(self):
        time_since_transaction = self.m.last_time() - self.transaction_time
        if time_since_transaction > self.m.prm.trending_break_time:
            min_max = self.m.min_max_since(self.m.prm.trending_break_time)
            gvars.datalog_buffer[self.m.ticker] += ("    1st: Inside trending.stopped:\n")
            gvars.datalog_buffer[self.m.ticker] += (f"      min_max_1: {min_max[1].price}\n")
            gvars.datalog_buffer[self.m.ticker] += (f"      min_max_0: {min_max[0].price}\n")
            gvars.datalog_buffer[self.m.ticker] += (f"      trending_break_value: {self.trending_break_value()}\n\n")
            if self.m.ticks(min_max[1].price - min_max[0].price) <= self.trending_break_value():
                return True
        if self.m.ticks(abs(self.m.last_price() - self.trending_price())) >= self.trending_break_value():
            return True
        return False


    # +++++++ Private +++++++++


    def append_results(self):
        self.m.results.append(
            pnl = round(self.direction * (self.m.data[-2].price - self.transaction_price),
                self.m.prm.price_precision),
            fantasy_pnl = round(self.direction * (self.trending_price() - self.transaction_price),
                self.m.prm.price_precision),
            fluctuation = round(self.up_trending_price - self.down_trending_price,
                self.m.prm.price_precision),
            reversal = round(abs(self.transaction_price - self.trending_price(False)),
                self.m.prm.price_precision),
            order_time = self.p.order_time,
            start_time = self.transaction_time,
            end_time = self.m.data[-2].time
        )


    def trending_price(self, straight=True):
        if straight:
            return self.up_trending_price if self.direction == 1 else self.down_trending_price
        else:
            return self.down_trending_price if self.direction == 1 else self.up_trending_price


    @property
    def transaction_price(self):
        return self.p.order_price


    def state_str(self):
        output = (
            f"  Active Position {self.direction}:\n"
            f"    transaction_time: {self.transaction_time:.4f}\n"
            f"    up_trending_price: {self.up_trending_price:.{self.m.prm.price_precision}f}\n"
            f"    down_trending_price: {self.down_trending_price:.{self.m.prm.price_precision}f}\n"
        )
        return output


    def trending_break_value(self):
        possible_trending_break_value = self.m.ticks(abs(self.trending_price() - self.transaction_price)) / 3.0
        if possible_trending_break_value > self.m.prm.min_trending_break_value:
            return possible_trending_break_value
        else:
            return self.m.prm.min_trending_break_value
