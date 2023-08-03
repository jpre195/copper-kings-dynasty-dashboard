import streamlit as st
import pandas as pd
import numpy as np
import requests
import matplotlib.pyplot as plt
import matplotlib.cbook as cbook
import altair as alt
import time
from PIL import Image
from io import BytesIO
import base64

#Constants
# LEAGUE_ID = 981358650981781504
LEAGUE_ID = 871181145969176576 #Use this league ID until our league starts
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
    results.drop(['taxi', 'settings', 'player_map', 'metadata', 'league_id', 'keepers', 'co_owners'], axis = 1, inplace = True)

    #Uncomment these when league starts
    results['points_for'] = [float(str(record['settings']['fpts']) + '.' + str(record['settings']['fpts_decimal'])) for record in rosters]
    results['points_against'] = [float(str(record['settings']['fpts_against']) + '.' + str(record['settings']['fpts_against_decimal'])) for record in rosters]

    #Extract points for/against, wins, ties, and losses
    # results['points_for'] = [record['settings']['fpts'] for record in rosters]
    # results['points_against'] = [0 for _ in rosters]
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

    #Initialize results
    matchups = pd.DataFrame()

    while True:

        #API query
        response = requests.get(f'{API_URL}/league/{LEAGUE_ID}/matchups/{week}')
        results = response.json()

        #Haven't reached current week
        if len(results) == 0 or week > 15:

            break

        results_df = pd.DataFrame(results)
        results_df['week'] = week
        
        results_df = results_df[['roster_id', 'points', 'matchup_id', 'week']]

        matchups = pd.concat([matchups, results_df])

        #Increment week
        week += 1

    return matchups

def calculate_power_rankings(matchups: pd.DataFrame, rosters: pd.DataFrame) -> pd.DataFrame:
    """Calculate power rankings

    :param matchups: Matchup information
    :type matchups: pd.DataFrame
    :param rosters: Roster information
    :type rosters: pd.DataFrame
    :return: Power rankings
    :rtype: pd.DataFrame
    """

    #Make copy of roster dataframe
    rosters_copy = rosters.copy()

    #Calculate win percentage
    rosters_copy['games'] = rosters_copy['wins'] + rosters_copy['ties'] + rosters_copy['losses']
    rosters_copy['win_percent'] = rosters_copy['wins'] / rosters_copy['games']

    #Filter out unecessary columns
    rosters_copy = rosters_copy[['roster_id', 'win_percent']]

    #Initialize final dataframe
    results = pd.DataFrame()

    for roster in rosters.roster_id.unique():

        #Extract current rosters matchups
        curr_matchups = matchups[matchups.roster_id == roster].reset_index(drop = True)

        #Initialize dataframe with opponent scores
        opponents = matchups[['roster_id', 'matchup_id', 'points', 'week']]

        #Join win percentage information to opponent scores
        opponents = opponents.merge(rosters_copy, on = 'roster_id', how = 'left')

        #Rename columns
        opponents.rename({'roster_id' : 'opponent_id',
                          'points' : 'opponent_points'}, axis = 1, inplace = True)
        
        #Join current teams matchups with opponents scores
        curr_matchups = curr_matchups.merge(opponents, on = ['matchup_id', 'week'], how = 'left')
        curr_matchups = curr_matchups[curr_matchups.roster_id != curr_matchups.opponent_id].reset_index(drop = True)

        #Calculate win/loss for each matchup
        curr_matchups['win'] = [1 if curr_points > curr_opponent_points else 0 for curr_points, curr_opponent_points in zip(curr_matchups['points'], curr_matchups['opponent_points'])]

        #Calculate rank score
        curr_matchups['rank_score'] = [win * win_percent for win, win_percent in zip(curr_matchups['win'], curr_matchups['win_percent'])]

        #Sum up rank score
        curr_results = curr_matchups.groupby('roster_id').sum().reset_index()

        #Filter out unecessary columns
        curr_results = curr_results[['roster_id', 'rank_score']]

        #Join current team's results to full dataframe
        results = pd.concat([results, curr_results])

    #Reset final dataframe's index
    results.reset_index(drop = True, inplace = True)

    return results

