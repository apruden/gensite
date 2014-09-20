import urllib, base64, json
from google.appengine.api import urlfetch


class GitClient(object):

	git_base = 'https://api.github.com'

	def __init__(self, owner, repo):
		self.owner = owner
		self.repo = repo

	def get_repos(self, url):
		url = url.lstrip('/')
		url = '%s/repos/%s/%s/%s' % (self.git_base, self.owner, self.repo, url)
		res = urlfetch.fetch(url=url, method=urlfetch.GET)
		return json.loads(res.content)

	def post_repos(self, url, data):
		form_data = urllib.urlencode(form_fields)
		res = None
		return json.loads(res)

	def get(self, url):
		res = urlfetch.fetch(url=url, method=urlfetch.GET)
		return json.loads(res.content)

