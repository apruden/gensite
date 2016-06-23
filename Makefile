GAE_HOME=/home/alex/google_appengine

run:
	python $(GAE_HOME)/dev_appserver.py .

deploy:
	cd .. && python $(GAE_HOME)/appcfg.py update gensite