def format_standings(users: pd.DataFrame, rosters: pd.DataFrame, power_ranks: pd.DataFrame) -> pd.DataFrame:
    """Format dataframe to display standings

    :param users: Users in league
    :type users: pd.DataFrame
    :param rosters: Roster information
    :type rosters: pd.DataFrame
    :param power_ranks: Power rankings
    :type power_ranks: pd.DataFrame
    :return: Standings
    :rtype: pd.DataFrame
    """

    #Make copies of input dataframes
    users_copy = users.copy()
    rosters_copy = rosters.copy()
    power_ranks_copy = power_ranks.copy()

    #Set indeces for joining
    users_copy.set_index('user_id', inplace = True)
    rosters_copy.set_index('owner_id', inplace = True)

    #Join to create standings
    standings = rosters_copy.join(users_copy)
    standings = standings.merge(power_ranks_copy, on = 'roster_id', how = 'left')

    #Reformat record into one column
    standings['record'] = [f'{wins}-{losses}' if ties == 0 else f'{wins}-{ties}-{losses}' for wins, ties, losses in zip(standings['wins'], standings['ties'], standings['losses'])]

    #Sort based on rank score
    standings.sort_values(['rank_score', 'points_for'], ascending = False, inplace = True)

    #Calculate power ranking
    standings['Power Rank'] = [i for i in range(1, standings.shape[0] + 1)]

    #Sort based on wins and then points for
    standings.sort_values(['wins', 'points_for'], ascending = False, inplace = True)

    #Calculate league rank
    standings['Rank'] = [i for i in range(1, standings.shape[0] + 1)]

    #Drop wins, ties, and losses columns
    standings.drop(['wins', 'ties', 'losses', 'starters', 'reserve', 'players'], inplace = True, axis = 1)

    #Rename columns
    standings.rename({'display_name' : 'Owner',
                      'team_name' : 'Team',
                      'points_for' : 'Points For',
                      'points_against' : 'Points Against',
                      'record' : 'Record'},
                      axis = 1,
                      inplace = True)
    
    #Filter out columns
    standings = standings[['Rank', 'Power Rank', 'Team', 'Owner', 'Points For', 'Points Against', 'Record']]

    return standings

def get_strength_group(df, avg_for, avg_against):

    #Current row's points for and point differential
    points_for = df['Points For']
    points_against = df['Points Against']

    #If they're points are above-average and have lower points against
    if points_for > avg_for and points_against > avg_against:

        df['Group'] = 'Mediocre'

    #If they're points are above-average, but have higher points against
    elif points_for > avg_for and points_against <= avg_against:

        df['Group'] = 'Juggernaut'

    #If they're points are below-average, but have lower points against
    elif points_for <= avg_for and points_against > avg_against:

        df['Group'] = 'Trash'

    #If they're points are below-average and have higher points against
    else:

        df['Group'] = 'Mediocre'

    return df

def format_strength(users: pd.DataFrame, standings: pd.DataFrame) -> pd.DataFrame:
    """Format dataframe for team strength view

    :param users: Users
    :type users: pd.DataFrame
    :param standings: Current standings
    :type standings: pd.DataFrame
    :return: Strength information
    :rtype: pd.DataFrame
    """

    #Copy of standings
    strength = standings.copy()
    users_copy = users.copy()

    #Calculate points differential
    # strength['Points Differential'] = strength['Points For'] - strength['Points Against']

    #Average points scored
    avg_points_for = strength['Points For'].mean()
    avg_points_against = strength['Points Against'].mean()

    #Get team strength grouping
    strength = strength.apply(get_strength_group, axis = 1, avg_for = avg_points_for, avg_against = avg_points_against)

    #Filter users to just have display name and avatar
    users_copy = users_copy[['display_name', 'avatar']]
    users_copy.rename({'display_name' : 'Owner'}, axis = 1, inplace = True)

    strength = strength.merge(users_copy, on = 'Owner', how = 'left')
    strength['avatar'] = [f'https://sleepercdn.com/avatars/thumbs/{avatar}' for avatar in strength['avatar']]

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

