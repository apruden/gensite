import os
from google.appengine.api import namespace_manager


def namespace_manager_default_namespace_for_request():
	#return os.environ['SERVER_NAME']
	return 'organic-duality-605.appspot.com'
