import gvars
from lib import util, core

class Density:
    def __init__(self, monitor):
        self.m = monitor
        self.list_dps = []
        self.initialize_interval_variables()
        self.in_position = False

        self.build_dps()

        # Private
        self._previous_price_data = []
        self.min_higher_area = None # type: int
        self.max_lower_area = None # type: int


    def initialize_interval_variables(self):
        self.current_dp = None
        self.up_density_direction = None # type: int
        self.down_density_direction = None # type: int

        self.up_interval_max = None # type: float
        self.up_interval_min = None # type: float
        self.current_interval_max = None # type: float
        self.current_interval_min = None # type: float
        self.down_interval_max = None # type: float
        self.down_interval_min = None # type: float
        

    def price_change(self):
        # Update structure
        self.update_dps()

        # Calculations
        if len(self.list_dps) >= util.value_or_min_max(self.m.prm.density_division, (10, 20)):
            self.set_percentagiles() and self.update_intervals()
            # self.update_heights() # Not in use now
            # self.update_intervals()
        else:
            self.initialize_interval_variables()


    def build_dps(self):
        data = self.m.data_since(self.m.prm.primary_look_back_time)
        dict_dps = {}
        for cdp in data:
            if cdp.price not in dict_dps:
                dict_dps[cdp.price] = DensityPoint(cdp.price)
            dict_dps[cdp.price].duration += cdp.duration
        self.list_dps = list(dict_dps.values())


    def update_dps(self):
        self.in_position = False

        data = self.m.data_since(self.m.prm.primary_look_back_time)
        
        # Add 2 newest prices
        for cdp in data[-2:]:
            dp = core.find(lambda dp: dp.price == cdp.price, self.list_dps)
            if dp is None:
                dp = DensityPoint(cdp.price)
                self.list_dps.append(dp)
            dp.duration += cdp.duration

        if (data[-1].time - data[0].time < self.m.prm.primary_look_back_time - 300 and 
                len(self._previous_price_data) == 0):
            return

        # Remove old elements
        for cdp in self._previous_price_data:
            if cdp == data[0]: # Pointer comparison
                break
            dp_index = core.index(lambda dp: dp.price == cdp.price, self.list_dps)
            if dp_index is None:
                continue
            dp = self.list_dps[dp_index]
            dp.duration -= cdp.duration
            if dp.price != self.m.last_price() and dp.duration < 0.001: # not last and duration close to zero (floating point errors)
                self.list_dps.pop(dp_index)
        self._previous_price_data = data


    def set_percentagiles(self):
        self.list_dps.sort(key=lambda dp: dp.duration)

        # Set dpercentage
        total_duration = sum(map(lambda dp: dp.duration, self.list_dps))
        for index, dp in enumerate(self.list_dps):
            dp.dpercentage = (dp.duration / total_duration) * 100

        # set dpercentile 
        dpercentile_coefficient = 100.0 / max(self.list_dps, key=lambda dp: dp.dpercentage).dpercentage
        for dp in self.list_dps:
            dp.dpercentile = round(dp.dpercentage * dpercentile_coefficient)

        # set first_quarter and last_quarter dpercentiles
        division = round((len(self.list_dps) - 1) / self.m.prm.density_division)
        self.min_higher_area = self.list_dps[(len(self.list_dps) - 1) - division].dpercentile
        self.max_lower_area = self.list_dps[division].dpercentile
        return True # Signals that the next method can be executed


    def update_heights(self):
        # This method assumes that self.list_dps is ordered by price
        if len(self._previous_price_data) == 0:
            return

        self.list_dps.sort(key=lambda dp: dp.price)

        for i in range(len(self.list_dps)):
            self.list_dps[i].height = gvars.HEIGHT['mid']
        unreal_consecutives = 0
        trend = 1
        for i in range(len(self.list_dps)):
            if i == 0:
                j = i
            else:
                if self.list_dps[j].dpercentile < self.list_dps[i].dpercentile:
                    if trend == -1:
                        if (0 < self.list_dps[i].dpercentile - self.list_dps[j].dpercentile < 10) and unreal_consecutives < 3:
                            # Unreal change
                            unreal_consecutives += 1
                        else:
                            # Real change
                            self.list_dps[i-1].height = gvars.HEIGHT['min']
                            for k in range(j, i-1):
                                self.list_dps[k].height = gvars.HEIGHT['min']
                            unreal_consecutives = 0
                            j = i
                            trend = 1
                    else:
                        unreal_consecutives = 0
                        j = i
                elif self.list_dps[j].dpercentile > self.list_dps[i].dpercentile:
                    if trend == 1:
                        if (0 < self.list_dps[j].dpercentile - self.list_dps[i].dpercentile < 10) and unreal_consecutives < 3:
                            # Unreal change
                            unreal_consecutives += 1
                        else:
                            # Real change
                            self.list_dps[i-1].height = gvars.HEIGHT['max']
                            for k in range(j, i-1):
                                self.list_dps[k].height = gvars.HEIGHT['max']
                            unreal_consecutives = 0
                            j = i
                            trend = -1
                    else:
                        unreal_consecutives = 0
                        j = i


    def update_intervals(self):
        # This method assumes that self.list_dps is ordered by price
        if len(self._previous_price_data) == 0:
            return

        self.list_dps.sort(key=lambda dp: dp.price)

        current_dp_index = core.index(lambda dp: dp.price == self.m.last_price(), self.list_dps)
        self.current_dp = self.list_dps[current_dp_index]

        if self.current_dp.dpercentile <= self.max_lower_area:
            self.up_density_direction = self.down_density_direction = gvars.DENSITY_DIRECTION['in']
        elif self.current_dp.dpercentile >= self.min_higher_area:
            self.up_density_direction = self.down_density_direction = gvars.DENSITY_DIRECTION['out']
        else:
            return

        # Set interval variables

        self.up_interval_max = None # type: float
        self.up_interval_min = None # type: float
        self.current_interval_max = None # type: float
        self.current_interval_min = None # type: float
        self.down_interval_max = None # type: float
        self.down_interval_min = None # type: float

        if self.up_density_direction == gvars.DENSITY_DIRECTION['out']:

            filled_position = 0
            for i in range(current_dp_index + 1, len(self.list_dps)): # up part
                
                if self.list_dps[i].dpercentile < self.min_higher_area and filled_position == 0:
                    self.current_interval_max = self.list_dps[i-1].price
                    filled_position = 1
                if self.list_dps[i].dpercentile >= self.min_higher_area and filled_position == 1:
                    self.up_interval_min = self.up_interval_max = self.list_dps[i].price
                    self.up_density_direction = gvars.DENSITY_DIRECTION['out-in']
                    break
                if self.list_dps[i].dpercentile <= self.max_lower_area and filled_position == 1:
                    self.up_interval_min = self.list_dps[i].price
                    filled_position = 2
                if self.list_dps[i].dpercentile > self.max_lower_area and filled_position == 2:
                    self.up_interval_max = self.list_dps[i-1].price
                    filled_position = 3
                    break

            filled_position = 0
            for i in reversed(range(current_dp_index)): # down part
            
                if self.list_dps[i].dpercentile < self.min_higher_area and filled_position == 0:
                    self.current_interval_min = self.list_dps[i+1].price
                    filled_position = 1
                if self.list_dps[i].dpercentile >= self.min_higher_area and filled_position == 1:
                    self.down_interval_max = self.down_interval_min = self.list_dps[i].price
                    self.down_density_direction = gvars.DENSITY_DIRECTION['out-in']
                    break
                if self.list_dps[i].dpercentile <= self.max_lower_area and filled_position == 1:
                    self.down_interval_max = self.list_dps[i].price
                    filled_position = 2
                if self.list_dps[i].dpercentile > self.max_lower_area and filled_position == 2:
                    self.down_interval_min = self.list_dps[i+1].price
                    filled_position = 3
                    break

        elif self.up_density_direction == gvars.DENSITY_DIRECTION['in']:

            filled_position = 0
            for i in range(current_dp_index + 1, len(self.list_dps)): # up part

                if self.list_dps[i].dpercentile > self.max_lower_area and filled_position == 0:
                    self.current_interval_max = self.list_dps[i-1].price
                    filled_position = 1
                if self.list_dps[i].dpercentile <= self.max_lower_area and filled_position == 1:
                    self.up_interval_min = self.up_interval_max = self.list_dps[i].price
                    self.up_density_direction = gvars.DENSITY_DIRECTION['in-out']
                    break
                if self.list_dps[i].dpercentile >= self.min_higher_area and filled_position == 1:
                    self.up_interval_min = self.list_dps[i].price
                    filled_position = 2
                if self.list_dps[i].dpercentile < self.min_higher_area and filled_position == 2:
                    self.up_interval_max = self.list_dps[i-1].price
                    filled_position = 3
                    break

            filled_position = 0
            for i in reversed(range(current_dp_index)): # down part

                if self.list_dps[i].dpercentile > self.max_lower_area and filled_position == 0:
                    self.current_interval_min = self.list_dps[i+1].price
                    filled_position = 1
                if self.list_dps[i].dpercentile <= self.max_lower_area and filled_position == 1:
                    self.down_interval_max = self.down_interval_min = self.list_dps[i].price
                    self.down_density_direction = gvars.DENSITY_DIRECTION['in-out']
                    break
                if self.list_dps[i].dpercentile >= self.min_higher_area and filled_position == 1:
                    self.down_interval_max = self.list_dps[i].price
                    filled_position = 2
                if self.list_dps[i].dpercentile < self.min_higher_area and filled_position == 2:
                    self.down_interval_min = self.list_dps[i+1].price
                    filled_position = 3
                    break

        if self.up_interval_max == None:
            self.up_interval_max = self.list_dps[-1].price
        if self.up_interval_min == None:
            self.up_interval_min = self.list_dps[-1].price
            self.up_density_direction = gvars.DENSITY_DIRECTION['out-edge']
        if self.current_interval_max == None:
            self.current_interval_max = self.list_dps[-1].price
        if self.current_interval_min == None:
            self.current_interval_min = self.list_dps[0].price
        if self.down_interval_max == None:
            self.down_interval_max = self.list_dps[0].price
            self.down_density_direction = gvars.DENSITY_DIRECTION['out-edge']
        if self.down_interval_min == None:
            self.down_interval_min = self.list_dps[0].price

        self.in_position = True


    def up_down_ratio(self, direction):
        mid_part = self.current_interval_max - self.current_interval_min
        if mid_part == 0:
            mid_part = self.m.prm.tick_price
        if direction == 1:
            up_part = self.up_interval_min - self.current_interval_max
            return up_part / mid_part
        else:
            down_part = self.current_interval_min - self.down_interval_max
            return down_part / mid_part


    def interval_tuples(self, direction):
        assert direction in (1, -1)
        up_tuple = (self.current_interval_max, self.up_interval_min, self.up_interval_max)
        down_tuple = (self.current_interval_min, self.down_interval_max, self.down_interval_min)
        if direction == 1:
            return (up_tuple, down_tuple)
        else:
            return (down_tuple, up_tuple)


    def density_direction(self, direction):
        assert direction in (1, -1)
        if direction == 1:
            return (self.up_density_direction, self.down_density_direction)
        else:
            return (self.down_density_direction, self.up_density_direction)


    def get_data(self, direction):
        dd = DensityData()
        dd.trend_tuple, dd.anti_trend_tuple = self.interval_tuples(direction)
        dd.trend_density_direction, dd.anti_trend_density_direction = self.density_direction(direction)
        dd.up_interval_max = self.up_interval_max
        dd.up_interval_min = self.up_interval_min
        dd.current_interval_max = self.current_interval_max
        dd.current_interval_min = self.current_interval_min
        dd.down_interval_max = self.down_interval_max
        dd.down_interval_min = self.down_interval_min
        return dd


    def values_set(self):
        # Using self.up_interval_max as representative of setting all the values in update_intervals()
        return self.up_interval_max is not None


    def state_str(self):
        if not self.values_set():
            return ""
        output = "  DENSITY:\n"
        if self.in_position:
            for dp in reversed(self.list_dps):
                if self.down_interval_min <= dp.price <= self.up_interval_max:
                    output += f"    {dp.state_str(self.m.prm.price_precision)}\n"
        output += (
            f"    in_position: {self.in_position}\n"
            f"    min_higher_area: {self.min_higher_area}\n"
            f"    max_lower_area: {self.max_lower_area}\n"
            f"    up_density_direction: {gvars.DENSITY_DIRECTION_INV[self.up_density_direction]}\n"
            f"    down_density_direction: {gvars.DENSITY_DIRECTION_INV[self.down_density_direction]}\n"
        )
        output += (
            "    {:.{price_precision}f}\n"
            "    {:.{price_precision}f}\n"
            "    {:.{price_precision}f}\n"
        ).format(self.up_interval_max, self.up_interval_min, self.current_interval_max,
            price_precision = self.m.prm.price_precision if self.m is not None else 5)
        if self.current_dp is not None:
            output += f"    current_dp: {self.current_dp.state_str(self.m.prm.price_precision)}\n"
        else:
            output += "    -\n"
        output += (
            "    {:.{price_precision}f}\n"
            "    {:.{price_precision}f}\n"
            "    {:.{price_precision}f}\n"
        ).format(self.current_interval_min, self.down_interval_max, self.down_interval_min,
            price_precision = self.m.prm.price_precision if self.m is not None else 5)
        return output


