import webapp2, jinja2, os, logging, StringIO, zipfile, json, base64, urllib, time
import mime as mimeutil, config
from hashlib import sha1
from model import Asset, Site, Settings, DataEntry
from git import GitClient
from google.appengine.ext import ndb
from google.appengine.api import memcache, mail, urlfetch, namespace_manager
from google.appengine.api.users import get_current_user, create_login_url

logging.getLogger().setLevel(logging.INFO)

_code_cache = {}


def load_asset_content(fullpath):
    asset = Asset.query(Asset.fullpath == fullpath).fetch(1)
    if asset: return asset[0].content


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


def _extract_zipped_files(site_zip, prefix=''):
    folder_name = site_zip.infolist()[0].filename
    return [(_get_path(p.filename.replace(folder_name, ''), prefix),
        site_zip.read(p),
        '%s/%s' % (prefix, p.filename.replace(folder_name, '').lstrip('/')),
        mimeutil.get_mime(p.filename)) for p in site_zip.infolist() if p.file_size]


def _get_fullpath(path, mime=None):
    path = '/%s' % path.lstrip('/')
    if path == '/': path = '/index.html'
    ext = os.path.splitext(path)[1]
    if ext: return path, mimeutil.get_mime(ext=ext)
    fullpath = '%s%s' % (path, mimeutil.get_ext(mime))

    return fullpath, mime


def _get_path(filename, prefix=''):
    return '%s/%s' % (prefix,
            filename.replace('index.html', '').replace('.html', '').replace('.py', '').lstrip('/'))


class RefreshHandler(webapp2.RequestHandler):
    def get(self):
        try: res = urlfetch.fetch(url='http://quizwiz.azurewebsites.net/home/ping', method=urlfetch.GET)
        except Exception, e: logging.info('Error refreshing site %s', e)


class AdminHandler(webapp2.RequestHandler):

    def get(self):
        site = self._get_site()

        if site.repo:
            owner, repo = site.repo.split('/')
            git = GitClient(owner, repo, site.github_token)
            commits = git.get_repos('/commits')
        else:
            commits = []

        self.response.write(JINJA_ENVIRONMENT.get_template('admin.html').render({
                'commits': commits,
                'current_sha': site.current_sha or '',
                'repo': site.repo or ''}))

    def post(self):
        site = self._get_site()
        site.repo = self.request.POST['repo']
        site.put()

    def _get_site(self):
        site = ndb.Key(Site, '_site').get()

        if not site:
            logging.error('Saving site')
            site = Site(id='_site')
            site.github_token = ''
            site.put()

        return site

    def download_commit(self):
        commit_id = self.request.POST['commit_id']
        site = self._get_site()
        owner, repo = site.repo.split('/')
        git = GitClient(owner, repo, site.github_token)
        res = git.get_repos('/zipball/%s' % commit_id, binary=True)
        res = StringIO.StringIO(res)
        site_zip = zipfile.ZipFile(res,'r')
        assets = _extract_zipped_files(site_zip, '')
        assets = [Asset(id=a[0], content=a[1], fullpath=a[2], mime=a[3]) for a in assets]
        ndb.put_multi(assets)

        site = self._get_site()
        site.current_sha = commit_id
        site.put()

    def download(self):
        q = Asset.query()
        assets = q.fetch(100)
        output = StringIO.StringIO()

        with zipfile.ZipFile(output, 'w') as zf:
            for a in assets:
                zf.writestr(a.fullpath.lstrip('/'), a.content)

        self.response.headers['Content-Type'] = 'application/zip'
        self.response.headers['Content-Disposition'] = 'attachment; filename="%s"' % 'site.zip'
        self.response.write(output.getvalue())


class AssetHandler(webapp2.RequestHandler):
    def get(self, path):
        path = path or '/'
        path = '/%s' % path.lstrip('/')
        logging.info('namespaces %s', namespace_manager.get_namespace())

        if '_admin' in self.request.GET:
            asset = ndb.Key(Asset, path).get(use_cache=False, use_memcache=False)
            return self._edit_form(path, asset)

        rendered_content = memcache.get(path) if '_nocache' not in self.request.GET else None

        if not rendered_content:
            logging.info('cache miss path %s', path)
            asset = ndb.Key(Asset, path).get(use_cache=False, use_memcache=False)

            if not asset:
                self.abort(404)

            if asset.mime == 'text/x-python':
                if path not in _code_cache:
                        cobj = compile(asset.content, '', 'exec')
                        _code_cache[path] = cobj
                globs = globals()
                globs.update({'request': self.request, 'response': self.response, 'settings': config.settings})
                exec _code_cache[path] in globs
                return eval('handle()', globs)
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
        path = '/%s' % path.lstrip('/')
        asset = ndb.Key(Asset, path).get()

        if not asset and not self.request.get('_create'):
            logging.warning('Asset not found for editing %s', path)
            self.abort(404)

        if not any(k in self.request.POST for k in ['_delete', '_edit', '_create']):
            if asset.mime != 'text/x-python': self.abort(404)

            if path not in _code_cache:
                cobj = compile(asset.content, '', 'exec')
                _code_cache[path] = cobj

            globs = globals()
            globs.update({'request': self.request, 'response': self.response, 'settings': config.settings})
            exec _code_cache[path] in globs
            return eval('handle()', globs)

        if '_delete' in self.request.POST:
            asset = ndb.Key(Asset, path).get()
            if asset: asset.key.delete()

            return

        logging.info('saving content %s', path)
        uploaded = None

        if hasattr(self.request.POST['asset'], 'file'):
            uploaded = self.request.POST['asset']

        self._save_asset(path, str(self.request.POST['asset']), uploaded, self.request.get('mime'))

    def _get_rendered_content(self, fullpath):
        try: template = JINJA_SITE_ENVIRONMENT.get_template(fullpath)
        except jinja2.TemplateNotFound: self.abort(404)

        return template.render({})

    def _edit_form(self, path, asset):
        user = get_current_user()
        if config.settings.editors and (not user or user.email() not in config.settings.editors):
            logging.warning('user %s not found in editors %s', user, config.settings.editors)
            return self.redirect(create_login_url('/'))

        create = False

        if not asset:
            logging.info('Creating asset %s', path)
            create = True
            asset = Asset(fullpath=path)

        _, ext = os.path.splitext(asset.fullpath or path)

        if 'upload' in self.request.GET:
            self.response.write(JINJA_ENVIRONMENT.get_template('asset_upload.html').render({}))
        else:
            self.response.write(JINJA_ENVIRONMENT.get_template('asset_edit.html').render({
                'mimes': mimeutil.MIME_DICT,
                'content': asset.content or '',
                'fullpath': asset.fullpath or '',
                'mime': asset.mime or mimeutil.get_mime(path),
                'create': create or ''}))

    def _save_asset(self, path, content, uploaded=None, mime=None):
        global _code_cache
        if uploaded is not None:
            if uploaded.filename.endswith('zip'):
                site_zip = zipfile.ZipFile(uploaded.file,'r')
                assets = _extract_zipped_files(site_zip, path if path != '/' else '')
            else:
                mime = mimeutil.get_mime(uploaded.filename)
                fullpath, mime = _get_fullpath(path, mime)
                assets = [(path, self.request.get('asset'), fullpath, mime)]
        else:
            fullpath, mime = _get_fullpath(path, mime)
            assets = [(path, content, fullpath, mime)]

        assets = [Asset(id=a[0], content=a[1], fullpath=a[2], mime=a[3]) for a in assets]
        ndb.put_multi(assets)
        _code_cache = {}
