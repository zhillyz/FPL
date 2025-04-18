from functools import partial, wraps
from datetime import datetime
import time
import logging
import requests
import pandas
import json

import functools
import logging
import inspect
import time

def logger(decorated_method):
    """
    Decorator to log the execution and completion of a method. Including the method name, start time, and end time.
    Also logs input and output variables under DEBUG level.
    """
    @wraps(decorated_method)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        logging.info(f"Starting method: {decorated_method.__name__}")
        
        # Log input variables under DEBUG level
        if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
            args_repr = [repr(a) for a in args]
            kwargs_repr = [f"{k}={v!r}" for k, v in kwargs.items()]
            signature = inspect.signature(decorated_method)
            bound_args = signature.bind(*args, **kwargs)
            bound_args.apply_defaults()
            logging.debug(f"Input variables: {bound_args.arguments}")
        
        result = decorated_method(*args, **kwargs)
        
        # Log output variables under DEBUG level
        if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
            logging.debug(f"Output variable: {result!r}")
        
        end_time = time.time()
        logging.info(f"Method {decorated_method.__name__} completed in {end_time - start_time:.2f} seconds")
        return result
    return wrapper

def extract_and_process_playerinfo_to_dict(player_dict):
    """
    Process the raw season stats dictionary into a dictionary of player information where the keys are player IDs
    and the values are dictionaries of player information. Also create a mapping of player web_name to player ID.
    """
    list_player_dicts = [player for player in player_dict['elements'] if player['minutes'] > 0]
    players = {}
    id_map = {}
    logging.info(f"Extracting player data from dictionary of length: {len(list_player_dicts)}...")
    for _,player_dict in enumerate(list_player_dicts):
        players.update({player_dict['id']:player_dict})
        id_map.update({player_dict['web_name']:player_dict['id']})
    return players,id_map

class DataGrabber():

    raw_player_stats_url = 'https://fantasy.premierleague.com/api/bootstrap-static/'
    raw_fixture_data_url = 'https://fantasy.premierleague.com/api/fixtures/'
    
    def __init__(self,lookback_weeks = 5, range_weeks = 3,):
        self.raw_season_stats_snap = self.get_raw_season_stats_snap()
        self.raw_fixture_data = self.get_raw_fixture_data()
        self.events = self.raw_season_stats_snap['events']
        self.gameweek_to_datestr_mapping = self.get_gameweek_to_datestr_mapping()
        self.player_gw_cache = {}
        self.players,self.id_to_pos_map = self.get_player_data(self.raw_season_stats_snap)
        self.current_gameweek = self.get_current_gameweek()
        self.start_gw = self.current_gameweek - lookback_weeks
        self.end_gw = self.start_gw + range_weeks
        self.range_historic_player_stats_snap = self.get_range_historic_player_stats_snap(self.start_gw, self.end_gw)
        
    @classmethod
    @logger
    def query_API( cls, url ):
        """
        Query a given URL, expecting a JSON response.

        Args:
            cls: Ignored, included for staticmethod compatibility.
            url (str): The URL to query.

        Returns:
            dict: The JSON-decoded response.

        Raises:
            Exception: If the response status code is not 200.
        """
        results = requests.get(url)
        if results.status_code == 200:
            return json.loads(results.content.decode('utf-8'))
        else:
            raise Exception(f"Failed to fetch data: {response.status_code}, URL: {url}")
    
    @classmethod
    @logger
    def get_raw_season_stats_snap( cls ):
        """
        Fetches the current season's static data from the FPL API.

        Returns:
            dict: The JSON-decoded response.
        """
        return DataGrabber.query_API(DataGrabber.raw_player_stats_url)
    
    @classmethod
    @logger
    def get_raw_fixture_data( cls ):
        return DataGrabber.query_API(DataGrabber.raw_fixture_data_url)           
    
    @logger
    def get_range_historic_player_stats_snap(self,start_gw,end_gw):
        """
        Fetches historic player statistics snapshot from the web archive for a given date.

        Args:
            date_str (str): The date string in 'YYYYMMDD' format to specify the snapshot date. Defaults to '20250331'.

        Returns:
            dict: The JSON-decoded response containing historic player stats.
        """
        @logger
        def get_raw_historic_player_stats_snap( date_str ):
            return DataGrabber.query_API(f"https://web.archive.org/web/{date_str}000000/"+DataGrabber.raw_player_stats_url)

        range_historic_player_stats_snap = {}
        for i in range(start_gw,end_gw+1):
            date_str = self.gameweek_to_datestr_mapping[i]
            try:
                range_historic_player_stats_snap[i] = get_raw_historic_player_stats_snap(date_str)
            except Exception as e:
                print(f"Failed to fetch data: {e}, URL: https://web.archive.org/web/{date_str}000000/{DataGrabber.raw_player_stats_url}")
        
        return range_historic_player_stats_snap
    
    @logger
    def get_current_gameweek(self):
        """
        Returns the ID of the current gameweek or None if not found.

        Iterates over the 'events' in the raw season stats snapshot and returns the ID of the first event with 'is_current'
        set to True. If no such event is found, returns None.

        Returns:
            int or None: The ID of the current gameweek or None if not found.
        """
        current_gw = next((gw for gw in self.events if gw["is_current"]), None)
        if current_gw:
            return current_gw["id"]
        return None
    
    @logger
    def get_player_data( self, data, cache = True):
        """
        Extracts player data from the raw season stats snapshot, filtering out players with zero minutes played.
        
        Creates a dictionary of player data, mapping player IDs to their corresponding player dictionaries.
        Also creates a dictionary mapping player names to their IDs.
        
        Additionally, fetches the gameweek data for each player and stores it in the `player_gw_cache` attribute.
        
        Returns:
            tuple: A tuple of two dictionaries, the first mapping player IDs to their dictionaries and the second mapping player names to their IDs.
        """
        players,id_map = extract_and_process_playerinfo_to_dict(data)
        logging.info(f"Number of players: {len(players)}")
        for i,id_num in enumerate(players):
            if id_num not in self.player_gw_cache and cache:
                logging.info(f"New player, caching for: {players[id_num]['web_name']}")
                url = f"https://fantasy.premierleague.com/api/element-summary/{id_num}/"
                response = requests.get(url)
                data = response.json()
                self.player_gw_cache[id_num] = data
            if i % 10 == 0:
                logging.info(f"Finished fetching gameweek data for {i} out of {len(players)} player dictionaries...")
        return players,id_map
    
    @logger
    def get_gameweek_to_datestr_mapping( self ):
        
        mapping = {}
        for event in self.events:
            gw = event['id']
            deadline = event['deadline_time']  # e.g., '2024-09-01T11:00:00Z'
            dt = datetime.strptime(deadline, "%Y-%m-%dT%H:%M:%SZ")
            datestr = dt.strftime("%Y%m%d")
            mapping[gw] = datestr
        return mapping

