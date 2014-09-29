from google.appengine.ext import ndb


class Settings(ndb.Expando):
	mapping = ndb.JsonProperty()


class Site(ndb.Model):
	owner = ndb.StringProperty()
	repo = ndb.StringProperty()
	current_sha = ndb.StringProperty()
	current_sha_date = ndb.StringProperty()


class Asset(ndb.Model):
	content = ndb.BlobProperty()
	mime = ndb.StringProperty()
	fullpath = ndb.StringProperty()


class DataEntry(ndb.Expando):
	data = ndb.TextProperty()

