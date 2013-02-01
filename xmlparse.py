# GPL XML Parser by Campbell Barton
# http://blenderartists.org/forum/showthread.php?89710-XML-parsing
# with some adaptations and fixes

class XmlBLock(object):
    __slots__ = 'name', 'children', 'options', 'data'
    def __init__(self, name, data=None, children=None, options=None):
        self.name = name
        self.data = data
        self.children = children or []
        self.options = options or {}
    
    def __eq__(self, other):
        # primarily used for testing to validate parsing
        if not isinstance(other, self.__class__):
            return False
        if self.name != other.name:
            return False
        if self.options != other.options:
            return False
        if len(self.children) != len(other.children):
            return False
        for i, child in enumerate(self.children):
            if not child == other.children[i]:
                return False
        return True
    
    def find(self, name=None, options=None):
        """Return the first element that matches name && options. If option[key] == None,
        the presense of that option will be required, but it's value will not be checked.
        
        >> msg = xml2msg('<tag><inner><body>....</body></inner></tag>')
        >> msg.find("body").data == '...'
        """
        
        found = True
        if name and self.name != name:
            found = False
        if options:
            for key, value in options:
                if value is None:
                    if key not in self.options:
                        found = False
                elif self.options.get(key) != value:
                    found = False
        if found:
            return self
        for child in self.children:
            obj = child.find(name, options)
            if obj:
                return obj
    
    def __repr__(self):
        return '<XmlBLock name:%s data:%r options:%s children:%s>' % (self.name, self.data, self.options, self.children)
    def dump(self):
        children = ', '.join([x.dump() for x in self.children])
        return 'XmlBLock(name=%r, data=%r,\n\toptions=%r,\n\tchildren=[%s]\n)' % (self.name, self.data, self.options, children)

def xml2msg(xml_text):
    msgs = xml2list(xml_text)
    assert len(msgs) == 1
    return msgs[0]

def xml2list(xml_text):
    tag_bounds = []
    xml_list = []
    # Mark all start and ends for the <> and </>
    START, END, SINGLE = 0,1,2 # is it a start tag, end tag or a single tag.
    i=0
    while i < len(xml_text):
        # tag all < and > 
        if xml_text[i] == '<':
            i = ii = i+1 # increase i so we can use slicing
            while xml_text[ii] != '>': ii += 1
            
            if xml_text[i] == '!': pass # comment, assume <!--
            elif xml_text[i] == '?': pass # assume <?xml
            elif xml_text[i] == '/': # Ending
                tag_bounds.append((i,ii, END))
            else: # Starting
                if xml_text[ii-1] == '/':
                    tag_bounds.append((i,ii-1, SINGLE)) # dont include the /
                else:
                    tag_bounds.append((i,ii, START))
            i= ii
        i+=1
        
    def build_xml(tag_idx, children):
        '''
        gets all the data between here and the next index
        '''
        tag = tag_bounds[tag_idx] # must be the starter - tag[2] == True
        
        if tag[2] == END:
            print xml_text[tag[0]:tag[1]]
            print xml_list
            raise "Error"
        
        
        name_and_opts = xml_text[tag[0] : tag[1]].split()
        xml_blk = XmlBLock(name=name_and_opts[0])
        children.append(xml_blk)
        
        if len(name_and_opts) > 1: # Some options were set
            i =1
            while i < len(name_and_opts):
                # print name_and_opts
                key, val = name_and_opts[i].split('=', 1)
                if val[0]=='"' and val[-1] == '"': 
                    val = val[1:-1] # strip ""
                elif val[0] == '"':
                    val = val[1:]
                    i += 1
                    while i < len(name_and_opts):
                        val += ' ' + name_and_opts[i]
                        i += 1
                        if val[-1] == '"':
                            break
                
                xml_blk.options[key] = val
                i+=1
        
        if tag[2] == SINGLE: # this tag has no matching end tag, return the next index.
            return tag_idx+1
        
        tag_next = tag_bounds[tag_idx+1]
        xml_blk.data = xml_text[tag[1]+1:tag_next[0]-1].strip() # Text between now and the next tag is data
        
        tag_idx += 1
        while 1:
            tag_next = tag_bounds[tag_idx]
            # This ends the current tag
            if tag_next[2] == END:
                name = xml_text[tag_next[0]+1:tag_next[1]]
                if name == xml_blk.name :
                    return tag_idx + 1
                # Should only be ending the current tag
            else:
                tag_idx= build_xml(tag_idx, xml_blk.children)
                if tag_idx >= len(tag_bounds):
                    return tag_idx # will finish
    
    build_xml(0, xml_list)
    return xml_list

