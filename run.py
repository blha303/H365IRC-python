from twisted.words.protocols import irc
from twisted.internet import protocol, task, reactor
import yaml, urllib2, json, sys, unicodedata, datetime
import xml.etree.ElementTree as ET

with open("config.yml") as file:
    config = yaml.load(file.read())
online = "\x033Online\x0f"
offline = "\x034Offline\x0f"
ua_chrome = 'Mozilla/5.0 (X11; Linux i686) AppleWebKit/537.4 (KHTML, ' \
            'like Gecko) Chrome/22.0.1229.79 Safari/537.4'
def wopen(url):
    request = urllib2.Request(url)
    request.add_header('User-Agent', ua_chrome)
    opener = urllib2.build_opener()
    return opener.open(request).read()

# https://pypi.python.org/pypi/XML2Dict/
class XML2Dict(object):
    def __init__(self, coding='UTF-8'):
        self._coding = coding
    def _parse_node(self, node):
        tree = {}
        #Save childrens
        for child in node.getchildren():
            ctag = child.tag
            cattr = child.attrib
            ctext = child.text.strip().encode(self._coding) if child.text is not None else ''
            ctree = self._parse_node(child)
            if not ctree:
                cdict = self._make_dict(ctag, ctext, cattr)
            else:
                cdict = self._make_dict(ctag, ctree, cattr)
            if ctag not in tree: # First time found
                tree.update(cdict)
                continue
            atag = '@' + ctag
            atree = tree[ctag]
            if not isinstance(atree, list):
                if not isinstance(atree, dict):
                    atree = {}
                if atag in tree:
                    atree['#'+ctag] = tree[atag]
                    del tree[atag]
                tree[ctag] = [atree] # Multi entries, change to list
            if cattr:
                ctree['#'+ctag] = cattr
            tree[ctag].append(ctree)
        return  tree
    def _make_dict(self, tag, value, attr=None):
        '''Generate a new dict with tag and value
        If attr is not None then convert tag name to @tag
        and convert tuple list to dict'''
        ret = {tag: value}
        # Save attributes as @tag value
        if attr:
            atag = '@' + tag
            aattr = {}
            for k, v in attr.items():
                aattr[k] = v
            ret[atag] = aattr
            del atag
            del aattr
        return ret
    def parse(self, xml):
        '''Parse xml string to python dict'''
        EL = ET.fromstring(xml)
        return self._make_dict(EL.tag, self._parse_node(EL), EL.attrib)
# End https://pypi.python.org/pypi/XML2Dict/

class Bot(irc.IRCClient):
    nickname = config["nickname"]
    username = config["username"]
    admins = config["admins"]
    lastDj = "Default"
    lastSong = "Default"
    news = "No news."
    schedule = None
    status = online
    topicfmt = "Welcome to http://hive365.co.uk | DJ: %s | Stream Status: %s | News: %s"
    furl = "http://hive365.co.uk/plugin/{}.php"
    try:
        with open("songs.txt") as f:
            songs = json.loads(f.read())
    except:
        songs = {}
        with open("songs.txt", "w") as f:
            f.write(json.dumps(songs))
    try:
        with open("djs.txt") as f:
            djs = json.loads(f.read())
    except:
        djs = {}
        with open("djs.txt", "w") as f:
            f.write(json.dumps(djs))

    def shoutout(self, user, request):
        user = user.encode('base64').strip()
        request = request.encode('base64').strip()
        wurl = self.furl.format("shoutout") + "?n=" + user + "&s=" + request + "&host=" + config["serverid"].encode('base64').strip()
        print wurl
        try:
            resp = wopen(wurl)
            return resp
        except Exception as e:
            return "An Error Occured: " + str(e)

    def choon(self, user):
        user = user.encode('base64').strip()
        wurl = self.furl.format("song_rate") + "?n=" + user + "&t=3&host=" + config["serverid"].encode('base64').strip()
        print wurl
        try:
            resp = wopen(wurl)
            if resp == "Song Rating Submitted, Thanks!":
                print "success"
            else:
                print None
        except Exception as e:
            print str(e)

    def poon(self, user):
        user = user.encode('base64').strip()
        wurl = self.furl.format("song_rate") + "?n=" + user + "&t=4&host=" + config["serverid"].encode('base64').strip()
        print wurl
        try:
            resp = wopen(wurl)
            print resp
        except Exception as e:
            print str(e)

    def djftw(self, user):
        user = user.encode('base64').strip()
        request = self.lastDj.encode('base64').strip()
        wurl = self.furl.format("djrate") + "?n=" + user + "&s=" + request + "&host=" + config["serverid"].encode('base64').strip()
        print wurl
        try:
            resp = wopen(wurl)
            print resp
        except Exception as e:
            print str(e)

    def request(self, user, request):
        user = user.encode('base64').strip()
        request = request.encode('base64').strip()
        wurl = self.furl.format("request") + "?n=" + user + "&s=" + request + "&host=" + config["serverid"].encode('base64').strip()
        print wurl
        try:
            resp = wopen(wurl)
            return resp
        except Exception as e:
            return "An Error Occured: " + str(e)

    def uni2str(self, inp):
        if isinstance(inp, unicode):
            return unicodedata.normalize('NFKD', inp).encode('ascii', 'ignore')
        elif isinstance(inp, str):
            return inp
        else:
            raise Exception("Not unicode or string")

    def updateData(self):
        data = json.loads(wopen("http://data.hive365.co.uk/stream/info.php"))["info"]
        #with open("tempdata.txt") as f:
        #    data = json.loads(f.read())["info"]
        msg = None
