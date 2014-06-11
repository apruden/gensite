import webapp2, jinja2, os, logging, StringIO
from google.appengine.ext import ndb
from google.appengine.api import memcache


EDITABLE = ['.html', '.css', '.json', '.js']


def load_template(path):
	asset = ndb.Key(Asset, path).get()
	if asset:
		return asset.content


def get_mime(path):
	if path == '/':
		return 'text/html'

	mime_dict = {
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
			'': 'application/octet-stream'
			}

	return mime_dict[os.path.splitext(path)[1]]


JINJA_SITE_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FunctionLoader(load_template),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)


JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.join(os.path.dirname(__file__), 'templates')),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)


class Asset(ndb.Model):
	content = ndb.BlobProperty()
	mime = ndb.StringProperty()


class AssetHandler(webapp2.RequestHandler):
	def get(self, path):
		path = self.request.path

		if 'admin' in self.request.GET:
			if 'delete' in self.request.GET:
				asset = ndb.Key(Asset, self.request.path).get()
				if asset:
					asset.key.delete()
				self.reponse.write('OK')
				return
			template_content = load_template(self.request.path) or ''
			self.response.write(JINJA_ENVIRONMENT.get_template('upload.html').render({
				'content': template_content,
				'editable': (self.request.path == '/' and 'upload' not in self.request.GET) or os.path.splitext(self.request.path)[1] in EDITABLE}))
			return

		asset = memcache.get(self.request.path)

		if not asset:
			logging.info('cache miss')

			if path.endswith('.html') or path == '/':
				t = JINJA_SITE_ENVIRONMENT.get_template(path)

				if not t:
					self.response.status = 404
					self.response.write('Not found')
					return

				asset = Asset(content=str(t.render({})), mime='text/html')
			else:
				asset = ndb.Key(Asset, self.request.path).get()

				if not asset:
					self.response.status = 404
					self.response.write('Not found')
					return

			memcache.add(path, asset, 3600)

		self.response.cache_control = 'public'
		self.response.cache_control.max_age = 300
		self.response.headers['Content-Type'] = str(asset.mime)
		self.response.write(asset.content)

	def post(self, path):
		import zipfile

		if hasattr(self.request.POST['asset'], 'file'):
			logging.info('saving file %s', self.request.path)
			uploaded = self.request.POST['asset']

			if uploaded.filename.endswith('zip'):
				site_zip = zipfile.ZipFile(uploaded.file,'r')
				self._save_zip_files(site_zip)
				return

			asset = Asset(id=self.request.path, content=uploaded.file.read(), mime=get_mime(uploaded.filename))
		else:
			logging.info('saving content %s', self.request.path)
			asset = Asset(id=self.request.path, content=str(self.request.POST['asset']), mime=get_mime(self.request.path))

		asset.put()

	def _save_zip_files(self, site_zip):
		for p in site_zip.infolist():
			logging.info('saving %s', p.filename)
			asset = Asset(id= '/%s' % p.filename, content=site_zip.read(p), mime=get_mime(p.filename))
			asset.put()


application = webapp2.WSGIApplication([('/(.*)', AssetHandler)], debug=True)