def format_roster(users: pd.DataFrame, rosters: pd.DataFrame, selected_team: str) -> pd.DataFrame:
    """Format data for roster view

    :param users: Owner information
    :type users: pd.DataFrame
    :param rosters: Roster information
    :type rosters: pd.DataFrame
    :param selected_team: Selected team from select box
    :type selected_team: str
    :return: Team roster
    :rtype: pd.DataFrame
    """

    #Get owner ID
    owner_id = users[users.display_name == selected_team]['user_id'].values[0]

    #Get team roster
    team_roster = rosters[rosters.owner_id == owner_id].reset_index(drop = True)

    #Explode players column
    team_roster = team_roster.explode('players', ignore_index = True)

    #Set players to index
    team_roster.set_index('players', inplace = True)

    #Make copy of player IDs dataframe
    player_ids_copy = player_ids.copy()

    #Set player_id to index
    player_ids_copy.set_index('player_id')

    #Join roster info to player IDs
    team_roster = team_roster.join(player_ids_copy)

    #Extract player names    
    team_roster = team_roster['player']

    return team_roster

def apply_cumulative_rank(df, box_scores):

    #Get roster ID and week
    roster_id = df['roster_id']
    week = df['week']

    #Filter down full dataframe to everything through current week
    wins_df = box_scores[box_scores.week <= week].reset_index(drop = True)
    wins_df = wins_df[wins_df.roster_id == roster_id].reset_index(drop = True)

    #Calculate win for each week
    wins_df['win'] = [1 if curr_points > curr_opponent else 0 for curr_points, curr_opponent in zip(wins_df['points'], wins_df['opponent_points'])]

    #Calculate number of wins and cumulative points
    wins = wins_df['win'].sum()
    cum_points = wins_df['points'].sum()

    df['cumulative_wins'] = wins
    df['cumulative_points'] = cum_points

    return df

def format_rank_race(matchups: pd.DataFrame, users: pd.DataFrame, rosters: pd.DataFrame) -> pd.DataFrame:
    """Format data to build rank race charts

    :param matchups: Matchup information
    :type matchups: pd.DataFrame
    :param users: Team owner information
    :type users: pd.DataFrame
    :param rosters: Roster information
    :type rosters: pd.DataFrame
    :return: Rank results over time
    :rtype: pd.DataFrame
    """

    #Create copies of input dataframes
    matchups_copy = matchups.copy()
    opponents = matchups.copy()

    #Rename columns for joining
    opponents.rename({'roster_id' : 'opponent_id',
                      'points' : 'opponent_points'}, axis = 1, inplace = True)
    
    #Merge opponents with matchups
    box_scores = matchups_copy.merge(opponents, on = ['matchup_id', 'week'])
    box_scores = box_scores[box_scores.roster_id != box_scores.opponent_id].reset_index(drop = True)

    #Get rank and cumulative points per week
    box_scores = box_scores.apply(apply_cumulative_rank, axis = 1, box_scores = box_scores)

    #Initialize results dataframe
    results = pd.DataFrame()

    #For each week
    for week in box_scores['week'].unique():

        #Get current weeks scores
        curr_week = box_scores[box_scores['week'] == week].reset_index(drop = True)

        #Sort by wins and points
        curr_week = curr_week.sort_values(['cumulative_wins', 'cumulative_points'], ascending = False)

        #Assign weekly rank
        curr_week['rank'] = [i for i in range(1, curr_week.shape[0] + 1)]

        #Append to results
        results = pd.concat([results, curr_week])

    #Reset index
    results.reset_index(drop = True, inplace = True)

    #Copy rosters dataframe
    rosters_copy = rosters.copy()
    rosters_copy.rename({'owner_id' : 'user_id'}, axis = 1, inplace = True)

    #Get team name information
    team_names = users.merge(rosters_copy, on = 'user_id')

    #Join results with team name information
    results = results.merge(team_names, on = 'roster_id', how = 'left')
    results = results[['display_name', 'week', 'cumulative_wins', 'cumulative_points', 'rank']]

    #Rename columns
    results.rename({'display_name' : 'Owner',
                    'week' : 'Week',
                    'cumulative_wins' : 'Wins',
                    'cumulative_points' : 'Points',
                    'rank' : 'Rank'}, axis = 1, inplace = True)

    return results

