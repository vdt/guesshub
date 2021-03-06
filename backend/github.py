import itertools
import re
import requests
import time

import config
import model

# The maximum number of entries that can be requested per page.
MAX_PAGE_SIZE = 100

# Implementation constants.
NEXT_PAGE_REGEX = re.compile(r'<([^<>]+)>; rel="next"')
TOTAL_PAGES_REGEX = re.compile(r'<[^<>]+=(\d+)>; rel="last"')


class GitHub(object):
  def __init__(self, client_id, client_secret, user_agent):
    self.client_id = client_id
    self.client_secret = client_secret
    self.user_agent = user_agent

  def Fetch(self, url, **params):
    """
    Performs an authenticated GitHub request, retrying on server errors and
    sleeping if the rate limit is exceeded.

    Args:
      url: The URL to request. An absolute path or full URL. Can include a
          query string.
      prams: The query parameters to send.

    Returns:
      A requests.Response object.
    """
    full_params = params.copy()
    full_params['client_id'] = self.client_id
    full_params['client_secret'] = self.client_secret
    request_headers = {'User-Agent': self.user_agent}
    if not url.startswith('https://api.github.com/'):
      url = 'https://api.github.com/' + url
    result = requests.get(url, params=full_params, headers=request_headers)

    # Explode on client errors and retry on server error.
    status = result.status_code
    if status >= 500:
      return self.Fetch(url, **params)
    elif status == 403:
      # Sleep and retry when we hit the rate limit.
      print 'Hit rate limit.'
      response_headers = result.headers
      reset_time = int(response_headers['X-RateLimit-Reset'])
      delay_time = int(reset_time - time.time()) + 1
      if delay_time > 0:  # Time sync issues may result in negative delay.
        print 'Sleeping for', delay_time, 'seconds...'
        time.sleep(delay_time)
        return self.Fetch(url, **params)
    elif status >= 400 and status < 500:
      raise RuntimeError('Client error, HTTP %s.\n'
                         'Path: %s\nParams: %s\nResponse: %s' %
                         (status, url, params, result.json()))

    # All's well that ends well.
    return result

  def List(self, url, pages=None, **params):
    """Fetches and yields each item from a GH listing."""
    if pages is None:
      page_range = itertools.repeat(1)
    else:
      page_range = range(pages)

    for page in page_range:
      # Fetch current page.
      response = self.Fetch(url, per_page=MAX_PAGE_SIZE, **params)
      json = response.json()
      if isinstance(json, dict):
        assert 'items' in json, json
        json = json['items']
      for item_json in json:
        yield item_json

      # Get next page.
      if 'Link' in response.headers:
        next_page_links = NEXT_PAGE_REGEX.findall(response.headers['Link'])
        if next_page_links:
          assert len(next_page_links) == 1, response.headers
          url = next_page_links[0]

  def GetCommitsList(self, repo, pages_count):
    """Yields the SHAs of recent commits given a repo name."""
    for commit_json in self.List('repos/%s/commits' % repo, pages_count):
      yield commit_json['sha']

  def GetCommits(self, repo, sha):
    """Yields Commit objects for each patch in a given commit.

    The commit is specified by a repo name and a SHA hash.
    """
    commit_json = self.Fetch('repos/%s/commits/%s' % (repo, sha)).json()
    for commit in model.Commit.split_from_json(commit_json):
      yield commit

  def GetStarCount(self, repo):
    """Returns the number stars for a repository given its name."""
    response = self.Fetch('repos/%s/stargazers' % repo)
    first_page_count = len(response.json())

    if 'Link' in response.headers:
      # Multiple pages. Estimate.
      matches = TOTAL_PAGES_REGEX.findall(response.headers['Link'])
      assert matches and len(matches) == 1, response.headers
      total_pages = int(matches[0])
      return (total_pages - 1) * first_page_count + first_page_count / 2
    else:
      # One page. Exact number.
      return first_page_count

  def GetUserRespositories(self, username):
    """Yields the repositories of a given user as Repository objects."""
    for repository_json in self.List('users/%s/repos' % username):
      yield model.Repository(repository_json,
                             self.GetStarCount(repository_json['full_name']))

  def GetTopUsers(self):
    """Yields the usernames of the top 10,000 users."""
    search_url = 'search/users?q=followers%3A%3E%3D0&sort=followers'
    for user_json in self.List(search_url):
      yield user_json['login']

  def GetTopRepositories(self):
    """Yields the top 10,000 repositories as Repository objects."""
    search_url = 'search/repositories?q=stars%3A>%3D0&sort=stars'
    for repository_json in self.List(search_url):
      yield model.Repository(repository_json,
                             self.GetStarCount(repository_json['full_name']))
