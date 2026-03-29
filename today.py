
import datetime
from dateutil import relativedelta
import requests
import os
from lxml import etree
import time

# Fine-grained personal access token with All Repositories access
HEADERS = {'authorization': 'token ' + os.environ['ACCESS_TOKEN']}
USER_NAME = os.environ['USER_NAME']
QUERY_COUNT = {'user_getter': 0, 'follower_getter': 0, 'graph_repos_stars': 0, 'recursive_loc': 0, 'graph_commits': 0, 'loc_query': 0}

def daily_readme(birthday):
    """
    Returns the length of time since May 3, 2012
    """
    diff = relativedelta.relativedelta(datetime.datetime.today(), birthday)
    return '{} {}, {} {}, {} {}{}'.format(
        diff.years, 'year' + format_plural(diff.years), 
        diff.months, 'month' + format_plural(diff.months), 
        diff.days, 'day' + format_plural(diff.days),
        ' 🎂' if (diff.months == 0 and diff.days == 0) else '')

def format_plural(unit):
    return 's' if unit != 1 else ''

def simple_request(func_name, query, variables):
    request = requests.post('https://api.github.com/graphql', json={'query': query, 'variables':variables}, headers=HEADERS)
    if request.status_code == 200:
        return request
    raise Exception(func_name, ' has failed with a', request.status_code, request.text, QUERY_COUNT)

def graph_repos_stars(count_type, owner_affiliation, cursor=None):
    query_count('graph_repos_stars')
    query = '''
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 100, after: $cursor, ownerAffiliations: $owner_affiliation) {
                totalCount
                edges {
                    node {
                        ... on Repository {
                            nameWithOwner
                            stargazers {
                                totalCount
                            }
                        }
                    }
                }
                pageInfo {
                    endCursor
                    hasNextPage
                }
            }
        }
    }'''
    variables = {'owner_affiliation': owner_affiliation, 'login': USER_NAME, 'cursor': cursor}
    request = simple_request(graph_repos_stars.__name__, query, variables)
    if count_type == 'repos':
        return request.json()['data']['user']['repositories']['totalCount']
    elif count_type == 'stars':
        return stars_counter(request.json()['data']['user']['repositories']['edges'])

def loc_query(owner_affiliation, cursor=None, edges=[], loc_add=0, loc_del=0, my_commits=0):
    query_count('loc_query')
    query = '''
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 60, after: $cursor, ownerAffiliations: $owner_affiliation) {
                edges {
                    node {
                        ... on Repository {
                            nameWithOwner
                            defaultBranchRef {
                                target {
                                    ... on Commit {
                                        history {
                                            totalCount
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                pageInfo {
                    endCursor
                    hasNextPage
                }
            }
        }
    }'''
    variables = {'owner_affiliation': owner_affiliation, 'login': USER_NAME, 'cursor': cursor}
    request = simple_request(loc_query.__name__, query, variables)
    edges += request.json()['data']['user']['repositories']['edges']
    if request.json()['data']['user']['repositories']['pageInfo']['hasNextPage']:
        return loc_query(owner_affiliation, request.json()['data']['user']['repositories']['pageInfo']['endCursor'], edges, loc_add, loc_del, my_commits)
    
    for edge in edges:
        if edge['node']['defaultBranchRef'] is not None:
            owner, repo_name = edge['node']['nameWithOwner'].split('/')
            result = recursive_loc(owner, repo_name)
            if result:
                loc_add += result[0]
                loc_del += result[1]
                my_commits += result[2]
    
    return [loc_add, loc_del, loc_add - loc_del, my_commits]

