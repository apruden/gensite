import urllib, base64, json, logging
from google.appengine.api import urlfetch
import config

logging.getLogger().setLevel(logging.INFO)

class GitClient(object):

    git_base = 'https://api.github.com'

    def __init__(self, owner, repo, token):
        self.owner = owner
        self.repo = repo
        self.token = token

    def get_repos(self, url, binary=False):
        url = url.lstrip('/')
        logging.info('fetching %s' % url)
        url = '%s/repos/%s/%s/%s?access_token=%s' % (self.git_base, self.owner, self.repo, url, self.token)
        res = urlfetch.fetch(url=url, method=urlfetch.GET, validate_certificate=True)

        logging.info('response %s' % res.status_code)

        if binary:
            return res.content

        return json.loads(res.content)

    def post_repos(self, url, data):
        pass

    def get(self, url, binary=False):
        sep = '?' if '?' not in url else '&'
        res = urlfetch.fetch(url='%s%saccess_token=%s' % (url, sep, self.token), method=urlfetch.GET, validate_certificate=True)

        if not binary:
            return json.loads(res.content)

        return res.content

