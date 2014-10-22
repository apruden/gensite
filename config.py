import logging, json, base64, time
from model import Site, Settings
from google.appengine.ext import ndb
from google.appengine.api import memcache, namespace_manager


default_settings = {
		'cache_enabled': False,
		'editors': '',
		'sender': 'alex.prudencio@gmail.com',
		'webadmin': 'alex@primefactor.solutions',
		'mapping': '{}'
}


def ensure_global_settings():
	current_namespace = namespace_manager.get_namespace()
	namespace_manager.set_namespace('global')
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

	namespace_manager.set_namespace(current_namespace)
	logging.info('Running with settings %s', settings)


ensure_global_settings()
_last_config_refreshes = {}


class SettingsProxy(object):
	def __init__(self):
		self.settings = None

	def __getattr__(self, name):
		namespace = namespace_manager.get_namespace()
		now = time.time()
		if not self.settings or now >= _last_config_refreshes.get(namespace, now - 300) + 300:
			self.settings = ndb.Key(Settings, '_settings').get(use_cache=False, use_memcache=False)
			if not self.settings:
				self.settings = Settings(id='_settings')

			settings_updated = False

			for s, v in default_settings.items():
				if not hasattr(self.settings, s):
					setattr(self.settings, s, v)
					settings_updated = True

			if settings_updated:
				self.settings.put()
				logging.info('Settings refreshed.')

			_last_config_refreshes[namespace] = now

		return getattr(self.settings, name)


settings = SettingsProxy()
