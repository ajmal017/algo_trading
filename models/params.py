import random
import statistics

class Params:
    def __init__(self, monitor):
        self.m = monitor
        self.set_basic_parameters()
        self.set_options()
        self.set_defaults()


    def set_basic_parameters(self):
        if self.m.ticker[0:2] == "ES":
            self.tick_price = 0.25
            self.price_precision = 2
        
        elif self.m.ticker[0:2] == "NQ":
            self.tick_price = 0.25
            self.price_precision = 2
        
        elif self.m.ticker[0:2] == "YM":
            self.tick_price = 1
            self.price_precision = 2
        
        elif self.m.ticker[0:2] == "CL":
            self.tick_price = 0.01
            self.price_precision = 2
        
        elif self.m.ticker[0:2] == "NG":
            self.tick_price = 0.001
            self.price_precision = 3
        
        elif self.m.ticker[0:2] == "GC":
            self.tick_price = 0.10
            self.price_precision = 2
        
        elif self.m.ticker[0:2] == "HG":
            self.tick_price = 0.0005
            self.price_precision = 4
        
        elif self.m.ticker[0:2] == "SI":
            self.tick_price = 0.005
            self.price_precision = 3
        
        elif self.m.ticker[0:3] == "EUR":
            self.tick_price = 0.00005
            self.price_precision = 5
        
        elif self.m.ticker[0:3] == "JPY":
            self.tick_price = 0.0000005
            self.price_precision = 7
        
        elif self.m.ticker[0:2] == "ZB":
            self.tick_price = 0.03125
            self.price_precision = 5
        
        elif self.m.ticker[0:2] == "ZN":
            self.tick_price = 0.015625
            self.price_precision = 6
        
        elif self.m.ticker[0:2] == "ZC":
            self.tick_price = 0.25
            self.price_precision = 2
        
        elif self.m.ticker[0:2] == "ZS":
            self.tick_price = 0.25
            self.price_precision = 2

        self.max_breaking_price_changes_list = 50
        self.min_breaking_price_changes_list = 20


    # performance parameters with options
    # if parameter is set None, means that should be resolved in the specific part of the code, probably in Decision class.
    # if parameter is set 'calc', it is calculated in the property part
    # first value of tuple is default value
    def set_options(self):
        self.primary_look_back_time_options = (900, 1800, 3600, 7200) # secs # ideal for ES, 600-900 for all others
        
        # Stop time
        self.breaking_stop_time_options = (60, 20, 40, 80, 120) # secs
        self.speeding_stop_time_options = (10, 5, 20, 30) # secs

        # Breaking
        self._min_breaking_price_changes_options = (5, 3, 10, 15, 'calc') # times
        self.breaking_up_down_ratio_options = (1.0, 1.5, 2.0)
        self.min_breaking_range_options = (2, 4)

        # Speeding
        self.speeding_time_options = (5, 10, 20) # secs
        self.time_speeding_points_length_options = (4, 3, 6)
        self.speed_min_max_win_loose_ticks_options = ((2, 6), (3, 6), (4, 8))

        # Stop values
        self.reached_first_target_break_options = (1, 2, 4)
        self.made_two_break_options = (3, 2, 5)
        self.min_max_loose_ticks_options = ((3, 6), (2, 6), (4, 8), (5, 10)) # could replace speed_min_max_win_loose_ticks_options
        self.reversal_addition_break_options = (1, 2, 4)

        self._max_winning_ticks_options = (None, 3, 4)

        self.density_min_data_options = (6, 10, 15)

        # Scores
        self.breaking_price_changes_score_options = (4, 3, 2)
        self.duration_score_options = (2, 1, 0)
        self.in_line_score_options = (2, 1)
        self.trend_two_score_options = (2, 1)
        self.in_density_direction_score_options = (2, 1, 3)
        self.out_density_direction_score_options = (2, 1, 3)
        self.advantage_score_options = (2, 1, 3)


    # set the default value as the first of the options
    def set_defaults(self):
        current_vars = dict(vars(self))
        for variable, value in current_vars.items():
            if variable[-8:] == '_options':
                setattr(self, variable.replace('_options', ''), value[0])


    def randomize(self):
        for variable, value in vars(self).items():
            if variable[-8:] == '_options':
                setattr(self, variable.replace('_options', ''), random.choice(value))


    @property
    def min_breaking_price_changes(self):
        if self._min_breaking_price_changes == 'calc':
            if len(self.m.breaking.price_changes_list) < self.min_breaking_price_changes_list:
                return self.default('_min_breaking_price_changes')
            else:
                try:
                    return statistics.mode(self.m.breaking.price_changes_list)
                except statistics.StatisticsError:
                    return self.default('_min_breaking_price_changes')
        else:
            return self._min_breaking_price_changes


    @property
    def max_winning_ticks(self):
        if self._max_winning_ticks == 'calc':
            if len(self.m.results.data) < 20:
                return self.default('_max_winning_ticks')
            else:
                try:
                    return statistics.mode(r.fantasy_pnl for r in self.m.results.data)
                except statistics.StatisticsError:
                    return self.default('_max_winning_ticks')
        else:
            return self._max_winning_ticks


    def default(self, attr):
        return getattr(self, attr + '_options')[0]


    def state_str(self):
        output = "  PARAMETERS:\n"
        for variable, value in vars(self).items():
            if variable[-8:] == '_options':
                output += f"    {variable.replace('_options', '')}: {getattr(self, variable.replace('_options', ''))}\n"
        return output