#        statusmsg = ""
#        for i in data:
#            statusmsg += data[i] + ", "
#        statusmsg += self.lastDj + ", " + self.lastSong
#        print statusmsg
        if data["status"] == "ON AIR":
            if self.lastDj != data["title"]:
                # New DJ!
                if not data["title"] in self.djs:
                    self.djs[data["title"]] = {'ftw': [], 'ftl': []}
                ddata = self.djs[data["title"]]
                msg = "\x02New DJ Playing:\x02 %s \x02FTW's:\x02 %s \x02FTL's:\x02 %s" % (data["title"], len(ddata["ftw"]), len(ddata["ftl"]))
                self.lastDj = data["title"]
                self.topic(config["channel"], topic=self.uni2str(self.topicfmt % (self.lastDj, online, self.news)))
            if self.lastSong != data["artist_song"]:
                # New song!
                if not data["artist_song"] in self.songs:
                    self.songs[data["artist_song"]] = {'choons': [], 'poons': []}
                sdata = self.songs[data["artist_song"]]
                msg = "\x02New Song:\x02 %s || \x02Choons:\x02 %s \x02Poons:\x02 %s" % (data["artist_song"], len(sdata["choons"]), len(sdata["poons"]))
                self.lastSong = data["artist_song"]
#            if not self.lastDj in str(self.topic(config["channel"])):
#                self.topic(config["channel"], topic=self.uni2str(self.topicfmt % (self.lastDj, online, self.news)))
        else:
            topica = self.topic(config["channel"])
            if not offline in topica and online in topica:
                oldtopic = self.topic(config["channel"])
                self.topic(config["channel"], topic=self.uni2str(oldtopic.replace(online, offline)))
        if msg:
            self._send_message(msg, config["channel"])
    
    def saveData(self):
        with open("songs.txt", "w") as f:
            f.write(json.dumps(self.songs))
        with open("djs.txt", "w") as f:
            f.write(json.dumps(self.djs))

    def signedOn(self):
        self.msg("root", "test test")
        self.msg("root", "connect quakenet")
        self.join(self.factory.channel)
        task.LoopingCall(self.updateData).start(2.0)
        task.LoopingCall(self.saveData).start(10.0)
        if not self.lastDj in self.djs:
            self.djs[self.lastDj] = {'ftw': [], 'ftl': []}
        self.topic(config["channel"], topic=self.uni2str(self.topicfmt % (self.lastDj, online, self.news)))
        print "Signed on as %s." % (self.nickname,)

    def joined(self, channel):
        print "Joined %s." % (channel,)

    def _send_message(self, msg, target, nick=None):
        if nick:
            msg = '%s, %s' % (nick, msg)
        self.msg(target, self.uni2str(msg))

    def privmsg(self, user, channel, msg):
        nick, _, host = user.partition('!')
        print msg
        if msg[0] == config["prefix"]:
            split = msg.split(' ')
            cmd = msg.split(' ')[0][1:]
            if len(split) > 1:
                msg = " ".join(msg.split(' ')[1:])
            if cmd == "dj":
                ddata = self.djs[self.lastDj]
                out = "\x02Current DJ:\x02 %s \x02FTW's:\x02 %s \x02FTL's:\x02 %s" % (self.lastDj, len(ddata["ftw"]), len(ddata["ftl"]))
                self._send_message(out, channel, nick=nick)
            elif cmd == "song":
                sdata = self.songs[self.lastSong]
                out = "\x02Current Song:\x02 %s || \x02Choons:\x02 %s \x02Poons:\x02 %s" % (self.lastSong, len(sdata["choons"]), len(sdata["poons"]))
            elif cmd == "news":
                self._send_message(self.news, channel, nick=nick)
            elif cmd == "setnews" and user in self.admins:
                self.news = msg.strip()
                self.topic(config["channel"], topic=self.uni2str(self.topicfmt % (self.lastDj, self.status, self.news)))
            elif cmd == "save" and user in self.admins:
                self.saveData()
                self._send_message("done.", channel, nick=nick)
            elif cmd in ["c", "ch", "choon"]:
                sdata = self.songs[self.lastSong]
                if not user in sdata["choons"]:
                    sdata["choons"].append(user)
                    self.songs[self.lastSong] = sdata
                    self.choon(nick)
                self._send_message("%s Thinks %s is a banging choon!" % (nick, self.lastSong), channel)
            elif cmd in ["p", "poon"]:
                sdata = self.songs[self.lastSong]
                if not user in sdata["poons"]:
                    sdata["poons"].append(user)
                    self.songs[self.lastSong] = sdata
                    self.poon(nick)
                self._send_message("%s Thinks %s is a bit of a 'naff poon!" % (nick, self.lastSong), channel)
            elif cmd == "djftw":
                ddata = self.djs[self.lastDj]
                if not user in ddata["ftw"]:
                    ddata["ftw"].append(user)
                    self.djs[self.lastDj] = ddata
                    self.djftw(nick)
                self._send_message("%s Thinks %s is a banging DJ!" % (nick, self.lastDj), channel)
            elif cmd == "djftl":
                ddata = self.djs[self.lastDj]
                if not user in ddata["ftl"]:
                    ddata["ftl"].append(user)
                    self.djs[self.lastDj] = ddata
            elif cmd == "shoutout":
                resp = self.shoutout(nick, msg)
                if resp:
                    self._send_message(resp, nick)
            elif cmd in ["schedule", "timetable", "sch", "sched", "tt"]:
                if not self.schedule:
                    xml = XML2Dict()
                    data = xml.parse(wopen("http://hive365.co.uk/schedule/schedule.xml"))
                    newdict = {}
                    for i in data["schedule"]["scheditem"]:
                        newdict[i["title"].lower()] = i["schedpost"].split("\n")
                    for i in newdict:
                        newlist = []
                        for a in newdict[i]:
                            newlist.append(a.strip())
                        newdict[i] = newlist
                    self.schedule = newdict
                if msg.lower() in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
                    day = msg.lower()
                else:
                    day = datetime.datetime.today().strftime("%A").lower()
                todayd = ", ".join(self.schedule[day])
                todayd = todayd.replace("[b]", "\x02").replace("[/b]", "\x0f")
                self._send_message(todayd, channel)
                

class BotFactory(protocol.ClientFactory):
    protocol = Bot

    def __init__(self, channel):
        self.channel = channel

    def clientConnectionLost(self, connector, reason):
        print "Lost connection (%s), reconnecting." % (reason,)
        connector.connect()

    def clientConnectionFailed(self, connector, reason):
        print "Could not connect: %s" % (reason,)


if __name__ == "__main__":
    channel = config["channel"]
    reactor.connectTCP(config["server"], config["port"], BotFactory(channel))
    reactor.run()
elif __name__ == '__builtin__':
    application = service.Application('H365IRCBot')
    channel = config["channel"]
    ircService = internet.TCPClient(config["server"], config["port"], BotFactory(channel))
    ircService.setServiceParent(application)