import webapp2
import gensite
from unittest import TestCase
from google.appengine.api import memcache
from google.appengine.ext import db
from google.appengine.ext import testbed


class SiteTests(TestCase):

	def setUp(self):
		self.testbed = testbed.Testbed()
		self.testbed.activate()
		self.testbed.init_datastore_v3_stub()
		self.testbed.init_memcache_stub()

	def tearDown(self):
		self.testbed.deactivate()

	def test_get_admin_upload(self):
		request = webapp2.Request.blank('/?admin=1&upload=1')
		response = request.get_response(gensite.application)

		self.assertEqual('200 OK', response.status)


if __name__ == '__main__':
	unittest.main()
