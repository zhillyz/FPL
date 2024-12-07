import requests
import json


class FPLData():

    player_url = 'https://fantasy.premierleague.com/api/bootstrap-static/'
    difficulty_url = 'https://fantasy.premierleague.com/api/fixtures?future=1'
    
    def __init__( self ):
        self.events = None
        self.players = {}
        self.teams = None
        
    
    def getPlayerData( self ):
        player_bytes_dict = self.queryAPI(self.player_url)
        return json.loads(player_bytes_dict.decode('utf-8'))
        
    def getDifficultyData( self ):
        difficulty_bytes_dict = self.queryAPI(self.difficulty_url)
        return json.loads(difficulty_bytes_dict.decode('utf-8'))
        
    def cleanData( self ):
        self.events = data['events']
        list_player_dicts = [player for player in data['elements'] if player['minutes'] > 0]
        player_pos_map = data['element_types']
        for index,player_dict in enumerate(list_player_dicts):
            self.players.update({str(player_dict['code']):player_dict})
        self.player_positions = None      

    def queryAPI( self, url ):
        results = requests.get(url)
        return results.content
    
    
        
class CurrentSquad():
    
    def __init__( self ):
        pass
