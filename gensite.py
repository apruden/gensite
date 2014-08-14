import webapp2, jinja2, os, logging, StringIO
from google.appengine.ext import ndb
from google.appengine.api import memcache


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


def load_template(path):
	asset = ndb.Key(Asset, path).get()
	if asset:
		return asset.content


def get_mime(path):
	return MIME_DICT.get(os.path.splitext(path)[1], 'application/octet-stream')


JINJA_SITE_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FunctionLoader(load_template),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True,
	cache_size=0)


JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.join(os.path.dirname(__file__), 'templates')),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True,
	cache_size=0)


class Asset(ndb.Model):
	content = ndb.BlobProperty()
	mime = ndb.StringProperty()


class AssetHandler(webapp2.RequestHandler):
	def get(self, path):
		path = self.request.path
		ext = os.path.splitext(path)[1]

		if not ext:
			path = '/index.html' if path == '/' else '%s.html' % path
			ext = '.html'

		if 'admin' in self.request.GET:
			if 'delete' in self.request.GET:
				asset = ndb.Key(Asset, path).get()
				if asset:
					asset.key.delete()
				self.reponse.write('OK')
				return
			template_content = load_template(path) or ''
			self.response.write(JINJA_ENVIRONMENT.get_template('upload.html').render({
				'content': template_content,
				'editable': 'upload' not in self.request.GET and ext in EDITABLE}))
			return

		asset = memcache.get(path)

		if not asset:
			logging.debug('cache miss')
			if path.endswith('.html'):
				t = JINJA_SITE_ENVIRONMENT.get_template(path)

				if not t:
					self.response.status = 404
					self.response.write('Not found')
					return

				asset = Asset(content=str(t.render({})), mime='text/html')
			else:
				asset = ndb.Key(Asset, path).get()

				if not asset:
					self.response.status = 404
					self.response.write('Not found')
					return


			if os.environ['CACHE_ENABLED'].lower() != 'false':
				logging.debug('adding to cache')
				memcache.add(path, asset, 3600)

		self.response.cache_control = 'public'
		self.response.cache_control.max_age = 48000
		self.response.headers['Content-Type'] = str(asset.mime)

		if ext == '.do':
			exec(asset.content, {'response': self.response}, {})
		else:
			self.response.headers['Content-Type'] = str(asset.mime)
			self.response.write(asset.content)

	def post(self, path):
		import zipfile
		path = self.request.path
		ext = os.path.splitext(path)[1]

		if not ext:
			path = '/index.html' if path == '/' else '%s.html' % path

		if hasattr(self.request.POST['asset'], 'file'):
			logging.debug('saving file %s', path)
			uploaded = self.request.POST['asset']

			if uploaded.filename.endswith('zip'):
				site_zip = zipfile.ZipFile(uploaded.file,'r')
				self._save_zip_files(site_zip)
				return

			asset = Asset(id=path, content=uploaded.file.read(), mime=get_mime(uploaded.filename))
		else:
			logging.debug('saving content %s', path)
			asset = Asset(id=path, content=str(self.request.POST['asset']), mime=get_mime(path))

		asset.put()

	def _save_zip_files(self, site_zip):
		for p in site_zip.infolist():
			logging.debug('saving %s', p.filename)
			asset = Asset(id= '/%s' % p.filename, content=site_zip.read(p), mime=get_mime(p.filename))
			asset.put()


application = webapp2.WSGIApplication([('/(.*)', AssetHandler)], debug=True)
