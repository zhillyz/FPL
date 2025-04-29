from constants import RAW_PLAYER_STATS_URL, RAW_FIXTURE_DATA_URL,INJURED_FLAGS,TEAM_ID
from functools import lru_cache, wraps
from datetime import datetime,timedelta
import requests
import logging
import inspect
import pandas
import time
import json


def memoize_with_logging(func):
    cached_func = lru_cache(maxsize=None)(func)
    @wraps(func)
    def wrapper(*args, **kwargs):
        key = args + tuple(sorted(kwargs.items()))
        if key not in wrapper._cache:
            logging.info(f"🔵 Cache miss for args:{args}, kwargs:{kwargs}")
        else:
            logging.info(f"🟢 Cache hit for args:{args}, kwargs:{kwargs}")
        result = cached_func(*args, **kwargs)
        wrapper._cache.add(key)
        return result
    wrapper._cache = set()
    return wrapper

@memoize_with_logging
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
    logging.info(f"Querying API with URL:{url}. Should be memoized. So won't see this again.")
    results = requests.get(url)
    if results.status_code == 200:
        return json.loads(results.content.decode('utf-8'))
    else:
        raise Exception(f"Failed to fetch data: {results.status_code}, URL: {url}")


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

CURRENT_TEAM_IDS = get_player_ids_for_entry(TEAM_ID,1)

def update_current_team_ids(gw):
    global CURRENT_TEAM_IDS
    CURRENT_TEAM_IDS = get_player_ids_for_entry(TEAM_ID,gw)

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


def extract_player_to_dict(player_dict):
    """
    Extracts player data from the raw season stats snapshot, filtering out players with fewer than 20 minutes played and an ownership percentage of less than 0.5%.
    
    Creates a dictionary of player data, mapping player IDs to their corresponding player dictionaries, and a separate dictionary mapping player web names to their IDs.
    """
    logging.info(f"Extracting player data...length: {len(player_dict['elements'])}")
    list_player_dicts = player_dict['elements']
    players = {}
    id_map = {}
    logging.info(f"Extracting player data from dictionary of length: {len(list_player_dicts)}...")
    for _,player_dict in enumerate(list_player_dicts):
        players.update({player_dict['id']:player_dict})
        id_map.update({player_dict['web_name']:player_dict['id']})
    return players,id_map

@logger
def extract_player_dict_from_snap( snap ):
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
    return players,id_map    
        

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
    return query_API(f"https://web.archive.org/web/{date_str}/"+RAW_PLAYER_STATS_URL)

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
        dt = datetime.strptime(deadline, "%Y-%m-%dT%H:%M:%SZ") - timedelta(hours=12)
        datestr = dt.strftime("%Y%m%d%H%M%S")
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
        logging.info(f"Current gameweek found to be {current_gw['id']} based on 'is_current' flag")
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
    dropping = df[df['minutes'] == 0]
    logging.warn(f"Dropping rows with no minutes played. {len(dropping)} rows dropped")
    logging.warn(f"Dropping IDs in Current Team: {[x for x in dropping['id'] if x in CURRENT_TEAM_IDS]}")
    df = df[df["minutes"] > 0]
    return df

def filter_dataframe(df,filters=None):
    if filters:
        return df[filters]
    return df

def get_player_data(snap=None,gw=None):
    """
    Retrieves player data from the FPL API, optionally using a cache for the raw player data.
    
    If cache is provided, the function will use the cache to store the raw player data.
    
    Returns:
        tuple: A tuple of three elements, the first being a DataFrame of player data, the second being a dictionary mapping player IDs to their positions, and the third being the raw season stats snapshot used to generate the player data.
    """
    if snap is None: 
        snap = get_raw_season_stats_snap()
    if gw:
        update_current_team_ids(gw)
    players_dict,id_to_pos_map = extract_player_dict_from_snap(snap,)
    players_snap = process_dictdata_to_dataframe(players_dict)
    players_snap.set_index('id',inplace=True)
    return players_snap,id_to_pos_map,snap

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

# def get_current_predictor_data(curr_gw=None):
#     players_df,_,stats = get_player_data()
#     fixtures = get_raw_fixture_data()
#     events = stats["events"]
#     date_map = get_gameweek_to_datestr_mapping(events)
#     if curr_gw is None: 
#         curr_gw = get_current_gameweek(events)
#     else:
#         stats = get_raw_historic_player_stats_snap(date_map[curr_gw])
#     players_df["num_fixtures"] = players_df.apply(lambda x: get_team_fixture_info(fixtures,curr_gw+1, curr_gw+1).get(x["team"],{}).get("num_fixtures",0),axis=1)
#     players_df["total_fdr"] = players_df.apply(lambda x: get_team_fixture_info(fixtures,curr_gw+1, curr_gw+1).get(x["team"],{}).get("total_fdr",0), axis=1)
#     players_df["is_injured"] = players_df["status"].apply(lambda x: 1 if x in INJURED_FLAGS else 0)
#     players_df.loc[:,'horizon'] = 1
#     return players_df

