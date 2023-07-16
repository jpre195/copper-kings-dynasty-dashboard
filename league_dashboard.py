import streamlit as st
import pandas as pd
import numpy as np
import requests
import matplotlib.pyplot as plt
import matplotlib.cbook as cbook
import altair as alt

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

@st.cache_data
def get_matchups():

    week = 1

    while True:

        response = requests.get(f'{API_URL}/league/{LEAGUE_ID}/matchups/{week}')

        results = response.json()

        if len(results) == 0:

            break

        week += 1

    return results

def format_standings(users, rosters):

    users.set_index('user_id', inplace = True)
    rosters.set_index('owner_id', inplace = True)

    standings = rosters.join(users)

    standings = standings[['team_name', 'display_name', 'points_for', 'points_against', 'wins', 'ties', 'losses']]
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

def get_strength_group(df, avg_for):

    points_for = df['Points For']
    points_diff = df['Points Differential']

    if points_for > avg_for and points_diff > 0:

        df['Group'] = 'Juggernaut'

    elif points_for > avg_for and points_diff <= 0:

        df['Group'] = 'Unucky'

    elif points_for <= avg_for and points_diff > 0:

        df['Group'] = 'Lucky'

    else:

        df['Group'] = 'Trash'

    return df

def format_strength(standings):

    strength = standings.copy()

    strength['Points Differential'] = strength['Points For'] - strength['Points Against']

    avg_points_for = strength['Points For'].mean()

    strength = strength.apply(get_strength_group, axis = 1, avg_for = avg_points_for)

    return strength

users = get_users()
rosters = get_rosters()
matchups = get_matchups()
standings = format_standings(users, rosters)
strength = format_strength(standings)

king_of_week = 'jpre195'
clown_of_week = 'tmyers44'

st.title('Copper Kings Dynasty League')

tab1, tab2 = st.tabs([':medal: League Standings', ':muscle: Team Strength'])

with st.container():

    col1, col2 = tab1.columns(2)

    col1.metric(':crown: King of the Week', f'{king_of_week}: 120', help = 'Team who scored the most points this week')
    col2.metric(':clown_face: Clown of the Week', f'{clown_of_week}: 89', help = 'Team who scored the least this week')

    tab1.dataframe(standings, hide_index = True, use_container_width = True)

with st.container():
    
    domain_ = ['Juggernaut', 'Lucky', 'Unlucky', 'Trash']
    range_ = ['blue', 'green', 'yellow', 'brown']

    chart = (alt.Chart(strength)
                .mark_circle(size = 250)
                .encode(x = 'Points Differential',
                        y = 'Points For',
                        color = alt.Color('Group').scale(domain = domain_, range = range_).title(None),
                        tooltip = ['Points For', 'Points Against', 'Points Differential', 'Owner', 'Team'])
                .interactive()
    )

    tab2.altair_chart(chart, use_container_width = True)