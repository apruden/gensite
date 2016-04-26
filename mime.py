import os


EDITABLE = {'.html': 'html',
        '.css': 'css',
        '.json': 'json',
        '.js': 'javascript',
        '.txt': 'text',
        '.xml': 'xml',
        '.py': 'python',
        '.md': 'markdown'}


MIME_DICT = {'.html': 'text/html',
        '.json': 'application/json',
        '.css': 'text/css',
        '.js': 'application/javascript',
        '.jpg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.ttf': 'application/x-font-ttf',
        '.woff': 'application/x-font-woff',
        '.eot': 'application/vnd.ms-fontobject',
        '.txt': 'text/plain',
        '.xml': 'text/xml',
        '.svg': 'image/svg+xml',
        '.md': 'text/x-markdown',
        '.py': 'text/x-python'}


REVERSE_MIME_DICT = dict((v, k) for k, v in MIME_DICT.items())


def get_mime(path=None, ext=None):
	ext = ext or os.path.splitext(path)[1]
	return MIME_DICT.get(ext, 'application/octet-stream')


def get_ext(mime):
	return REVERSE_MIME_DICT.get(mime, '.bin')
