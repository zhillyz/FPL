from utils import (
    get_player_data,
    get_raw_fixture_data,
    get_gameweek_to_datestr_mapping,
    get_current_gameweek,
    get_raw_historic_player_stats_snap,
    logger,
    get_team_fixture_info,
    filter_dataframe,
    get_dynamic_horizon
)
from constants import RAW_PLAYER_STATS_URL,AVAILABLE_FEATURES,CREATED_FEATURES
import pandas

class DataContainer():
    
    def __init__(self,lookback_weeks = 10, range_weeks = 10,):
        self.range_weeks = range_weeks
        self.player_gw_cache = {}
        self.players,self.id_to_pos_map,self.raw_season_stats_snap = get_player_data(cache=self.player_gw_cache)
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
        for i in range(start_gw,end_gw+1):
            date_str = self.gameweek_to_datestr_mapping[i]
            try:
                range_historic_player_stats_snap[i] = get_raw_historic_player_stats_snap(date_str)
            except Exception as e:
                print(f"Failed to fetch data: {e}, URL: https://web.archive.org/web/{date_str}000000/{RAW_PLAYER_STATS_URL}")
        
        return range_historic_player_stats_snap

class DataProcessor():
    
    def __init__( self, data_obj, features=AVAILABLE_FEATURES):
        self.data_obj = data_obj
        self.features = features
        self.required_features = ['id','now_cost','element_type','web_name','status']
        self.attributes = self.required_features+self.features
        self.players = filter_dataframe(self.data_obj.players, self.attributes)
        self.players["is_injured"] = self.players["status"].apply(lambda x: 1 if x in ["i", "s", "n", "u"] else 0)
        self.training_data  = self.get_training_data()
        
    def get_player_gameweek_data(self,player_id, start_gw, end_gw):
        """
        Retrieves, from the data_container, gameweek data for a specific player within a specified range of gameweeks.

        Args:
            player_id (int): The ID of the player to retrieve gameweek data for.
            start_gw (int): The starting gameweek number.
            end_gw (int): The ending gameweek number.

        Returns:
            list: A list of dictionaries containing the gameweek data for the specified player and range.
        """
        data = self.data_obj.player_gw_cache[player_id]
        filtered = [gw for gw in data["history"] if start_gw <= gw["round"] <= end_gw]
        return filtered        
     
    @logger
    def get_training_data( self,):

        def get_future_points_and_fdr(row, start_gw, end_gw):
            try:
                # Get team-level fixture info
                team_fixture_info = get_team_fixture_info(self.data_obj.raw_fixture_data, start_gw, end_gw)
                player_id = int(row["id"])
                team_id = int(self.data_obj.players[self.data_obj.players["id"]==player_id]["team"].iloc[0])
                fixture_data = team_fixture_info.get(team_id, {"num_fixtures": 0, "total_fdr": 0})

                gw_data = self.get_player_gameweek_data(player_id, start_gw, end_gw)
                future_points = sum(gw["total_points"] for gw in gw_data)

                return future_points, fixture_data["num_fixtures"], fixture_data["total_fdr"]
            except Exception as e:
                print(f"Error with player {row['id']}: {e}")
                return None, None, None

        X_all, Y_all = [], []

        for gw in range(self.data_obj.start_gw, self.data_obj.end_gw):
            rolling_horizon = get_dynamic_horizon(gw, 38, max_horizon=self.data_obj.range_weeks)
            last_gw = min(gw + rolling_horizon, self.data_obj.end_gw)
            if last_gw <= gw:  # Redundant safety check
                continue
            snapshot_dict = self.data_obj.range_historic_player_stats_snap[gw]
            snapshot,_,_ = get_player_data(snap=snapshot_dict)
            snapshot["is_injured"] = snapshot["status"].apply(lambda x: 1 if x in ["i", "s", "n", "u", "d"] else 0)
            snapshot["horizon"] = last_gw - gw

            future_points_list = []
            num_fixtures_list = []
            fdr_list = []
            
            for _, row in snapshot.iterrows():
                pts, nfix, tfdr = get_future_points_and_fdr(row, gw+1, last_gw)
                future_points_list.append(pts)
                num_fixtures_list.append(nfix)
                fdr_list.append(tfdr)

            snapshot["future_points"] = future_points_list
            snapshot["num_fixtures"] = num_fixtures_list
            snapshot["total_fdr"] = fdr_list

            snapshot.dropna(subset=["future_points"], inplace=True)

            
            selected_features = self.features + CREATED_FEATURES
            X_all.append(snapshot[selected_features])
            Y_all.append(snapshot["future_points"])

        return pandas.concat(X_all, ignore_index=True), pandas.concat(Y_all, ignore_index=True)
