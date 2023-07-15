import streamlit as st
import pandas as pd
import numpy as np
import requests
from PIL import Image
from pprint import pprint

LEAGUE_ID = 981358650981781504
API_URL = 'https://api.sleeper.app/v1'

@st.cache_data
def get_users():

    response = requests.get(f'{API_URL}/league/{LEAGUE_ID}/users')

    users = response.json()

    results = pd.DataFrame(users)
    results.drop(['settings', 'metadata', 'league_id', 'is_bot'], inplace = True, axis = 1)

    results['team_name'] = [np.nan if record['metadata'] is None or 'team_name' not in record['metadata'] else record['metadata']['team_name'] for record in users]

    return results

@st.cache_data
def get_rosters():

    response = requests.get(f'{API_URL}/league/{LEAGUE_ID}/rosters')

    rosters = response.json()

    results = pd.DataFrame(rosters)

    results.drop(['taxi', 'settings', 'starters', 'reserve', 'players', 'player_map', 'metadata', 'league_id', 'keepers', 'co_owners'], axis = 1, inplace = True)

    #Uncomment these when league starts
    # results['points_for'] = [float(str(record['settings']['fpts']) + str(record['settings']['fpts_decimal'])) for record in rosters]
    # results['points_against'] = [float(str(record['settings']['fpts_against']) + str(record['settings']['fpts_against_decimal'])) for record in rosters]

    results['points_for'] = [record['settings']['fpts'] for record in rosters]
    results['points_against'] = [0 for _ in rosters]
    results['wins'] = [record['settings']['wins'] for record in rosters]
    results['ties'] = [record['settings']['ties'] for record in rosters]
    results['losses'] = [record['settings']['losses'] for record in rosters]

    return results

def format_standings(users, rosters):

    users.set_index('user_id', inplace = True)
    rosters.set_index('owner_id', inplace = True)

    standings = rosters.join(users)

    standings = standings[['display_name', 'team_name', 'points_for', 'points_against', 'wins', 'ties', 'losses']]
    standings['record'] = [f'{wins}-{losses}' if ties == 0 else f'{wins}-{ties}-{losses}' for wins, ties, losses in zip(standings['wins'], standings['ties'], standings['losses'])]

    standings.sort_values(['wins', 'points_for'], ascending = False, inplace = True)

    standings.drop(['wins', 'ties', 'losses'], inplace = True, axis = 1)

    standings.rename({'display_name' : 'Owner',
                      'team_name' : 'Team',
                      'points_for' : 'Points For',
                      'points_against' : 'Points Against',
                      'record' : 'Record'},
                      axis = 1,
                      inplace = True)

    return standings

users = get_users()
rosters = get_rosters()
standings = format_standings(users, rosters)


st.title('Copper Kings Dynasty League')

with st.container():

    st.header(':medal: League Standings')
    st.dataframe(standings, hide_index = True)
