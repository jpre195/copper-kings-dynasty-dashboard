import streamlit as st
import pandas as pd
import numpy as np
import requests
import matplotlib.pyplot as plt
import matplotlib.cbook as cbook
import altair as alt

#Constants
LEAGUE_ID = 981358650981781504
API_URL = 'https://api.sleeper.app/v1'

@st.cache_data
def get_users() -> pd.DataFrame:
    """Query users in league

    :return: Users in league
    :rtype: pd.DataFrame
    """

    #API query
    response = requests.get(f'{API_URL}/league/{LEAGUE_ID}/users')
    users = response.json()

    #Convert to dataframe
    results = pd.DataFrame(users)
    results.drop(['settings', 'metadata', 'league_id', 'is_bot'], inplace = True, axis = 1)

    #Extract team name
    results['team_name'] = [np.nan if record['metadata'] is None or 'team_name' not in record['metadata'] else record['metadata']['team_name'] for record in users]

    return results

@st.cache_data
def get_rosters() -> pd.DataFrame:
    """Get roster information for each team in league

    :return: Roster information
    :rtype: pd.DataFrame
    """

    #API query
    response = requests.get(f'{API_URL}/league/{LEAGUE_ID}/rosters')
    rosters = response.json()

    #Convert to dataframe
    results = pd.DataFrame(rosters)

    #Drop unnecessary columns
    results.drop(['taxi', 'settings', 'starters', 'reserve', 'players', 'player_map', 'metadata', 'league_id', 'keepers', 'co_owners'], axis = 1, inplace = True)

    #Uncomment these when league starts
    # results['points_for'] = [float(str(record['settings']['fpts']) + str(record['settings']['fpts_decimal'])) for record in rosters]
    # results['points_against'] = [float(str(record['settings']['fpts_against']) + str(record['settings']['fpts_against_decimal'])) for record in rosters]

    #Extract points for/against, wins, ties, and losses
    results['points_for'] = [record['settings']['fpts'] for record in rosters]
    results['points_against'] = [0 for _ in rosters]
    results['wins'] = [record['settings']['wins'] for record in rosters]
    results['ties'] = [record['settings']['ties'] for record in rosters]
    results['losses'] = [record['settings']['losses'] for record in rosters]

    return results

@st.cache_data
def get_matchups() -> pd.DataFrame:
    """Gather matchup information

    :return: Matchup results
    :rtype: pd.DataFrame
    """

    #Initialize week variable
    week = 1

    while True:

        #API query
        response = requests.get(f'{API_URL}/league/{LEAGUE_ID}/matchups/{week}')
        results = response.json()

        #Haven't reached current week
        if len(results) == 0:

            break

        #Increment week
        week += 1

    #TODO: Extract data once first week has finished

    return results

def format_standings(users: pd.DataFrame, rosters: pd.DataFrame) -> pd.DataFrame:
    """Format dataframe to display standings

    :param users: Users in league
    :type users: pd.DataFrame
    :param rosters: Roster information
    :type rosters: pd.DataFrame
    :return: Standings
    :rtype: pd.DataFrame
    """

    #Set indeces for joining
    users.set_index('user_id', inplace = True)
    rosters.set_index('owner_id', inplace = True)

    #Join to create standings
    standings = rosters.join(users)

    #Reformat record into one column
    standings['record'] = [f'{wins}-{losses}' if ties == 0 else f'{wins}-{ties}-{losses}' for wins, ties, losses in zip(standings['wins'], standings['ties'], standings['losses'])]

    #Sort based on wins and then points for
    standings.sort_values(['wins', 'points_for'], ascending = False, inplace = True)

    #Calculate league rank
    standings['Rank'] = [i for i in range(1, standings.shape[0] + 1)]

    #Drop wins, ties, and losses columns
    standings.drop(['wins', 'ties', 'losses'], inplace = True, axis = 1)

    #Rename columns
    standings.rename({'display_name' : 'Owner',
                      'team_name' : 'Team',
                      'points_for' : 'Points For',
                      'points_against' : 'Points Against',
                      'record' : 'Record'},
                      axis = 1,
                      inplace = True)
    
    #Filter out columns
    standings = standings[['Rank', 'Team', 'Owner', 'Points For', 'Points Against', 'Record']]

    return standings

def get_strength_group(df, avg_for):

    #Current row's points for and point differential
    points_for = df['Points For']
    points_diff = df['Points Differential']

    #If they're points are above-average and have lower points against
    if points_for > avg_for and points_diff > 0:

        df['Group'] = 'Juggernaut'

    #If they're points are above-average, but have higher points against
    elif points_for > avg_for and points_diff <= 0:

        df['Group'] = 'Unlucky'

    #If they're points are below-average, but have lower points against
    elif points_for <= avg_for and points_diff > 0:

        df['Group'] = 'Lucky'

    #If they're points are below-average and have higher points against
    else:

        df['Group'] = 'Trash'

    return df

def format_strength(standings: pd.DataFrame) -> pd.DataFrame:
    """Format dataframe for team strength view

    :param standings: Current standings
    :type standings: pd.DataFrame
    :return: Strength information
    :rtype: pd.DataFrame
    """

    #Copy of standings
    strength = standings.copy()

    #Calculate points differential
    strength['Points Differential'] = strength['Points For'] - strength['Points Against']

    #Average points scored
    avg_points_for = strength['Points For'].mean()

    #Get team strength grouping
    strength = strength.apply(get_strength_group, axis = 1, avg_for = avg_points_for)

    return strength

def format_winners_losers(standings: pd.DataFrame):
    """Separate standings into winners/loser's bracket

    :param standings: Current league standings
    :type standings: pd.DataFrame
    :return: Tuple of winners and losers bracket
    :rtype: tuple
    """

    #Copy of standings
    standings_copy = standings[['Rank', 'Team', 'Owner']]

    #Separate winners and losers
    winners = standings_copy[standings_copy.Rank < 7]
    losers = standings_copy[standings_copy.Rank >= 7].reset_index(drop = True)

    return winners, losers

#Pull data
users = get_users()
rosters = get_rosters()
matchups = get_matchups()

#Format data
standings = format_standings(users, rosters)
strength = format_strength(standings)
winners_bracket, losers_bracket = format_winners_losers(standings)

#Calculate data
king_of_week = 'jpre195'
clown_of_week = 'tmyers44'

#App title
st.title('Copper Kings Dynasty League')

#App tabs
tab1, tab2 = st.tabs([':medal: Standings', ':muscle: Team Strength'])

#King/Clown of the week cards
with st.container():

    col1, col2 = tab1.columns(2)

    col1.metric(':crown: King of the Week', f'{king_of_week}: 120', help = 'Team who scored the most points this week')
    col2.metric(':clown_face: Clown of the Week', f'{clown_of_week}: 89', help = 'Team who scored the least this week')

tab1.divider()

#Standings
with st.container():

    tab1.dataframe(standings, hide_index = True, use_container_width = True)

tab1.divider()

#Winner's Loser's Bracket
with st.container():

    col1, col2 = tab1.columns(2)

    col1.header(":trophy: Playoff Bracket")
    col1.dataframe(winners_bracket, hide_index = True, use_container_width = True)

    col2.header(":shit: Loser's Bracket")
    col2.dataframe(losers_bracket, hide_index = True, use_container_width = True)

#Team strength view
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