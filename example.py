import logging
import getpass
import tornado.options
import tornado.ioloop
from xmpp_ioloop import XMPPIOLoopClient

class App(object):
    def __init__(self, options):
        self.xmpp_client = XMPPIOLoopClient(
                host="talk.google.com",
                domain=options.google_apps_domain,
                username=options.google_apps_account,
                password=getpass.getpass(),
                resource="xmpp_ioloop_example")

        self.xmpp_client.connect(connect_cb=self.xmpp_connect_cb, 
                presence_cb=self.xmpp_presence_cb, 
                message_cb=self.xmpp_message_cb,
                close_cb=self.xmpp_close_cb)
    
    def xmpp_close_cb(self):
        logging.info('lost xmpp connection')
    
    def xmpp_connect_cb(self):
        # this is called once we have connected successfully
        logging.info('connected to gtalk')
        self.xmpp_client.presence(show="chat", status="A-Status-Msg", priority=5)
    
    def xmpp_presence_cb(self, msg):
        """ called with presence notifications for other individuals (ie: your roster)"""
        logging.info('presence_cb %r', msg)
        
        if msg.options.get('type') == 'subscribe':
            # auto-respond to presense notification
            # you could save this in the roster, etc
            self.xmpp_client.presence(to=msg.options["from"], type="subscribed")
    
    def xmpp_message_cb(self, msg):
        """
        Called for messages recieved (not all messages have a body). the msg is a simple XML wrapper object.
        some details are in msg.options. for others find the xml child node with `find('nodename')`
        """
        if not msg.find("body"):
            return
        logging.info(msg)
        
        from_addr = msg.options['from']
        body = msg.find("body").data
        print ""
        logging.info("%s >> %s", from_addr.split('/')[0], body)
        
        response_txt = raw_input("Response: ")
        if response_txt.strip():
            self.xmpp_client.message(to=from_addr, body=response_txt)


if __name__ == "__main__":
    tornado.options.define("google_apps_domain", type=str)
    tornado.options.define("google_apps_account", type=str)
    tornado.options.parse_command_line()

    app = App(tornado.options.options)
    tornado.ioloop.IOLoop.instance().start()
    