def recursive_loc(owner, repo_name, addition_total=0, deletion_total=0, my_commits=0, cursor=None):
    query_count('recursive_loc')
    query = '''
    query ($repo_name: String!, $owner: String!, $cursor: String) {
        repository(name: $repo_name, owner: $owner) {
            defaultBranchRef {
                target {
                    ... on Commit {
                        history(first: 100, after: $cursor) {
                            edges {
                                node {
                                    author {
                                        user {
                                            id
                                        }
                                    }
                                    deletions
                                    additions
                                }
                            }
                            pageInfo {
                                endCursor
                                hasNextPage
                            }
                        }
                    }
                }
            }
        }
    }'''
    variables = {'repo_name': repo_name, 'owner': owner, 'cursor': cursor}
    request = requests.post('https://api.github.com/graphql', json={'query': query, 'variables':variables}, headers=HEADERS)
    if request.status_code == 200:
        ref = request.json()['data']['repository']['defaultBranchRef']
        if ref is not None:
            history = ref['target']['history']
            for node in history['edges']:
                if node['node']['author']['user'] and node['node']['author']['user']['id'] == OWNER_ID['id']:
                    my_commits += 1
                    addition_total += node['node']['additions']
                    deletion_total += node['node']['deletions']
            if not history['pageInfo']['hasNextPage']:
                return addition_total, deletion_total, my_commits
            else:
                return recursive_loc(owner, repo_name, addition_total, deletion_total, my_commits, history['pageInfo']['endCursor'])
    return 0

def stars_counter(data):
    total_stars = 0
    for node in data: total_stars += node['node']['stargazers']['totalCount']
    return total_stars

def svg_overwrite(filename, age_data, commit_data, star_data, repo_data, contrib_data, follower_data, loc_data):
    tree = etree.parse(filename)
    root = tree.getroot()
    justify_format(root, 'age_data', age_data)
    justify_format(root, 'commit_data', commit_data)
    justify_format(root, 'star_data', star_data)
    justify_format(root, 'repo_data', repo_data)
    justify_format(root, 'follower_data', follower_data)
    justify_format(root, 'loc_data', loc_data[2])
    tree.write(filename, encoding='utf-8', xml_declaration=True)

def justify_format(root, element_id, new_text):
    if isinstance(new_text, int):
        new_text = f"{'{:,}'.format(new_text)}"
    new_text = str(new_text)
    element = root.find(f".//*[@id='{element_id}']")
    if element is not None:
        element.text = new_text

def user_getter(username):
    query_count('user_getter')
    query = 'query($login: String!){ user(login: $login) { id createdAt } }'
    request = simple_request(user_getter.__name__, query, {'login': username})
    return {'id': request.json()['data']['user']['id']}, request.json()['data']['user']['createdAt']

def follower_getter(username):
    query_count('follower_getter')
    query = 'query($login: String!){ user(login: $login) { followers { totalCount } } }'
    request = simple_request(follower_getter.__name__, query, {'login': username})
    return int(request.json()['data']['user']['followers']['totalCount'])

def query_count(funct_id):
    global QUERY_COUNT
    QUERY_COUNT[funct_id] += 1

def perf_counter(funct, *args):
    start = time.perf_counter()
    funct_return = funct(*args)
    return funct_return, time.perf_counter() - start

def formatter(query_type, difference):
    print('{:<23}{:>12}'.format('   ' + query_type + ':', '%.4f' % difference + ' s'))

if __name__ == '__main__':
    print('Calculation times:')
    user_data, user_time = perf_counter(user_getter, USER_NAME)
    OWNER_ID, acc_date = user_data
    formatter('account data', user_time)

    # UPDATED BIRTHDAY: May 3, 2012
    age_data, age_time = perf_counter(daily_readme, datetime.datetime(2012, 5, 3))
    formatter('age calculation', age_time)

    total_loc, loc_time = perf_counter(loc_query, ['OWNER', 'COLLABORATOR', 'ORGANIZATION_MEMBER'])
    formatter('LOC (no cache)', loc_time)

    star_data, star_time = perf_counter(graph_repos_stars, 'stars', ['OWNER'])
    repo_data, repo_time = perf_counter(graph_repos_stars, 'repos', ['OWNER'])
    contrib_data, contrib_time = perf_counter(graph_repos_stars, 'repos', ['OWNER', 'COLLABORATOR', 'ORGANIZATION_MEMBER'])
    follower_data, follower_time = perf_counter(follower_getter, USER_NAME)

    commit_data = total_loc[3] # Total commits from LOC query

    svg_overwrite('dark_mode.svg', age_data, commit_data, star_data, repo_data, contrib_data, follower_data, total_loc)

    print('Total GitHub GraphQL API calls:', sum(QUERY_COUNT.values()))
