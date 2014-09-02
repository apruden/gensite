import webapp2, jinja2, os, logging, StringIO, zipfile
from google.appengine.ext import ndb
from google.appengine.api import memcache
from google.appengine.api.users import get_current_user, create_login_url

EDITABLE = ['.html', '.css', '.json', '.js', '.txt', '.xml', '.do']
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
		'.svg': 'image/svg+xml'
		}


code_cache = {}


class Settings(ndb.Expando):
	pass


settings = ndb.Key(Settings, '_settings').get()


if not settings:
	logging.debug('Settings not found. Init.')
	settings = Settings(id='_settings', cache_enabled=False, editors='')
	settings.put()

logging.debug('Running with settings %s', settings)


def load_asset_content(path):
	asset = ndb.Key(Asset, path).get()
	if asset:
		return asset.content


def get_mime(path):
	return MIME_DICT.get(os.path.splitext(path)[1], 'application/octet-stream')


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


class AppSetting(ndb.Model):
	name = ndb.StringProperty()
	value = ndb.StringProperty()


class Asset(ndb.Model):
	content = ndb.BlobProperty()
	mime = ndb.StringProperty()


class ConfigHandler(webapp2.RequestHandler):
	def get(self):
		global settings
		found = ndb.Key(Settings, '_settings').get(use_cache=False, use_memcache=False)
		if found:
			logging.info('Config refreshed: %s', found)
			settings = found


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

		if ext == '.do':
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
		if not user or user.email() not in settings.editors:
			logging.warning('user %s not found in editors %s', user.email(), settings.editors)
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
		if uploaded.filename.endswith('zip'):
			site_zip = zipfile.ZipFile(uploaded.file,'r')
			self._save_zipped_files(site_zip)
			return

		if uploaded:
			asset = Asset(id=path, content=uploaded.file.read(), mime=get_mime(uploaded.filename))
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
	('/config/refresh', ConfigHandler),
	('/(.*)', AssetHandler)], debug=True)
