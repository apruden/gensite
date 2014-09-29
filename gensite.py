import logging, webapp2, controller


application = webapp2.WSGIApplication([webapp2.Route('/_site/admin', handler=controller.AdminHandler),
	webapp2.Route('/_site/admin/download_release', handler=controller.AdminHandler, handler_method='download_release'),
	webapp2.Route('/_site/admin/download', handler=controller.AdminHandler, handler_method='download'),
	webapp2.Route('/_site/admin/fetch', handler=controller.AdminHandler, handler_method='fetch'),
	webapp2.Route('/_site/config/refresh', handler=controller.ConfigHandler),
	webapp2.Route(r'/<path:.*>', handler=controller.AssetHandler)], debug=True)

