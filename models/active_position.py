import gvars
class ActivePosition:
    def __init__(self, monitor, position, fill_price, fill_time):
        self.m = monitor
        self.p = position
        
        self.direction = self.p.direction()
        assert self.direction != 0
        self.transaction_price = self.up_trending_price = self.down_trending_price = fill_price
        self.transaction_time = fill_time


    def price_change(self):
        if self.m.last_price() > self.up_trending_price:
            self.up_trending_price = self.m.last_price()
        elif self.m.last_price() < self.down_trending_price:
            self.down_trending_price = self.m.last_price()


    def append_results(self, fill_price, fill_time):
        self.m.results.append(
            pnl = round(self.direction * (fill_price - self.transaction_price),
                self.m.prm.price_precision),
            fantasy_pnl = round(self.direction * (self.trending_price() - self.transaction_price),
                self.m.prm.price_precision),
            fluctuation = round(self.up_trending_price - self.down_trending_price,
                self.m.prm.price_precision),
            reversal = round(abs(self.transaction_price - self.trending_price(False)),
                self.m.prm.price_precision),
            order_time = self.p.order_time,
            start_time = self.transaction_time,
            end_time = fill_time
        )


    def trending_price(self, straight=True):
        if straight:
            return self.up_trending_price if self.direction == 1 else self.down_trending_price
        else:
            return self.down_trending_price if self.direction == 1 else self.up_trending_price


    def state_str(self):
        output = (
            f"  Active Position {self.direction}:\n"
            f"    transaction_price: {self.transaction_price:.{self.m.prm.price_precision}f}\n"
            f"    transaction_time: {self.transaction_time:.4f}\n"
            f"    up_trending_price: {self.up_trending_price:.{self.m.prm.price_precision}f}\n"
            f"    down_trending_price: {self.down_trending_price:.{self.m.prm.price_precision}f}\n"
        )
        return output
