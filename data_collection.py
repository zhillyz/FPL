import requests
import json


class FPLData():

    player_url = 'https://fantasy.premierleague.com/api/bootstrap-static/'
    difficulty_url = 'https://fantasy.premierleague.com/api/fixtures?future=1'
    
    def __init__( self ):
        self.data = self.getPlayerAndTeamData()
        self.events = self.data['events']
        self.players = self.cleanPlayerData()#self.data['elements']
        self.teams = None
        self.fdr = self.getDifficultyData()
        
    
    def getPlayerAndTeamData( self ):
        player_bytes_dict = self.queryAPI(self.player_url)
        return json.loads(player_bytes_dict.decode('utf-8'))
        
    def getDifficultyData( self ):
        difficulty_bytes_dict = self.queryAPI(self.difficulty_url)
        return json.loads(difficulty_bytes_dict.decode('utf-8'))
        
    def cleanPlayerData( self ):
        list_player_dicts = [player for player in self.data['elements'] if player['minutes'] > 0]
        players = {}
        for index,player_dict in enumerate(list_player_dicts):
            players.update({player_dict['id']:player_dict})
        return players
        # self.player_positions = None      
        # player_pos_map = data['element_types']

    def queryAPI( self, url ):
        results = requests.get(url)
        return results.content
    
    
        
class CurrentSquad():
    
    def __init__( self ):
        pass
