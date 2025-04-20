from constants import RAW_PLAYER_STATS_URL, RAW_FIXTURE_DATA_URL, AVAILABLE_FEATURES, CREATED_FEATURES
from functools import wraps
from datetime import datetime
import requests
import logging
import inspect
import time
import json

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

@logger
def query_API( url ):
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
        raise Exception(f"Failed to fetch data: {results.status_code}, URL: {url}")


def extract_player_to_dict(player_dict):
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


@logger
def create_and_cache_player_dict_from_snap( snap, cache = False):
    """
    Extracts player data from the raw season stats snapshot, filtering out players with zero minutes played.
    
    Creates a dictionary of player data, mapping player IDs to their corresponding player dictionaries.
    Also creates a dictionary mapping player names to their IDs.
    
    Additionally, fetches the gameweek data for each player and stores it in the `player_gw_cache` attribute.
    
    Returns:
        tuple: A tuple of two dictionaries, the first mapping player IDs to their dictionaries and the second mapping player names to their IDs.
    """
    players,id_map = extract_player_to_dict(snap)
    logging.info(f"Number of players: {len(players)}")
    for i,id_num in enumerate(players):
        if isinstance(cache,dict) and id_num not in cache:
            logging.info(f"New player, caching for: {players[id_num]['web_name']}")
            url = f"https://fantasy.premierleague.com/api/element-summary/{id_num}/"
            data = query_API(url)
            cache[id_num] = data
        if i % 10 == 0:
            logging.info(f"Finished fetching gameweek data for {i} out of {len(players)} player dictionaries...")
    return players,id_map

def get_player_ids_for_entry(entry_id,event_id):
    """
    Retrieves a list of player IDs for a given entry and event from the Fantasy Premier League API.

    Args:
        entry_id (int): The ID of the entry to retrieve player picks for.
        event_id (int): The ID of the event to retrieve player picks for.

    Returns:
        list: A list of player IDs representing the picks for the specified entry and event.
    """

    url = f"https://fantasy.premierleague.com/api/entry/{entry_id}/event/{event_id}/picks/"
    data = query_API(url)
    return [pick['element'] for pick in data['picks']]

@logger
def get_raw_season_stats_snap():
    """
    Fetches the current season's static data from the FPL API.

    Returns:
        dict: The JSON-decoded response.
    """
    return query_API(RAW_PLAYER_STATS_URL)

@logger
def get_raw_historic_player_stats_snap( date_str ):
    """
    Fetches the season's static data from the FPL API for a given date.

    Args:
        date_str (str): The date string in 'YYYYMMDD' format to specify the snapshot date.

    Returns:
        dict: The JSON-decoded response.
    """
    return query_API(f"https://web.archive.org/web/{date_str}000000/"+RAW_PLAYER_STATS_URL)

@logger
def get_raw_fixture_data():
    """
    Fetches the current season's fixture data from the FPL API.

    Returns:
        dict: The JSON-decoded response containing fixture data.
    """

    return query_API(RAW_FIXTURE_DATA_URL)

@logger
def get_gameweek_to_datestr_mapping( events ):  
    """
    Maps gameweek IDs to date strings in the format 'YYYYMMDD'.

    Args:
        events (list): The list of events from the raw season stats snapshot.

    Returns:
        dict: A dictionary mapping gameweek IDs to date strings.
    """
    
    mapping = {}
    for event in events:
        gw = event['id']
        deadline = event['deadline_time']  # e.g., '2024-09-01T11:00:00Z'
        dt = datetime.strptime(deadline, "%Y-%m-%dT%H:%M:%SZ")
        datestr = dt.strftime("%Y%m%d")
        mapping[gw] = datestr
    return mapping

@logger
def get_current_gameweek( events ):
    """
    Returns the ID of the current gameweek or None if not found.

    Iterates over the 'events' from the raw season stats snapshot and returns the ID of the first event with 'is_current'
    set to True. If no such event is found, returns None.

    Returns:
        int or None: The ID of the current gameweek or None if not found.
    """
    current_gw = next((gw for gw in events if gw["is_current"]), None)
    if current_gw:
        return current_gw["id"]
    return None

def process_dictdata_to_dataframe(dictdata):
    import pandas
    df = pandas.DataFrame.from_dict(dictdata)
    
    # Separate numeric columns and fill NaNs with 0
    numeric_columns = df.select_dtypes(include=[float, int]).columns
    df[numeric_columns] = df[numeric_columns].fillna(0)
    
    df[df.columns] = df[df.columns].apply(pandas.to_numeric,errors='ignore')
    df = df.T
    return df

def filter_dataframe(df,filters=None):
    if filters:
        return df[filters]
    return df

def get_player_data(snap=None,cache=False):
    """
    Retrieves player data from the FPL API, optionally using a cache for the raw player data.
    
    If cache is provided, the function will use the cache to store the raw player data.
    
    Returns:
        tuple: A tuple of three elements, the first being a DataFrame of player data, the second being a dictionary mapping player IDs to their positions, and the third being the raw season stats snapshot used to generate the player data.
    """
    if snap is None: 
        snap = get_raw_season_stats_snap()
    players_dict,id_to_pos_map = create_and_cache_player_dict_from_snap(snap, cache=cache)
    players = process_dictdata_to_dataframe(players_dict)
    return players,id_to_pos_map,snap

def get_dynamic_horizon(gw, total_gws, max_horizon=5, min_horizon=1):
    # Linear decay from max_horizon to min_horizon across the season
    season_progress = gw / total_gws
    dynamic_horizon = max(min_horizon, int(round(max_horizon * (1 - season_progress))))
    return dynamic_horizon

def get_team_fixture_info(fixtures, start_gw, end_gw):
        """
        Returns a dict of team_id → dict with 'num_fixtures' and 'total_fdr'
        """

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

def get_current_predictor_data(curr_gw=None):
    players_df,_,stats = get_player_data()
    fixtures = get_raw_fixture_data()
    events = stats["events"]
    date_map = get_gameweek_to_datestr_mapping(events)
    if curr_gw is None: 
        curr_gw = get_current_gameweek(events)
    else:
        stats = get_raw_historic_player_stats_snap(date_map[curr_gw])
    players_df["num_fixtures"] = players_df.apply(lambda x: get_team_fixture_info(fixtures,curr_gw+1, curr_gw+1).get(x["team"],{}).get("num_fixtures",0),axis=1)
    players_df["total_fdr"] = players_df.apply(lambda x: get_team_fixture_info(fixtures,curr_gw+1, curr_gw+1).get(x["team"],{}).get("total_fdr",0), axis=1)
    players_df["is_injured"] = players_df["status"].apply(lambda x: 1 if x in ["i", "s", "n", "u"] else 0)
    players_df.loc[:,'horizon'] = 1
    return players_df
