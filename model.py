import json
from google.appengine.ext import ndb


class Settings(ndb.Expando):
    mapping = ndb.StringProperty()

    def set_mapping(self, mapping):
        self.mapping = json.dumps(mapping)

    def get_mapping_dict(self):
        return json.loads(self.mapping)


class Site(ndb.Model):
    owner = ndb.StringProperty()
    repo = ndb.StringProperty()
    github_token = ndb.StringProperty()
    current_sha = ndb.StringProperty()
    current_sha_date = ndb.StringProperty()


class Asset(ndb.Model):
    content = ndb.BlobProperty()
    mime = ndb.StringProperty()
    fullpath = ndb.StringProperty()

    def __str__(self):
        return '%s' % self.fullpath


class DataEntry(ndb.Expando):
    data = ndb.TextProperty()
    file = ndb.BlobProperty()