def get_player_gameweek_data(row,index):
    """
    Retrieves, from the data_container, gameweek data for a specific player within a specified range of gameweeks.

    Args:
        player_id (int): The ID of the player to retrieve gameweek data for.
        start_gw (int): The starting gameweek number.
        end_gw (int): The ending gameweek number.

    Returns:
        list: A list of dictionaries containing the gameweek data for the specified player and range.
    """
    id_num = index
    logging.info(f"Querying API, for: {row['web_name']}")
    url = f"https://fantasy.premierleague.com/api/element-summary/{id_num}/"
    data = query_API(url)
    filtered = [gw for gw in data["history"] if row["gw"]+1 <= gw["round"] <= row["last_gw"]]
    if not filtered:
        filtered = [gw for gw in data["fixtures"] if row["gw"]+1 <= gw["event"] <= row["last_gw"]]
    return filtered    

def get_future_points_and_fdr(row,gw_data,raw_fixture_data,):
    """
    Get future points and fixture difficulty for a player.

    Args:
        row: pandas Series, a player row from the players dataframe
        start_gw: int, the start gameweek
        end_gw: int, the end gameweek

    Returns:
        tuple of (future_points, num_fixtures, total_fdr, total_minutes)
            future_points: int, total points scored by the player in the given gameweek range
            num_fixtures: int, number of fixtures the player's team has in the given gameweek range
            total_fdr: int, total fixture difficulty for the player's team in the given gameweek range
            total_minutes: int, total minutes played by the player in the given gameweek range
    """
    try:
        # Get team-level fixture info
        logging.info(f"Getting team fixture info between gw {row['gw']+1} and gw {row['last_gw']}")
        team_fixture_info = get_team_fixture_info(raw_fixture_data,row["gw"]+1,row["last_gw"])
        team_id = int(row["team"])
        logging.info(f"Filtering for team id: {team_id}")
        fixture_data = team_fixture_info.get(team_id, {"num_fixtures": 0, "total_fdr": 0})

        future_points = sum(gw["total_points"] if gw.get("total_points")  else 0 for gw in gw_data )
        total_minutes = sum(gw["minutes"]  if gw.get("minutes") else 0 for gw in gw_data)

        return future_points, fixture_data["num_fixtures"], fixture_data["total_fdr"], total_minutes
    except Exception as e:
        print(f"Error with player {row.name}: {e}")
        return None, None, None, None

def add_extra_features(snapshot,snapshot_dict,features):
    if any(strength in features for strength in ["strength_overall_home","strength_overall_away","strength_attack_home","strength_attack_away","strength_defence_home","strength_defence_away",]):
        # Add team strength fields from snapshot_dict["teams"]
        strengths = [strength for strength in ["strength_overall_home","strength_overall_away","strength_attack_home","strength_attack_away","strength_defence_home","strength_defence_away",] if strength in features]
        team_strength_df = pandas.DataFrame(snapshot_dict["teams"])
        team_strength_df = team_strength_df[['id',]+strengths]
        
        # Rename team id to match player field
        team_strength_df.rename(columns={"id": "team"}, inplace=True)

        # Merge team strength info into the snapshot on team ID
        snapshot = snapshot.merge(team_strength_df, on="team", how="left")
        
    if "is_injured" in features:
        snapshot["is_injured"] = snapshot["status"].apply(lambda x: 1 if x in INJURED_FLAGS else 0)
        
    future_points_list = []
    num_fixtures_list = []
    fdr_list = []
    minutes_list = []
    points_per_90 = []
    adjusted_points_per_90 = []
    raw_fixture_data = get_raw_fixture_data()
    index_list = []
    for index, row in snapshot.iterrows():
        gw_data = get_player_gameweek_data(row,index)
        pts, nfix, tfdr, mins = get_future_points_and_fdr(row, gw_data,raw_fixture_data,)
        if mins is None:
            continue
        future_points_list.append(pts)
        num_fixtures_list.append(nfix)
        fdr_list.append(tfdr)
        minutes_list.append(mins)
        p90 = (pts / mins) * 90 if mins else 1# Avoid div by zero
        #normalize with a simple linear adjustment
        fdr_adjustment = 1 / (1 + tfdr) if tfdr else 1  # Avoid div by zero
        adjusted_p90 = p90 * fdr_adjustment
        points_per_90.append(p90)
        adjusted_points_per_90.append(adjusted_p90)
        index_list.append(index)
    included_features = [feat for feat in ["num_fixtures", "total_fdr", "minutes_played_horizon","points_per_90","adjusted_points_per_90"] if feat in features] + ["future_points"]
    # Create a new DataFrame with the new columns (no need to set index manually)
    horizon = len(set([game.get('round',game.get('event')) for game in gw_data]))
    horizons_list = [horizon] * len(future_points_list)
    new_columns_df = pandas.DataFrame({
        "future_points": future_points_list,
        "num_fixtures": num_fixtures_list,
        "total_fdr": fdr_list,
        "minutes": minutes_list,
        "points_per_90": points_per_90,
        "adjusted_points_per_90": adjusted_points_per_90,
        "horizon": horizons_list,
        "id": index_list
    })
    new_columns_df.set_index("id", inplace=True)
    # Concatenate the new columns with the original DataFrame (index will align automatically)
    snapshot.update(new_columns_df[included_features])# = pandas.concat([snapshot, new_columns_df[included_features]], axis=1)
    return snapshot