def build_rank_race_chart(df: pd.DataFrame) -> alt.Chart:
    """Build rank race chart

    :param df: Dataframe to build chart with
    :type df: pd.DataFrame
    :return: Chart
    :rtype: alt.Chart
    """

    #Build chart
    base_chart = (alt.Chart(df)
                  .mark_line(strokeWidth = 6,
                             interpolate = 'monotone')
                  .encode(x = 'Week:O',
                          y = alt.Y('Rank', scale = alt.Scale(reverse = True, zero = False)),
                          color = 'Owner:N')
                    )
    
    #Set height
    base_chart = base_chart.properties(height = 400)
    
    return base_chart

def build_points_race_chart(df: pd.DataFrame) -> alt.Chart:
    """Build points race bar chart

    :param df: Dataframe to build chart with
    :type df: pd.DataFrame
    :return: Chart
    :rtype: alt.Chart
    """

    #Sort dataframe by points
    df = df.sort_values('Points', ascending = False)

    #Build chart
    base_chart = (alt.Chart(df)
                  .mark_bar(cornerRadius = 5)
                  .encode(y = alt.Y('Owner:N', sort = '-x'),
                          x = 'Points:Q',
                          color = 'Owner:N',
                          text = 'Points')
                    )
    
    #Add text labels
    base_chart = base_chart + base_chart.mark_text(align = 'left', dx = 2)
    
    #Set title and height
    base_chart = base_chart.properties(title = f'Cumulative Points Scored - Week {int(df.Week.max())}')
    base_chart = base_chart.properties(height = 400)
    
    return base_chart

#Pull data
users = get_users()
rosters = get_rosters()
matchups = get_matchups()
player_ids = pd.read_csv('./data/player_ids.csv')
current_week = matchups[matchups.week == max(matchups.week)].reset_index(drop = True)

#Format data
power_ranks = calculate_power_rankings(matchups, rosters)
standings = format_standings(users, rosters, power_ranks)
strength = format_strength(users, standings)
winners_bracket, losers_bracket = format_winners_losers(standings)
rank_race = format_rank_race(matchups, users, rosters)

#Calculate data
king_of_week_id = ''
clown_of_week_id = ''
max_score = -1
min_score = 9999

#Find king/clown of the week
for score, roster in zip(current_week['points'], current_week['roster_id']):

    if score > max_score:

        king_of_week_id = roster
        max_score = score
    
    if score < min_score:

        clown_of_week_id = roster
        min_score = score

king_of_week_owner = rosters[rosters.roster_id == king_of_week_id]['owner_id'].values[0]
clown_of_week_owner = rosters[rosters.roster_id == clown_of_week_id]['owner_id'].values[0]

king_of_week = users[users.user_id == king_of_week_owner]['display_name'].values[0]
clown_of_week = users[users.user_id == clown_of_week_owner]['display_name'].values[0]

#App title
st.title('Copper Kings Dynasty League')

#App tabs
# tab1, tab2, tab3 = st.tabs([':medal: Standings', ':muscle: Team Strength', ':football: Rosters'])
tab1, tab2, tab3 = st.tabs([':medal: Standings', ':muscle: Team Strength', ':runner: Playoff Race'])

### Tab 1 -------------------------------

#King/Clown of the week cards
with st.container():

    col1, col2 = tab1.columns(2)

    col1.metric(':crown: King of the Week', f'{king_of_week}: {max_score}', help = 'Team who scored the most points this week')
    col2.metric(':clown_face: Clown of the Week', f'{clown_of_week}: {min_score}', help = 'Team who scored the least this week')

tab1.divider()

