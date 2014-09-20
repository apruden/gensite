from google.appengine.ext import ndb


class Settings(ndb.Expando):
	pass


class AppSetting(ndb.Model):
	name = ndb.StringProperty()
	value = ndb.StringProperty()


class Site(ndb.Model):
	owner = ndb.StringProperty()
	repo = ndb.StringProperty()
	current_sha = ndb.StringProperty()
	current_sha_date = ndb.StringProperty()


class Asset(ndb.Model):
	content = ndb.BlobProperty()
	mime = ndb.StringProperty()


class DataEntry(ndb.Expando):
	data = ndb.TextProperty()

