import webapp2, jinja2, os, logging, StringIO, zipfile, json, base64, urllib, time
import mime as mimeutil, config
from model import Asset, Site, Settings, DataEntry
from git import GitClient
from google.appengine.ext import ndb
from google.appengine.api import memcache, mail, urlfetch, namespace_manager
from google.appengine.api.users import get_current_user, create_login_url

logging.getLogger().setLevel(logging.DEBUG)

_code_cache = {}


def load_asset_content(fullpath):
	asset = Asset.query(Asset.fullpath == fullpath).fetch(1)
	if asset:
		return asset[0].content


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


def _get_fullpath(path, mime):
	path = '/%s' % path.lstrip('/')

	if path == '/':
		path = '/index'

	ext = os.path.splitext(path)[1]

	if ext:
		return path, mimeutil.get_mime(ext)

	fullpath = '%s%s' % (path, mimeutil.get_ext(mime))

	return fullpath, mime


def _get_path(filename, prefix=''):
	return '%s/%s' % (prefix, filename.replace('index.html', '').replace('.html', '').replace('.py', '').lstrip('/'))


class ConfigHandler(webapp2.RequestHandler):
	def get(self):
		pass


class AdminHandler(webapp2.RequestHandler):
	def get(self):
		site = ndb.Key(Site, '_site').get()

		if not site:
			site = Site(id='_site')
			site.put()

		commits = [] #git.get_repos('/commits')
		releases = [] #git.get_repos('/releases')
		self.response.write(JINJA_ENVIRONMENT.get_template('admin.html').render({
			'releases':releases, 'commits':commits, 'current_sha': site.current_sha, 'repo': site.repo}))

	def post(self):
		pass

	def download_release(self, release):
		owner, repo = config.settings.repo.split('/')
		git = GitClient(owner, repo)
		asset = git.get_repos('/releases/asset/%s' % (release,))

	def fetch(self):
		owner, repo = config.settings.repo.split('/')
		git = GitClient(owner, repo)
		sha = self.request.get('sha')
		logging.info('fetching %s', sha)
		site = ndb.Key(Site, '_site').get()
		assets = []

		if not site.current_sha:
			tree = git.get_repos('/git/trees/%s?recursive=1' % sha)
			tree = tree['tree']
			for f in tree:
				blob = git.get(f['url'])
				content = base64.decodestring(blob['content'])
				fullpath, mime = _get_fullpath(f['path'])
				assets.append(Asset(id=_get_path(f['path']), content=content, mime=mime, fullpath=fullpath))
				logging.info('Added asset %s', f['path'])
		else:
			diff = git.get_repos('/compare/%s:%s...%s:%s' % (owner, current_sha, owner, sha))
			for f in diff['files']:
				content = git.get(f['contents_url'])
				content = base64.decodestring(content['content'])
				fullpath, mime = _get_fullpath(f['filename'])
				assets.append(Asset(id=_get_path(f['filename']), content=content, mime=mime, fullpath=fullpath))
				logging.info('Updated asset %s', f['filename'])

		ndb.put_multi(assets)
		site.current_sha = sha
		site.put()

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


class AssetHandler(webapp2.RequestHandler):
	def get(self, path):
		path = path or '/'
		path = '/%s' % path.lstrip('/')
		logging.info('namespaces %s', namespace_manager.get_namespace())

		if '_admin' in self.request.GET:
			asset = ndb.Key(Asset, path).get()
			return self._edit_form(path, asset)

		rendered_content = memcache.get(path)

		if not rendered_content:
			logging.info('cache miss path %s', path)
			asset = ndb.Key(Asset, path).get()

			if not asset:
				self.abort(404)

			if asset.mime == 'text/x-python':
				if path not in _code_cache:
					cobj = compile(asset.content, '', 'exec')
					_code_cache[path] = cobj
				exec(_code_cache[path], globals(), {'request': self.request, 'response': self.response})
				return
			elif asset.mime == 'text/html':
				rendered_content = (self._get_rendered_content(asset.fullpath), asset.mime)
			else:
				rendered_content = (asset.content, asset.mime)

			if config.settings.cache_enabled:
				logging.debug('adding to cache')
				memcache.add(path, rendered_content, 3600)

		self.response.cache_control = 'public'
		self.response.cache_control.max_age = 48000
		self.response.headers['Content-Type'] = str(rendered_content[1])
		self.response.write(rendered_content[0])

	def post(self, path):
		path = path or '/'
		asset = ndb.Key(Asset, path).get()

		if not asset and not self.request.get('_create'):
			self.abort(404)

		if not any(k in self.request.POST for k in ['_delete', '_edit', '_create']):
			if asset.mime != 'text/x-python':
				self.abort(404)

			if path not in _code_cache:
				cobj = compile(asset.content, '', 'exec')
				_code_cache[path] = cobj

			exec _code_cache[path] in globals(), {'request': self.request, 'response': self.response}
			return

		if '_delete' in self.request.POST:
			asset = ndb.Key(Asset, path).get()

			if asset:
				asset.key.delete()

			return

		logging.debug('saving content %s', path)
		uploaded = None

		if hasattr(self.request.POST['asset'], 'file'):
			uploaded = self.request.POST['asset']

		self._save_asset(path, str(self.request.POST['asset']), uploaded, self.request.get('mime'))

	def _get_rendered_content(self, fullpath):
		try:
			template = JINJA_SITE_ENVIRONMENT.get_template(fullpath)
		except jinja2.TemplateNotFound:
			self.abort(404)

		return template.render({})

	def _edit_form(self, path, asset):
		user = get_current_user()
		if config.settings.editors and (not user or user.email() not in config.settings.editors):
			logging.warning('user %s not found in editors %s', user, config.settings.editors)
			return self.redirect(create_login_url('/'))

		create = False

		if not asset:
			create = True
			asset = Asset()

		_, ext = os.path.splitext(path)

		if 'upload' in self.request.GET or ext not in mimeutil.EDITABLE:
			self.response.write(JINJA_ENVIRONMENT.get_template('asset_upload.html').render({}))
		else:
			self.response.write(JINJA_ENVIRONMENT.get_template('asset_edit.html').render({
				'mimes': mimeutil.MIME_DICT,
				'content': asset.content or '',
				'fullpath': asset.fullpath or '',
				'mime': asset.mime or 'text/html',
				'create': create or ''}))

	def _save_asset(self, path, content, uploaded=None, mime=None):
		if uploaded is not None:
			if uploaded.filename.endswith('zip'):
				site_zip = zipfile.ZipFile(uploaded.file,'r')
				assets = self._extract_zipped_files(site_zip, path if path != '/' else '')
			else:
				fullpath, mime = _get_fullpath(path, mime)
				assets = [(path, self.request.get('asset'), fullpath, mime)]
		else:
			fullpath, mime = _get_fullpath(path, mime)
			assets = [(path, content, fullpath, mime)]

		assets = [Asset(id=a[0], content=a[1], fullpath=a[2], mime=a[3]) for a in assets]
		ndb.put_multi(assets)

	def _extract_zipped_files(self, site_zip, prefix=''):
		return [(_get_path(p.filename, prefix), site_zip.read(p), '%s/%s' % (prefix, p.filename.lstrip('/')), mimeutil.get_mime(p.filename)) for p in site_zip.infolist()]
