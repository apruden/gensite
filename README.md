# Gensite

GAE application to manage static content.

## Features

  * Online edit
  * Batch upload (zip files)
  * Templating (using jinja2)

## Architecture

All content is saved as `BlobProperty` data on Datastore (NDB) and cached using memcache service. Multitenancy is supported so a single GAE application can serve multiple domains.

A simple RESTful API is provided to edit content.

#TODO

  * Integrate with GitHub.
