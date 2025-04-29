TEAM_ID = 1729758
RAW_PLAYER_STATS_URL = 'https://fantasy.premierleague.com/api/bootstrap-static/'
RAW_FIXTURE_DATA_URL = 'https://fantasy.premierleague.com/api/fixtures/'
INJURED_FLAGS = ["i", "s", "n", "u","d"]
CURRENT_STATS_FEATURES = ['points_per_game','form','transfers_out','ict_index','cost_change_event','transfers_in','now_cost','clean_sheets']
POSSIBLE_FUTURE_FEATURES = [   
    "num_fixtures",
    # "total_fdr",  
]
CREATED_AVG_FEATURES = ["points_per_90","adjusted_points_per_90",]
ID_FEATURES = ['now_cost','element_type','web_name','status']
UNUSED_FEATURES = [    "strength_overall_home",
    "strength_overall_away",
    "strength_attack_home",
    "strength_attack_away",
    "strength_defence_home",
    "strength_defence_away",]  
