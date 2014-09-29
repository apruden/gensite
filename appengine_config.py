import os
from model import Settings
from google.appengine.api import namespace_manager
from google.appengine.ext import ndb


mapping = None


def _get_namespace(domain):
	global mapping
	if mapping is None:
		namespace_manager.set_namespace('global')
		settings = ndb.Key(Settings, '_settings').get()
		mapping = settings.mapping if settings else {}
		mapping = mapping or {}

	return mapping.get(domain, domain)


def namespace_manager_default_namespace_for_request():
	return _get_namespace(os.environ['SERVER_NAME'])