class DataProcessor():
    
    def __init__( self, data_obj,  features = ['points_per_game_rank_type','expected_goal_involvements','total_points','creativity','bonus','ict_index',] ):
        self.data_obj = data_obj
        self.features = features
        self.attributes = ['id','now_cost','element_type','web_name',]+self.features
        self.players = self.process_dictdata_to_dataframe(self.data_obj.players)
        self.training_data  = self.get_training_data()
        
    @logger
    def get_player_gameweek_data(self,player_id, start_gw, end_gw):
        data = self.data_obj.player_gw_cache[player_id]
        filtered = [gw for gw in data["history"] if start_gw <= gw["round"] <= end_gw]
        return filtered        
    

    @logger
    def process_dictdata_to_dataframe(self, dictdata):
        import pandas
        df = pandas.DataFrame.from_dict(dictdata)
        
        # Separate numeric columns and fill NaNs with 0
        numeric_columns = df.select_dtypes(include=[float, int]).columns
        df[numeric_columns] = df[numeric_columns].fillna(0)
        
        df[df.columns] = df[df.columns].apply(pandas.to_numeric,errors='ignore')
        df = df.loc[self.attributes]
        df = df.T
        return df
        
    def get_team_fixture_info(self, start_gw, end_gw):
        """
        Returns a dict of team_id → dict with 'num_fixtures' and 'total_fdr'
        """
        fixtures = self.data_obj.raw_fixture_data

        team_fixture_data = {}

        for fixture in fixtures:
            gw = fixture.get("event")
            if gw is None or not (start_gw <= gw <= end_gw):
                continue

            # Home team
            home_id = fixture["team_h"]
            home_difficulty = fixture["team_h_difficulty"]
            team_fixture_data.setdefault(home_id, {"num_fixtures": 0, "total_fdr": 0})
            team_fixture_data[home_id]["num_fixtures"] += 1
            team_fixture_data[home_id]["total_fdr"] += home_difficulty

            # Away team
            away_id = fixture["team_a"]
            away_difficulty = fixture["team_a_difficulty"]
            team_fixture_data.setdefault(away_id, {"num_fixtures": 0, "total_fdr": 0})
            team_fixture_data[away_id]["num_fixtures"] += 1
            team_fixture_data[away_id]["total_fdr"] += away_difficulty

        return team_fixture_data
     
    @logger
    def get_training_data( self ):

        def get_future_points_and_fdr(row, start_gw, end_gw):
            try:
                # Get team-level fixture info
                team_fixture_info = self.get_team_fixture_info(start_gw, end_gw)
                player_id = int(row["id"])
                team_id = self.data_obj.players[player_id]["team"]
                fixture_data = team_fixture_info.get(team_id, {"num_fixtures": 0, "total_fdr": 0})

                gw_data = self.get_player_gameweek_data(player_id, start_gw, end_gw)
                future_points = sum(gw["total_points"] for gw in gw_data)

                return future_points, fixture_data["num_fixtures"], fixture_data["total_fdr"]
            except Exception as e:
                print(f"Error with player {row['id']}: {e}")
                return None, None, None

        X_all, Y_all = [], []

        for gw in range(self.data_obj.start_gw, self.data_obj.end_gw + 1):
            snapshot_dict = self.data_obj.range_historic_player_stats_snap[gw]
            players,_ = extract_and_process_playerinfo_to_dict(snapshot_dict)
            snapshot = self.process_dictdata_to_dataframe(players)
            future_points_list = []
            num_fixtures_list = []
            fdr_list = []

            for idx, row in snapshot.iterrows():
                pts, nfix, tfdr = get_future_points_and_fdr(row, gw+1, self.data_obj.end_gw)
                future_points_list.append(pts)
                num_fixtures_list.append(nfix)
                fdr_list.append(tfdr)

            snapshot["future_points"] = future_points_list
            snapshot["num_fixtures"] = num_fixtures_list
            snapshot["total_fdr"] = fdr_list

            snapshot.dropna(subset=["future_points"], inplace=True)

            selected_features = self.features[1:] + ["num_fixtures", "total_fdr"]
            X_all.append(snapshot[selected_features])
            Y_all.append(snapshot["future_points"])

        return pandas.concat(X_all, ignore_index=True), pandas.concat(Y_all, ignore_index=True)