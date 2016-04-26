import urllib, base64, json
from google.appengine.api import urlfetch
import config

class GitClient(object):

    git_base = 'https://api.github.com'

    def __init__(self, owner, repo, token):
        self.owner = owner
        self.repo = repo
        self.token = token

    def get_repos(self, url, binary=False):
        url = url.lstrip('/')
        url = '%s/repos/%s/%s/%s?access_token=%s' % (self.git_base, self.owner, self.repo, url, self.token)
        res = urlfetch.fetch(url=url, method=urlfetch.GET)

        if binary:
            return res.content

        return json.loads(res.content)

    def post_repos(self, url, data):
        pass

    def get(self, url, binary=False):
        sep = '?' if '?' not in url else '&'
        res = urlfetch.fetch(url='%s%saccess_token=%s' % (url, sep, self.token), method=urlfetch.GET)

        if not binary:
            return json.loads(res.content)

        return res.content

