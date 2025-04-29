from utils import (
    get_player_data,
    get_raw_fixture_data,
    get_gameweek_to_datestr_mapping,
    get_current_gameweek,
    get_raw_historic_player_stats_snap,
    logger,
    get_dynamic_horizon,
    add_extra_features,
    CURRENT_TEAM_IDS,
    update_current_team_ids
)
from constants import RAW_PLAYER_STATS_URL,CURRENT_STATS_FEATURES,ID_FEATURES,POSSIBLE_FUTURE_FEATURES,CREATED_AVG_FEATURES
import pandas
import logging
    

class DataContainer():
    
    def __init__(self,lookback_weeks = 10, range_weeks = 10,):
        self.range_weeks = range_weeks
        self.players,self.id_to_pos_map,self.raw_season_stats_snap = get_player_data()
        self.events = self.raw_season_stats_snap['events']
        self.raw_fixture_data = get_raw_fixture_data()
        self.gameweek_to_datestr_mapping = get_gameweek_to_datestr_mapping(self.events)
        self.current_gameweek = get_current_gameweek(self.events)
        self.start_gw = self.current_gameweek - lookback_weeks
        self.end_gw = self.start_gw + range_weeks
        self.range_historic_player_stats_snap = self.get_range_historic_player_stats_snap(self.start_gw, self.end_gw)       
    
    @logger
    def get_range_historic_player_stats_snap(self,start_gw,end_gw):
        """
        Fetches historic player statistics snapshot from the web archive for a given date.

        Args:
            date_str (str): The date string in 'YYYYMMDD' format to specify the snapshot date. Defaults to '20250331'.

        Returns:
            dict: The JSON-decoded response containing historic player stats.
        """

        range_historic_player_stats_snap = {}
        for i in range(start_gw,end_gw):
            date_str = self.gameweek_to_datestr_mapping[i]
            try:
                range_historic_player_stats_snap[i] = get_raw_historic_player_stats_snap(date_str)
            except Exception as e:
                print(f"Failed to fetch data: {e}, URL: https://web.archive.org/web/{date_str}/{RAW_PLAYER_STATS_URL}")
        
        return range_historic_player_stats_snap

class DataProcessor():
    
    def __init__( self, data_obj=None, features=CURRENT_STATS_FEATURES+POSSIBLE_FUTURE_FEATURES+ID_FEATURES+CREATED_AVG_FEATURES,horizon = 'dynamic', next_week_pred = False):
        self.data_obj = data_obj
        self.next_week_pred = next_week_pred
        self.features = features
        self.horizon = horizon
        self.required_features = ID_FEATURES
        self.training_data  = self.get_training_data()    
     
    @logger
    def get_training_data( self,):
        def get_data(gw,snapshot=None,snapshot_dict=None):
            rolling_horizon = get_dynamic_horizon(gw, 38, max_horizon=self.data_obj.range_weeks) if self.horizon == 'dynamic' else self.horizon
            last_gw = min(gw + rolling_horizon, self.data_obj.end_gw)
            if last_gw <= gw:  # Redundant safety check
                return None,None
            if snapshot is None:
                snapshot_dict = self.data_obj.range_historic_player_stats_snap[gw]
                snapshot,_,_ = get_player_data(snap=snapshot_dict,gw=gw)
                snapshot.loc[:,["gw","last_gw"]] = [gw, last_gw]
                snapshot = add_extra_features(snapshot,snapshot_dict,features=self.features)
            else:
                snapshot.loc[:,["gw","last_gw"]] = [gw, last_gw]
                snapshot = add_extra_features(snapshot,snapshot_dict,features=self.features)
                if gw == self.data_obj.end_gw-1:
                    next_fixture_update = snapshot.copy()
                    next_fixture_update.loc[:,["gw","last_gw"]] = last_gw, last_gw+1
                    next_fixture_update = add_extra_features(next_fixture_update,snapshot_dict,features=self.features)
                    snapshot[POSSIBLE_FUTURE_FEATURES] = next_fixture_update[POSSIBLE_FUTURE_FEATURES]
            
            #filtering out irrelevant data that would skew model
            if not self.next_week_pred:
                update_current_team_ids(gw)
                logging.info(f"Filtering out irrelevant data...length: {len(snapshot)}")
                
                not_owned = snapshot[snapshot["selected_by_percent"].astype(float) < 0.5]
                # Get the index values (IDs) from the snapshot where the "selected_by_percent" is less than 0.5
                not_owned_index = set(not_owned.index)  # Convert to a set for faster lookup
                # Now find the intersection between not_owned_index and CURRENT_TEAM_IDS
                dropped_ids = not_owned_index.intersection(CURRENT_TEAM_IDS)
                logging.warn(f"Dropped IDs in Current Team that are not owned by at least 0.5: {dropped_ids}")
                
                not_playing = snapshot[snapshot["minutes"] < 20]
                not_playing_index = set(not_playing.index)  # Convert to a set for faster lookup
                dropped_ids = not_playing_index.intersection(CURRENT_TEAM_IDS)
                logging.warn(f"Dropped IDs in Current Team that are not playing: {dropped_ids}")
                
                snapshot = pandas.concat([snapshot,not_owned,not_playing]).drop_duplicates(keep=False)
                logging.info(f"Down to...length: {len(snapshot)}")

            snapshot.dropna(subset=["future_points"], inplace=True)
            
            return snapshot[self.features], snapshot["future_points"]

        X_all, Y_all = [], []
        for gw in range(self.data_obj.start_gw, self.data_obj.end_gw):
            if self.next_week_pred:
                X,Y = get_data(gw,self.data_obj.players,self.data_obj.raw_season_stats_snap)
            else:
                X,Y = get_data(gw)
            if X is not None: 
                X_all.append(X)
                Y_all.append(Y)
                

        return pandas.concat(X_all, ignore_index=True), pandas.concat(Y_all, ignore_index=True)
