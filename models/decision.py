from functools import lru_cache

import gvars
from lib import util

class Decision:
    def __init__(self, monitor, density_data = None, time_speeding_points = None):
        assert (density_data is not None or time_speeding_points is not None)
        self.m = monitor
        self.density_data = density_data
        self.time_speeding_points = time_speeding_points

        self.direction = None # type: int
        self.last_price = None # type: float
        
        self.breaking_duration_ok = False
        self.breaking_price_changes = 0
        self.in_line = 0
        self.trend_two = 0

        self.adjusting_ticks = None # type: int

        self.trend_pattern = gvars.TREND_PATTERN['neutral']

        self._scores_output = ""


    def is_breaking_in_range(self):
        return self.density_data is not None


    def is_speeding(self):
        return self.time_speeding_points is not None


    @lru_cache(maxsize=None)
    def should(self):
        decision = ''
        if self.is_breaking_in_range():
            total_score = sum(self.all_scores())
            if total_score >= 6:
                self.adjusting_ticks = 1
                if self.direction == 1:
                    decision = 'buy'
                elif self.direction == -1:
                    decision = 'sell'
        elif self.is_speeding():
            self.set_speeding_data()
            self.adjusting_ticks = 0
            if self.direction == 1:
                decision = 'buy'
            elif self.direction == -1:
                decision = 'sell'
        return decision


    def should_close(self):
        trending_break_ticks = self.trending_break_ticks()
        gvars.datalog_buffer[self.m.ticker] += (f"    decision.should_close.trending_break_ticks: {trending_break_ticks}\n")

        # Time stop
        time_since_transaction = self.m.last_time() - self.ap.transaction_time
        if time_since_transaction > self.break_time():
            min_max = self.m.min_max_since(self.break_time())
            gvars.datalog_buffer[self.m.ticker] += (f"    decision.should_close.min_max[1].price: {min_max[1].price}\n")
            gvars.datalog_buffer[self.m.ticker] += (f"    decision.should_close.min_max[0].price: {min_max[0].price}\n")
            if self.m.ticks(min_max[1].price - min_max[0].price) <= trending_break_ticks:
                return True
        
        # Price stop
        if self.m.ticks(abs(self.m.last_price() - self.ap.trending_price())) >= trending_break_ticks:
            return True

        if self.reached_maximum():
            return True

        return False


    def all_scores(self):
        scores = []
        for funct_name, funct_obj in vars(type(self)).items():
            if funct_name[-6:] == '_score':
                score = funct_obj(self)
                self._scores_output += (f"          {funct_name}: {score}\n")
                scores.append(score)
        return scores


    # ++++++++ SCORES +++++++++++++

    # ++++++++ Breaking +++++++++++
    
    def breaking_price_changes_score(self):
        score = 0
        if self.breaking_price_changes > self.m.prm.min_breaking_price_changes:
            score += 4
            if self.breaking_duration_ok:
                score += 2
        return score


    def in_line_score(self):
        return 2 if self.in_line >= 3 else 0


    def trend_two_score(self):
        return 2 if self.trend_two > 0 else 0


    def density_direction_score(self):
        if not self.is_breaking_in_range():
            return 0
        score = 0
        if self.density_data.trend_density_direction in (gvars.DENSITY_DIRECTION['in'], gvars.DENSITY_DIRECTION['out-in']):
            score += 2
            if self.density_data.anti_trend_density_direction in (gvars.DENSITY_DIRECTION['out'], gvars.DENSITY_DIRECTION['out-edge']):
                score += 2
                self.trend_pattern = gvars.TREND_PATTERN['reversal']
        return score


    def advantage_score(self):
        if not self.is_breaking_in_range():
            return 0
        score = 0
        if self.to_win_ticks() <= 1:
            score += -1000 # Big number so it doesn't place the trade
        if self.to_win_ticks() - self.to_loose_ticks() >= 1:
            score += 2
        return score

    # +++++++++++++++++++++++++++++

    # +++++++++++++++++++++++++++++


    def set_speeding_data(self):
        if len(self.time_speeding_points) == 1:
            return
        if -1 <= self.time_speeding_points[-1].ticks <= 1:
            sum_ticks = sum(tsp.ticks for tsp in self.time_speeding_points)
            ini_ticks = self.time_speeding_points[0].ticks
            if ini_ticks > 0:
                if sum_ticks >= ini_ticks * 0.75:
                    self.direction = -1
                    self.trend_pattern = gvars.TREND_PATTERN['reversal']
            elif ini_ticks < 0:
                if sum_ticks <= ini_ticks * 0.75:
                    self.direction = 1
                    self.trend_pattern = gvars.TREND_PATTERN['reversal']
        elif len(self.time_speeding_points) == self.m.prm.time_speeding_points_length:
            if all(tsp.ticks >= 2 for tsp in self.time_speeding_points):
                self.direction = 1
                self.trend_pattern = gvars.TREND_PATTERN['follow']
            elif all(tsp.ticks <= -2 for tsp in self.time_speeding_points):
                self.direction = -1
                self.trend_pattern = gvars.TREND_PATTERN['follow']


    def trending_break_ticks(self):
        break_ticks = None
        if self.is_breaking_in_range():
            trend_ticks = self.m.ticks(abs(self.density_data.trend_tuple[1] - self.ap.trending_price()))
            anti_trend_ticks = self.m.ticks(abs(self.ap.transaction_price - self.density_data.anti_trend_tuple[0]))

            # break_ticks = min(trend_ticks, anti_trend_ticks)
            if self.direction * self.m.ticks(self.ap.trending_price() - self.density_data.trend_tuple[1]) >= 0:
                break_ticks = 1
            elif self.direction * self.m.ticks(self.ap.trending_price() - self.ap.transaction_price) >= 2:
                break_ticks = 3
            else:
                break_ticks = util.value_or_min_max(anti_trend_ticks, (3, 6))
            # or break_ticks = fixed 3 ?
        elif self.is_speeding():
            break_ticks = self.to_loose_ticks()
        break_ticks += 1 if self.trend_pattern == gvars.TREND_PATTERN['reversal'] else 0
        return break_ticks


    def reached_maximum(self):
        if self.is_breaking_in_range():
            if self.direction * (self.m.last_price() - self.m.mid_price(self.density_data.trend_tuple[1:3])) >= 0:
                return True
            else:
                return False
        elif self.is_speeding():
            if self.direction * self.m.ticks(self.ap.trending_price() - self.ap.transaction_price) >= self.to_win_ticks():
                return True
            else:
                return False


    @lru_cache(maxsize=None)
    def to_win_ticks(self):
        if self.is_breaking_in_range():
            return self.m.ticks(abs(self.density_data.trend_tuple[1] - self.last_price))
        elif self.is_speeding():
            return util.value_or_min_max(
                    abs(round(sum(tsp.ticks for tsp in self.time_speeding_points) * 0.75)),
                    self.m.prm.speed_min_max_win_loose_ticks)


    @lru_cache(maxsize=None)
    def to_loose_ticks(self):
        if self.is_breaking_in_range():
            return self.m.ticks(abs(self.density_data.anti_trend_tuple[0] - self.last_price))
        elif self.is_speeding():
            return util.value_or_min_max(
                    round(self.to_win_ticks() * 0.75),
                    self.m.prm.speed_min_max_win_loose_ticks)


    @lru_cache(maxsize=None)
    def break_time(self):
        if self.is_breaking_in_range():
            return self.m.prm.breaking_stop_time
        elif self.is_speeding():
            return self.m.prm.speeding_stop_time


    @property
    def ap(self):
        return self.m.position.ap


    def state_str(self):
        output = ""
        if self.is_breaking_in_range():
            output += "        Is breaking:\n"
        elif self.is_speeding():
            output += "        Is speeding:\n"
        output += (
            "        Variables:\n"
            "          breaking_price_changes: {}\n"
            "          breaking_duration_ok: {}\n"
            "          in_line: {}\n"
            "          trend_two: {}\n"
        ).format(self.breaking_price_changes, self.breaking_duration_ok, self.in_line, self.trend_two)
        output += "        Scores:\n"
        output += self._scores_output
        return output