#Standings
with st.container():

    tab1.dataframe(standings, hide_index = True, use_container_width = True)

    tab1.info("""
    Power rankings are calculated based on the win percentage of teams you have beat in matchups. High ranking teams
    with low power rank have a _weak_ strength of schedule whereas teams with low rank and high power rank have 
    a _strong_ strength of schedule.
    """)

tab1.divider()

#Winner's Loser's Bracket
with st.container():

    col1, col2 = tab1.columns(2)

    col1.header(":moneybag: Playoff Bracket")
    col1.dataframe(winners_bracket, hide_index = True, use_container_width = True)

    col2.header(":shit: Loser's Bracket")
    col2.dataframe(losers_bracket, hide_index = True, use_container_width = True)

### Tab 2 -------------------------------

#Team strength view
with st.container():
    
    domain_ = ['Juggernaut', 'Mediocre', 'Trash']
    range_ = ['blue', 'yellow', 'brown']

    chart = (alt.Chart(strength)
                .mark_image(width = 25, height = 25)
                .encode(x = alt.X('Points For', scale = alt.Scale(zero = False)),
                        # x = 'Points For',
                        y = alt.Y('Points Against', sort = 'descending', scale = alt.Scale(zero = False)),
                        url = 'avatar',
                        # color = alt.Color('Group').scale(domain = domain_, range = range_).title(None),
                        tooltip = ['Points For', 'Points Against', 'Group', 'Owner', 'Team', 'Record'])
                .interactive()
    )

    min_point = min([strength['Points For'].min(), strength['Points Against'].min()])
    max_point = max([strength['Points For'].max(), strength['Points Against'].max()])

    ref_line_df = pd.DataFrame({'Points For' : [min_point, max_point],
                                'Points Against' : [min_point, max_point]})

    reference_line = (alt.Chart(ref_line_df)
                      .mark_line(color = 'white', strokeDash = [5, 2])
                      .encode(x = alt.X('Points For', scale = alt.Scale(zero = False)),
                              y = alt.Y('Points Against', sort = 'descending', scale = alt.Scale(zero = False)))
                    )
    
    chart = chart + reference_line

    tab2.altair_chart(chart, use_container_width = True)

    tab2.info("""
    Teams landing above the mediocrity line are more dominant while teams falling below are __trash__.
    """)

### Tab 3 -------------------------------

with st.container():

    #Create a select box with chart options
    option = tab3.selectbox('What would you like to view over time?', ('Rank', 'Points'))

    #Build initial charts
    rank_race_chart = build_rank_race_chart(rank_race[rank_race.Week < 2])
    points_race_chart = build_points_race_chart(rank_race[rank_race.Week == 1])

    #Add initial chart to app
    if option == 'Rank':

        rank_plot = tab3.altair_chart(rank_race_chart, use_container_width = True)

    else:

        points_plot = tab3.altair_chart(points_race_chart, use_container_width = True)

    #Create a start button
    start_btn = tab3.button('Start', type = 'primary')

    #If start button has been pressed
    if start_btn:

        #For each week
        for i in range(2, int(rank_race.Week.max()) + 1):

            #If rank view, update with everything up through current week
            if option == 'Rank':

                curr_rank_race = rank_race[rank_race.Week < i + 1]
                curr_rank_chart = build_rank_race_chart(curr_rank_race)
                rank_plot = rank_plot.altair_chart(curr_rank_chart, use_container_width = True)

            #If points view, update with current week
            else:

                curr_points_race = rank_race[rank_race.Week == i]
                curr_points_chart = build_points_race_chart(curr_points_race)
                points_plot = points_plot.altair_chart(curr_points_chart, use_container_width = True)

            time.sleep(1)

# with st.container():

#     #Get a list of all owners
#     teams = list(users['display_name'].unique())

#     #Select box of owners
#     selected_team = tab3.selectbox('Owner', teams)

#     #Get players on selected team
#     team_roster = format_roster(users, rosters, selected_team)

#     #Present dataframe of roster
#     tab3.dataframe(team_roster, hide_index = True, use_container_width = True)
