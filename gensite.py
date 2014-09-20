import webapp2, jinja2, os, logging, StringIO, zipfile, json, base64, urllib
from model import Asset, Site, Settings, AppSetting, DataEntry
from git import GitClient
from google.appengine.api import urlfetch
from google.appengine.ext import ndb
from google.appengine.api import memcache, mail
from google.appengine.api.users import get_current_user, create_login_url


EDITABLE = ['.html', '.css', '.json', '.js', '.txt', '.xml', '.py']
MIME_DICT = {
		'.html': 'text/html',
		'.json': 'application/json',
		'.css': 'text/css',
		'.js': 'application/javascript',
		'.jpg': 'image/jpeg',
		'.png': 'image/png',
		'.gif': 'image/gif',
		'.ttf': 'application/x-font-ttf',
		'.woff': 'application/x-font-woff',
		'.eot': 'application/vnd.ms-fontobject',
		'.txt': 'text/plain',
		'.xml': 'text/xml',
		'.svg': 'image/svg+xml',
		'.md': 'text/plain'
		}

default_settings = {
		'cache_enabled': False,
		'editors': '',
		'sender': 'alex.prudencio@gmail.com',
		'webadmin': 'alex@primefactor.solutions',
		'repo': 'apruden/primefactor_www'
}

code_cache = {}


def get_mime(path):
	return MIME_DICT.get(os.path.splitext(path)[1], 'application/octet-stream')


def load_asset_content(path):
	asset = ndb.Key(Asset, path).get()
	if asset:
		return asset.content


JINJA_SITE_ENVIRONMENT = jinja2.Environment(
		loader=jinja2.FunctionLoader(load_asset_content),
		extensions=['jinja2.ext.autoescape'],
		autoescape=True,
		cache_size=0)


JINJA_ENVIRONMENT = jinja2.Environment(
		loader=jinja2.FileSystemLoader(os.path.join(os.path.dirname(__file__), 'templates')),
		extensions=['jinja2.ext.autoescape'],
		autoescape=True,
		cache_size=0)

settings = ndb.Key(Settings, '_settings').get()
settings_updated = False

if not settings:
	logging.debug('Settings not found. Init.')
	settings = Settings(id='_settings')

for s, v in default_settings.items():
	if not hasattr(settings, s):
		setattr(settings, s, v)
		settings_updated = True

if settings_updated:
	settings.put()

git = GitClient('apruden', 'primefactor_www')

logging.info('Running with settings %s', settings)


class ConfigHandler(webapp2.RequestHandler):
	def get(self):
		global settings
		found = ndb.Key(Settings, '_settings').get(use_cache=False, use_memcache=False)
		if found:
			logging.info('Config refreshed: %s', found)
			settings = found


class AdminHandler(webapp2.RequestHandler):
	def get(self):
		site = ndb.Key(Site, '_site').get()
		if not site:
			site = Site(id='_site', owner='apruden', repo='primefactor_www')
			site.put()

		commits = git.get_repos('/commits')
		releases = git.get_repos('/releases')

		self.response.write(JINJA_ENVIRONMENT.get_template('admin.html').render({
			'releases':releases, 'commits':commits, 'current_sha': site.current_sha, 'repo': site.repo}))

	def post(self):
		pass

	def download_release(self, release):
		asset = git.get_repos('/releases/asset/%s' % (release,))

	def fetch(self):
		sha = self.request.get('sha')
		logging.info('fetching %s', sha)
		site = ndb.Key(Site, '_site').get()

		if not site.current_sha:
			tree = git.get_repos('/git/trees/%s?recursive=1' % sha)
			tree = tree['tree']
			for f in tree:
				blob = git.get(f['url'])
				content = base64.decodestring(blob['content'])
				asset = Asset(id=self._get_path(f['path']), content=content, mime=get_mime(f['path']))
				asset.put()
				logging.info('Added asset %s', f['path'])
			site.current_sha = sha
			site.put()
		else:
			diff = git.get_repos('/compare/%s:%s...%s:%s' % (owner, current_sha, owner, sha))

			for f in diff['files']:
				content = git.get(f['contents_url'])
				content = base64.decodestring(content['content'])
				asset = Asset(id=self._get_path(f['filename']), content=content, mime=get_mime(f['filename']))
				asset.put()
				logging.info('Updated asset %s', f['filename'])

	def download(self):
		q = Asset.query()
		assets = q.fetch(100)
		output = StringIO.StringIO()

		with zipfile.ZipFile(output, 'w') as zf:
			for a in assets:
				zf.writestr(a.key.id().lstrip('/'), a.content)

		self.response.headers['Content-Type'] = 'application/zip'
		self.response.headers['Content-Disposition'] = 'attachment; filename="%s"' % 'site.zip'
		self.response.write(output.getvalue())

	def _get_path(self, path):
		path = path.lstrip('/')
		return '/%s' % path