def pytest_generate_tests(metafunc):
    if metafunc.function in [test_xml_parsing]:
        raw_xml = '''
<presence from="jehiah@gmail.com/Adium439D0DB4" to="user@test/jidD515BC32"><show>away</show><c node="http://pidgin.im/" hash="sha-1" ver="VUFD6HcFmUiKlZnS3M=" xmlns="http://jabber.org/protocol/caps"/><x xmlns="vcard-temp:x:update"><photo>f5b8aa332a9c91e65f42</photo></x></presence>
        '''
        result_xml=XmlBLock(name='presence', data='',
            options={'to': 'user@test/jidD515BC32', 'from': 'jehiah@gmail.com/Adium439D0DB4'},
            children=[XmlBLock(name='show', data='away',
                    options={},
                    children=[]
                ), XmlBLock(name='c', data=None,
                    options={'node': 'http://pidgin.im/', 'ver': 'VUFD6HcFmUiKlZnS3M=', 'xmlns': 'http://jabber.org/protocol/caps', 'hash': 'sha-1'},
                    children=[]
                ), XmlBLock(name='x', data='',
                    options={'xmlns': 'vcard-temp:x:update'},
                    children=[XmlBLock(name='photo', data='f5b8aa332a9c91e65f42',
                    options={},
                    children=[]
                )]
            )]
        )
        metafunc.addcall(funcargs=dict(raw_xml=raw_xml, result_xml=result_xml))
        
        raw_xml = '<presence from="test@test/brisketC9E760B8" to="asdf@gmail.com/jid04DDE7A3"><show>xa</show>\n<priority>0</priority>\n<c node="http://www.apple.com/ichat/caps" ver="800" ext="ice recauth rdserver maudio audio rdclient mvideo auxvideo rdmuxing avcap avavail video" xmlns="http://jabber.org/protocol/caps"/><x xmlns="http://jabber.org/protocol/tune"/>\n<x xmlns="vcard-temp:x:update"><photo>e51c941d752aa382d998e97ba34841102cd52bc4</photo></x></presence>'
        result_xml = XmlBLock(name='presence', data='',
            options={'to': 'asdf@gmail.com/jid04DDE7A3', 'from': 'test@test/brisketC9E760B8'},
            children=[XmlBLock(name='show', data='xa',
            options={},
            children=[]
        ), XmlBLock(name='priority', data='0',
            options={},
            children=[]
        ), XmlBLock(name='c', data=None,
            options={'node': 'http://www.apple.com/ichat/caps', 'ext': 'ice recauth rdserver maudio audio rdclient mvideo auxvideo rdmuxing avcap avavail video"', 'ver': '800'},
            children=[]
        ), XmlBLock(name='x', data=None,
            options={'xmlns': 'http://jabber.org/protocol/tune'},
            children=[]
        ), XmlBLock(name='x', data='',
            options={'xmlns': 'vcard-temp:x:update'},
            children=[XmlBLock(name='photo', data='e51c941d752aa382d998e97ba34841102cd52bc4',
            options={},
            children=[]
        )]
        )]
        )
        metafunc.addcall(funcargs=dict(raw_xml=raw_xml, result_xml=result_xml))
        


def test_xml_parsing(raw_xml, result_xml):
    o = xml2msg(raw_xml)
    print o.dump()
    assert o == result_xml
