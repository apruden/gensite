GAE_HOME=/home/alex/google_appengine

run:
	python $(GAE_HOME)/dev_appserver.py .

deploy:
	gcloud app deploy

