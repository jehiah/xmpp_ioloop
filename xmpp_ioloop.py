import logging
import socket
import ssl
import time

import tornado.iostream
import tornado.ioloop

# note: this iostream must be a tornado 2.2+ iostream.
# the version from tornado 1.2 does not support ssl.PROTOCOL_TLSv1 properly
assert tornado.version_info >= (2, 1), "XMPPIOLoopClient is incompatible with this version tornado ioloop"

from xmpp_handlers import Handler, MessageHandler, IQHandler, PresenceHandler, FeaturesHandler, ALL_TAGS
NS_CLIENT = 'jabber:client'
NS_STREAM = 'http://etherx.jabber.org/streams'

class XMPPIOLoopClient(object):
    def __init__(self, host, port=5222, domain=None, io_loop=None, username=None, password=None, resource=None):
        self.host = host
        self.port = port
        self.domain = domain or host
        self.username = username
        self.password = password
        self.resource = resource
        self._jid = username + '@' + domain + '/' + resource
        self._full_jid = None
        self.io_loop = io_loop or tornado.ioloop.IOLoop.instance()
        
        self._current_processors = []
        self._process_stack = []
        self._connected = False
        self._sequence = 1
        self.autoreconnect = True
        self.autoreconnect_tries = 0
        self.autoreconnect_last_connect = None
    
    @property
    def jid(self):
        return self._full_jid or self.jid
    
    def set_jid(self, jid):
        assert jid.startswith(self._jid[:10]) # it seems to always have the same 10 char's anyway
        self._full_jid = jid
    
    def stream_close_cb(self):
        self._connected = False
        logging.warning('xmpp stream closed')
        if self.close_cb:
            self.close_cb()
        
        now = time.time()
        reconnect_delay = self.autoreconnect_tries * self.autoreconnect_tries
        if now - reconnect_delay > self.autoreconnect_last_connect:
            # re-set the count
            self.autoreconnect_tries = 0
        
        if self.autoreconnect:
            self.autoreconnect_tries += 1
            min_connect_time = self.autoreconnect_last_connect + reconnect_delay
            if min_connect_time <= now:
                # go ahead and connect
                logging.info('running reconnect now')
                self._connect()
            else:
                logging.warning('reconnecting in %0.2f seconds', min_connect_time - now)
                self.io_loop.add_timeout(min_connect_time, self._connect)
    
    
    ##########
    def push_handler(self, tag, handler):
        if self._current_processors:
            self._process_stack.insert(0, self._current_processors)
            self._current_processors = []
        self.add_handler(tag, handler)
    
    def pop_handlers(self):
        if not self._process_stack:
            raise Exception("No handlers defined")
        self._current_processors = self._process_stack.pop()
    
    def add_handler(self, tag, handler):
        handler.initialize(self)
        self._current_processors.append((tag, handler))
    
    def remove_handler(self, tag, klass=None):
        if isinstance(tag, Handler):
            self._current_processors = [(t, k) for t, k in self._current_processors if k is not tag]
        else:
            self._current_processors = [(t, k) for t, k in self._current_processors if t != tag and k is not klass]
        
    ########
    def connect(self, connect_cb, presence_cb, message_cb, close_cb=None):
        assert not self._connected
        assert callable(connect_cb)
        assert callable(presence_cb)
        assert callable(message_cb)
        if close_cb:
            assert callable(close_cb)
        self.connect_cb = connect_cb
        self.presence_cb = presence_cb
        self.message_cb = message_cb
        self.close_cb = close_cb
        self._connect()
    
    def _connect(self):
        self._connected = False
        self._full_jid = None
        self._current_processors = []
        self._process_stack = []
        self.autoreconnect_last_connect = time.time()
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        self.stream = tornado.iostream.IOStream(self.socket)
        self.stream.set_close_callback(self.stream_close_cb)
        logging.info('connecting to %r %r' % (self.host, self.port))
        self.stream.connect((self.host, self.port), self.initialize_stream)
    
    def read_next(self):
        # logging.debug('read_next tag')
        try:
            self.stream.read_until(">", self._start_tag)
        except IOError:
            logging.exception('socket error')
    
    def read_until(self, tag, callback):
        # logging.debug('reading till %r', tag)
        try:
            self.stream.read_until(tag, callback)
        except IOError:
            logging.exception('socket error')
    
    def _start_tag(self, data):
        # this is the main tag read loop
        # logging.debug('_start_tag: %r', data)
        if not data.lstrip().startswith("<"):
            node_content, tag = data.split("<", 1)
        else:
            node_content = None
            tag = data.lstrip()
        tag_name = tag.strip(">").strip("<").split(" ", 1)[0]
        
        handler = None
        if not self._current_processors:
            self.pop_handlers()
        for needle, possible_handler in self._current_processors:
            if needle == tag_name or needle is ALL_TAGS:
                handler = possible_handler
                break
        assert handler
        if handler.handle(tag, content=node_content):
            self.read_next()
    
    #################
    
    def get_sequence(self):
        self._sequence += 1
        return self._sequence
    
    def write(self, data):
        try:
            logging.debug("W:%r" % data)
            self.stream.write(_utf8(data))
        except IOError:
            logging.exception('failed write for %r' % data)
    
    def presence(self, show=None, status=None, priority=None, to=None, type=None):
        assert self._connected
        if show:
            assert show in ["chat", "away", "dnd", "xa"]
            assert not to
            assert not type
        else:
            assert to
            assert type
            assert not show
            assert not priority
            assert not status
        
        body = ""
        attrs = ""
        
        if show:
            body += "<show>%s</show>" % show
        if status:
            body += "<status>%s</status>" % status
        if priority:
            body += "<priority>%d</priority>" % priority
        
        if to:
            attrs += ' to="%s"' % to
        if type:
            attrs += ' type="%s"' % type
        
        self.write("<presence%s>%s</presence>" % (attrs, body))
    
    def iq(self, type, body, attrs=None, id_str=None, from_str=None):
        attrs = attrs or ''
        if id_str:
            attrs = (' id="%s"' % id_str) + attrs
        if from_str:
            attrs += ' from="%s"' % self.jid
        self.write("""<iq type="%s"%s>%s</iq>""" % (type, attrs, body))
    
    def message(self, to, body):
        # <message to="you@domain.com" type="chat" id="purpleada23077" from="jehiah@domain.com/AdiumCD37AB23">
        #   <active xmlns="http://jabber.org/protocol/chatstates"/>
        #   <body>test</body>
        #   <nos:x xmlns:nos="google:nosave" value="disabled"/>
        #   <arc:record xmlns:arc="http://jabber.org/protocol/archive" otr="false"/>
        # </message>
        # id_str = uuid.uuid4().hex
        self.write(_utf8("""<message to="%(to)s" type="chat" id="%(id_str)s" from="%(jid)s"><body>%(body)s</body></message>"""
        % dict(to=to, body=body, id_str=self.get_sequence(), jid=self.jid)))

    
    #############
    
    def initialize_stream(self, host=None, xmlns_stream=NS_STREAM, xmlns=NS_CLIENT):
        """Initiates the XML stream. Writes the start tag over the socket."""
        # step 2
        if not host:
            host = self.domain
        logging.debug('initialize stream')
        self.write('''<?xml version="1.0" encoding="UTF-8"?>
            <stream:stream xmlns:stream="%s" to="%s" version="1.0"
            xmlns="%s">''' % (xmlns_stream, host, xmlns))
        self.stream.read_until(">", self._finish_connection)
    
    def _finish_connection(self, data):
        # this is the <stream:stream ...> block
        # <stream:stream from="domain.com" id="E44F73FE0D9C659F" version="1.0" xmlns:stream="http://etherx.jabber.org/streams" xmlns="jabber:client">
        logging.debug('_finish_connection: %r', data)
        self.add_handler("stream:features", FeaturesHandler())
        self.read_next()
    
    def upgrade_to_tls(self):
        logging.info('upgrading to tls')
        self.write('<starttls xmlns="urn:ietf:params:xml:ns:xmpp-tls"/>')
        self.stream.read_until("/>", self.finish_tls_upgrade)
    
    def finish_tls_upgrade(self, data):
        # http://xmpp.org/registrar/stream-features.html
        # <proceed xmlns="urn:ietf:params:xml:ns:xmpp-tls"/>
        logging.debug(data)
        assert data.startswith("<proceed")
        logging.info('converting connection to ssl.PROTOCOL_TLSv1')
        ssl_socket = ssl.wrap_socket(self.socket, ssl_version=ssl.PROTOCOL_TLSv1, do_handshake_on_connect=False)
        self.io_loop.remove_handler(self.socket.fileno())
        self.stream = tornado.iostream.SSLIOStream(ssl_socket)
        self.stream.set_close_callback(self.stream_close_cb)
        self.initialize_stream()
    
    def set_connected(self):
        self.iq_handler = IQHandler()
        self.push_handler("message", MessageHandler())
        self.add_handler("iq", self.iq_handler)
        self.add_handler("presence", PresenceHandler())
        self._connected = True
        self.connect_cb()

def _utf8(s):
    if isinstance(s, unicode):
        s = s.encode('utf-8')
    assert isinstance(s, str)
    return s