class DensityPoint:
    def __init__(self, price):
        self.price = price
        self.duration = 0
        self.dpercentage = None # type: int
        self.dpercentile = None # type: int
        self.height = gvars.HEIGHT['mid']

    def state_str(self, price_precision = 2):
        output = (
            "price: {:.{price_precision}f}, "
            "duration: {:.2f}, "
            "dpercentage: {:.2f}, "
            "dpercentile: {}, "
            "height: {}"
        ).format(self.price, self.duration,
            self.dpercentage, self.dpercentile, self.height,
            price_precision = price_precision)
        return output


class DensityData:
    def __init__(self):
        self.trend_tuple = self.anti_trend_tuple = None
        self.trend_density_direction = self.anti_trend_density_direction = None
        
        self.up_interval_max = None # type: int
        self.up_interval_min = None # type: int
        self.current_interval_max = None # type: int
        self.current_interval_min = None # type: int
        self.down_interval_max = None # type: int
        self.down_interval_min = None # type: int

    def state_str(self, price_precision = 2):
        output = (
            "  Density Data:\n"
            f"    trend_density_direction: {gvars.DENSITY_DIRECTION_INV[self.trend_density_direction]}\n"
            f"    anti_trend_density_direction: {gvars.DENSITY_DIRECTION_INV[self.anti_trend_density_direction]}\n"
            f"    {self.up_interval_max:.{price_precision}f}\n"
            f"    {self.up_interval_min:.{price_precision}f}\n"
            f"    {self.current_interval_max:.{price_precision}f}\n"
            f"    -\n"
            f"    {self.current_interval_min:.{price_precision}f}\n"
            f"    {self.down_interval_max:.{price_precision}f}\n"
            f"    {self.down_interval_min:.{price_precision}f}\n"
        )
        return output