class ApplyHandler(webapp2.RequestHandler):
	def post(self):
		data = json.loads(self.request.body)
		entry = DataEntry(id='application:%s' % data['email'], type='application', data=self.request.body)
		entry.put()
		self._send_notification_email(data['email'])

	def _send_notification_email(self, email):
		logging.info('received application from %s. sending notification.' % (email,))
		message = mail.EmailMessage(sender=settings.sender,
				to=settings.webadmin,
				subject='New job application')

		message.body= """
		A new job application was received at http://www.primefactor.solutions/api/apply?email=%s
		""" % (email,)

		message.send()

	def get(self):
		email = self.request.get('email')

		if not email:
			return

		entry = ndb.Key(DataEntry, 'application:%s' % email).get()
		doc = JINJA_SITE_ENVIRONMENT.get_template('/_app_templates/application.html').render(json.loads(entry.data))
		self.response.write(doc)


class AssetHandler(webapp2.RequestHandler):
	def get(self, path):
		path, ext = self.get_path()

		if 'admin' in self.request.GET:
			return self.edit_form(load_asset_content(path) or '', ext)

		rendered_asset = memcache.get(path)

		if not rendered_asset:
			logging.debug('cache miss')
			if ext == '.html':
				rendered_asset = self.get_rendered_asset(path)
			else:
				rendered_asset = ndb.Key(Asset, path).get()

				if not rendered_asset:
					self.abort(404)

			if settings.cache_enabled:
				logging.debug('adding to cache')
				memcache.add(path, rendered_asset, 3600)

		self.response.cache_control = 'public'
		self.response.cache_control.max_age = 48000

		if ext == '.py':
			if path not in code_cache:
				cobj = compile(rendered_asset.content, '', 'exec')
				code_cache[path] = cobj

			exec(code_cache[path], {'response': self.response}, {})
		else:
			self.response.headers['Content-Type'] = str(rendered_asset.mime)
			self.response.write(rendered_asset.content)

	def post(self, path):
		path, ext = self.get_path()

		if 'delete' in self.request.POST:
			asset = ndb.Key(Asset, path).get()
			return self.delete_asset(asset)

		logging.debug('saving content %s', path)
		uploaded = None

		if hasattr(self.request.POST['asset'], 'file'):
			uploaded = self.request.POST['asset']

		self.update_asset(path, str(self.request.POST['asset']), uploaded)

	def get_rendered_asset(self, path):
		try:
			template = JINJA_SITE_ENVIRONMENT.get_template(path)
		except jinja2.TemplateNotFound:
			self.abort(404)

		return Asset(content=str(template.render({})), mime='text/html')

	def edit_form(self, asset_content, ext):
		user = get_current_user()
		if settings.editors and (not user or user.email() not in settings.editors):
			logging.warning('user %s not found in editors %s', user, settings.editors)
			return self.redirect(create_login_url('/'))

		self.response.write(JINJA_ENVIRONMENT.get_template('upload.html').render({
			'content': asset_content,
			'editable': 'upload' not in self.request.GET and ext in EDITABLE}))

	def get_path(self):
		path = self.request.path
		ext = os.path.splitext(path)[1]

		if not ext:
			path = '/index.html' if path == '/' else '%s.html' % path
			ext = '.html'

		return path, ext

	def update_asset(self, path, content, uploaded=None):
		if uploaded is not None:
			if uploaded.filename.endswith('zip'):
				site_zip = zipfile.ZipFile(uploaded.file,'r')
				self._save_zipped_files(site_zip)
				return

			asset = Asset(id=path, content=self.request.get('asset'), mime=get_mime(uploaded.filename))
		else:
			asset = Asset(id=path, content=content, mime=get_mime(path))

		asset.put()

	def delete_asset(self, asset):
		if asset:
			asset.key.delete()

		return 'OK'

	def _save_zipped_files(self, site_zip):
		for p in site_zip.infolist():
			logging.debug('saving %s', p.filename)
			asset = Asset(id= '/%s' % p.filename, content=site_zip.read(p), mime=get_mime(p.filename))
			asset.put()


application = webapp2.WSGIApplication([
	webapp2.Route('/_site/admin', handler=AdminHandler),
	webapp2.Route('/_site/admin/download_release', handler=AdminHandler, handler_method='download_release'),
	webapp2.Route('/_site/admin/download', handler=AdminHandler, handler_method='download'),
	webapp2.Route('/_site/admin/fetch', handler=AdminHandler, handler_method='fetch'),
	webapp2.Route('/_site/config/refresh', handler=ConfigHandler),
	webapp2.Route('/api/apply', handler=ApplyHandler),
	webapp2.Route(r'/<path:.*>', handler=AssetHandler)], debug=True)
