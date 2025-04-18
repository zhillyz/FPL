from functools import partial
from datetime import datetime
import requests
import pandas
import json

BOOTSTRAP_URL = 'https://fantasy.premierleague.com/api/bootstrap-static/'

def get_gameweek_to_datestr_mapping():
    response = requests.get(BOOTSTRAP_URL)
    data = response.json()
    
    mapping = {}
    for event in data['events']:
        gw = event['id']
        deadline = event['deadline_time']  # e.g., '2024-09-01T11:00:00Z'
        dt = datetime.strptime(deadline, "%Y-%m-%dT%H:%M:%SZ")
        datestr = dt.strftime("%Y%m%d")
        mapping[gw] = datestr
    return mapping

class CurrentSeasonalFPLData():

    difficulty_url = 'https://fantasy.premierleague.com/api/fixtures?future=1'
    
    def __init__( self, lookback = 5, features = ['points_per_game_rank_type','expected_goal_involvements','total_points','creativity','bonus','ict_index',] ):
        self.features = features
        self.attributes = ['id','now_cost','element_type','web_name',]+self.features
        self.raw_data = self.getPlayerAndTeamData()
        self.events = self.raw_data['events']
        self.current_gameweek = self.getCurrentGameweek()
        self.players,self.id_map = self.cleanPlayerData(self.raw_data)#self.data['elements']
        self.teams = None
        self.fdr = self.getDifficultyData()
        self.processed_data = self.processData(self.players)
        
    
    def getPlayerAndTeamData( self ):
        player_bytes_dict = self.queryAPI(BOOTSTRAP_URL)
        return json.loads(player_bytes_dict.decode('utf-8'))
        
    def getDifficultyData( self ):
        difficulty_bytes_dict = self.queryAPI(self.difficulty_url)
        return json.loads(difficulty_bytes_dict.decode('utf-8'))
        
    def cleanPlayerData( self, data ):
        list_player_dicts = [player for player in data['elements'] if player['minutes'] > 0]
        players = {}
        id_map = {}
        for index,player_dict in enumerate(list_player_dicts):
            players.update({player_dict['id']:player_dict})
            id_map.update({player_dict['web_name']:player_dict['id']})
        return players,id_map
        # self.player_positions = None      
        # player_pos_map = data['element_types']

    def queryAPI( cls, url ):
        results = requests.get(url)
        return results.content
    
    def getCurrentGameweek(self):
        current_gw = next((gw for gw in self.events if gw["is_current"]), None)
        if current_gw:
            return current_gw["id"]
        return None
    
    def processData(self, data):
        import pandas
        df = pandas.DataFrame.from_dict(data)
        
        # Separate numeric columns and fill NaNs with 0
        numeric_columns = df.select_dtypes(include=[float, int]).columns
        df[numeric_columns] = df[numeric_columns].fillna(0)
        
        df[df.columns] = df[df.columns].apply(pandas.to_numeric,errors='ignore')
        df = df.loc[self.attributes]
        df = df.T
        return df

    def getGameweekSnapshot(self,date_str='20250331'):
        gameweek_url = f"https://web.archive.org/web/{date_str}000000/https://fantasy.premierleague.com/api/bootstrap-static/"
        response = requests.get(gameweek_url)
        if response.status_code == 200:
            temp = json.loads(response.content.decode('utf-8'))
            temp,_ = self.cleanPlayerData(temp)
            return self.processData(temp)
        else:
            raise Exception(f"Failed to fetch data: {response.status_code}, URL: {url}")
    
    # def standarizedData(cls,data):
    #     df = data.copy()
    #     def standardization(df, column_name):
    #             mean_value = df[column_name].mean()
    #             std_value = df[column_name].std()
    #             df[column_name] = (df[column_name] - mean_value) / std_value


    #     for column in df.columns:
    #         standardization(df,column)
    #     return df
        
class HistoricFPLData():
    
    def __init__( self, currentFPLData, lookback = 3, future_points_weeks = 3 ):
        self.mapping = get_gameweek_to_datestr_mapping()
        self.current_stats = currentFPLData
        self.predict_future_points_num_weeks = future_points_weeks
        self.player_gw_cache = {}
        self.data = self.getLookbackData(lookback)
        
    def get_player_gameweek_data(self,player_id, start_gw, end_gw):
        if player_id not in self.player_gw_cache:
            url = f"https://fantasy.premierleague.com/api/element-summary/{player_id}/"
            response = requests.get(url)
            data = response.json()
            self.player_gw_cache[player_id] = data
        else:
            data = self.player_gw_cache[player_id]
        filtered = [gw for gw in data["history"] if start_gw <= gw["round"] <= end_gw]
        return filtered
    
    def getLookbackData(self, lookback):
        curr_gw = self.current_stats.current_gameweek
        start_gw = curr_gw - lookback
        end_gw = start_gw + self.predict_future_points_num_weeks
        
        def get_future_points(row,start_gw,end_gw):
            try:
                player_id = int(row["id"])
                gw_data = self.get_player_gameweek_data(player_id, start_gw, end_gw)
                future_points = sum(gw["total_points"] for gw in gw_data)
                return future_points
            except Exception as e:
                print(f"Error with player {row['id']}: {e}")
                return None  # or np.nan

        X_all = []
        Y_all = []
        
        for gw in range(start_gw,end_gw+1):
            # feature_df = self.current_stats.processed_data.copy()
            feature_df = self.current_stats.getGameweekSnapshot(self.mapping[gw+1])
            feature_df = feature_df[self.current_stats.features+['id']]
            # Compute future points as a new column
            wrapped_func = partial(get_future_points, start_gw=gw+1, end_gw=end_gw)
            feature_df["future_points"] = feature_df.apply(wrapped_func, axis=1)

            # Optionally, drop rows with missing target
            feature_df = feature_df.dropna(subset=["future_points"])
            
            X_all.append(feature_df[self.current_stats.features])  # drop 'id'
            Y_all.append(feature_df['future_points'])
        
        return pandas.concat(X_all, ignore_index=True), pandas.concat(Y_all, ignore_index=True)
        
