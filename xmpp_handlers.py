import logging
import base64
import re

from xmlparse import xml2list
ALL_TAGS = "_ALL_TAGS_"



class Handler(object):
    def initialize(self, client):
        self.client = client
    
    def handle(self, data, content=None):
        raise NotImplemented

class SingleTagHandler(Handler):
    def handle(self, data, content=None):
        # logging.debug('%r %r', data, content)
        self.client.remove_handler(self)
        return True

class MessageHandler(Handler):
    """Reads an incoming message, calling the client message_cb"""
    def handle(self, data, content=None):
        self.data = [data]
        if content:
            self.data.append(content)
        self.client.read_until("</message>", self._finish_message)
    
    def _finish_message(self, data):
        self.data.append(data)
        message = ''.join(self.data)
        logging.debug('Message: %r', message)
        xml = xml2list(message)[0]
        # logging.debug(xml)
        self.client.message_cb(xml)
        self.client.read_next() # give control back to the client

class IQHandler(Handler):
    """Reads an iq message, and calls any registered callbacks"""
    def __init__(self):
        self._handlers = {}
    
    def handle(self, data, content=None):
        self.data = [data]
        if content:
            self.data.append(content)
        self.client.read_until("</iq>", self._finish_message)
    
    def add_handler(self, for_id, callback):
        if isinstance(for_id, (int, long)):
            for_id = str(for_id)
        assert for_id not in self._handlers
        self._handlers[for_id] = callback
    
    def _finish_message(self, data):
        for_id = re.findall(r'id="(.*?)"', self.data[0])[0]
        self.data.append(data)
        message = ''.join(self.data)
        logging.debug('IQ: %r', message)
        
        # if we have a match
        if for_id in self._handlers:
            callback = self._handlers.pop(for_id)
            xml = xml2list(message)[0]
            # logging.debug(xml)
            callback(xml)
        
        self.client.read_next() # give control back to the client

class PresenceHandler(Handler):
    def handle(self, data, content=None):
        if data.endswith("/>"):
            logging.debug('Presence: %r', data)
            xml = xml2list(data)[0]
            # logging.debug(xml)
            self.client.presence_cb(xml)
            return True
        else:
            self.data = [data]
        if content:
            self.data.append(content)
            
        self.client.read_until("</presence>", self._finish_message)
    
    def _finish_message(self, data):
        self.data.append(data)
        message = ''.join(self.data)
        logging.debug('Presence: %r', message)
        xml = xml2list(message)[0]
        # logging.debug(xml)
        self.client.presence_cb(xml)
        self.client.read_next() # give control back to the client

class AuthHandler(Handler):
    def initialize(self, client):
        self.client = client
        logging.info('authenticating as %s@%s', self.client.username, self.client.domain)
        # http://stackoverflow.com/questions/5209568/how-does-xmpp-client-select-an-authentication-mechanism
        auth_str = base64.b64encode("\x00%s@%s\x00%s" % (self.client.username, self.client.domain, self.client.password))
        jid_domain_change = ''' xmlns:ga="http://www.google.com/talk/protocol/auth" ga:client-uses-full-bind-result="true"'''
        self.client.write("""<auth xmlns="urn:ietf:params:xml:ns:xmpp-sasl" mechanism="PLAIN"%s>%s</auth>""" % (jid_domain_change, auth_str))

    def handle(self, data, content=None):
        # logging.debug('data: %r content: %r', data, content)
        if not data.startswith("<success "):
            logging.error(data)
            return self.client.stream.read_until_close(logging.error)
        self.client.remove_handler(self)
        
        # http://code.google.com/apis/talk/jep_extensions/jid_domain_change.html
        self.client.write("""<stream:stream to="%s" version="1.0" xmlns:stream="http://etherx.jabber.org/streams" xmlns="jabber:client">""" % self.client.domain)
        self.client.push_handler("stream:features", FeaturesHandler())
        self.client.push_handler("stream:stream", SingleTagHandler())
        return True
        

class ReadLoopHandler(Handler):
    def handle(self, data, content=None):
        logging.debug('ReadLoopHandler: data: %r content: %r', data, content)
        return True

class FeaturesHandler(Handler):
    def handle(self, data, content=None):
        # logging.debug('data: %r', data)
        self.client.read_until("</stream:features>", self._finish_features)
    
    def _finish_bind(self, data):
        # logging.debug('_finish_bind:.... %r', data)
        self.client.pop_handlers() # remove the iq handler
        
        # <iq id="2" type="result"><bind xmlns="urn:ietf:params:xml:ns:xmpp-bind"><jid>user@domain/jid1802227C</jid></bind></iq>
        jid = data.find("jid").data
        logging.info('received bind response. setting jid to %r', jid)
        self.client.set_jid(jid)


# <iq type='get' to='gmail.com'>
#   <query xmlns='http://jabber.org/protocol/disco#info'/>
# </iq>
            # self.client.iq(type="get", attrs=' to="gmail.com"', body='<query xmlns="http://jabber.org/protocol/disco#info"/>')

            # query = """<query xmlns="jabber:iq:roster" xmlns:gr="google:roster" gr:ext="2"/>"""
            # #self.client. write("""<iq from="%s" type="get" id="google-roster-1">%s</iq>""" % (self.client.jid, query))
            # self.client.iq(type="get", id_str="google-roster-1", from_str=True, body=query)
            # # [request]    <iq type="get" id="3" from="-[removed]@chat.facebook.com/[removed]"><query xmlns="jabber:iq:roster"/></iq>
        self.client.iq(type="get", id_str=self.client.get_sequence(), from_str=True, body='<query xmlns="jabber:iq:roster"/>')
        self.client.set_connected()
    
    def _finish_features(self, data):
        logging.debug('features: %r' % data)
        data = re.sub('[\n\r]', '', data)
        if '<starttls' in data:
            self.client.remove_handler(self)
            self.client.upgrade_to_tls()
        
        elif '<mechanism>PLAIN</mechanism>' in data:
            # logging.debug('start auth')
            self.client.remove_handler(self)
            self.client.add_handler(ALL_TAGS, AuthHandler())
            self.client.read_next() # give control back to the client
        elif '<bind xmlns="urn:ietf:params:xml:ns:xmpp-bind"/>' in data:
            # initiate a bind
            # bind_id = uuid.uuid4().hex
            resource = self.client.resource
            logging.info('binding to resource %r' % resource)
            body = """<bind xmlns="urn:ietf:params:xml:ns:xmpp-bind"><resource>%s</resource></bind>""" % resource
            id_str = self.client.get_sequence()
            self.client.iq(type="set", id_str=id_str, body=body)
            
            iq_handler = IQHandler()
            self.client.push_handler("iq", iq_handler)
            iq_handler.add_handler(id_str, self._finish_bind)
            self.client.read_next() # give control back to the client

            return True
        else:
            raise NotImplemented
