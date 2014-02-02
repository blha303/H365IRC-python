from twisted.words.protocols import irc
from twisted.internet import protocol, task, reactor
from twisted.application import internet, service
from datetime import datetime
import yaml, urllib2, json, sys, unicodedata, time, random, operator, tweepy, os, ago, difflib, fnmatch
import xml.etree.ElementTree as ET

with open("config.yml") as file:
    config = yaml.load(file.read())
colors = ["\x032", "\x033", "\x034", "\x035", "\x036",
          "\x037", "\x038", "\x039", "\x0310", "\x0311", "\x0312", "\x0313",
          "\x0314", "\x0315"]
online = "\x039\x02Online\x0f"
offline = "\x034\x02Offline\x0f"
ua_chrome = 'Mozilla/5.0 (X11; Linux i686) AppleWebKit/537.4 (KHTML, ' \
            'like Gecko) Chrome/22.0.1229.79 Safari/537.4'
def wopen(url):
    request = urllib2.Request(url)
    request.add_header('User-Agent', ua_chrome)
    opener = urllib2.build_opener()
    return opener.open(request).read()

# https://pypi.python.org/pypi/XML2Dict/
# Here because the PyPI installer is broken (Missing file)
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
    password = config["server_password"]
    lastDj = "Default"
    lastSong = "Default"
    news = "No news."
    schedule = None
    status = online
    quiet = False
    permaquiet = False
    lastactivity = int(time.time())
    slap = []
    antispam = {}
    loopcall = None
    topicfmt = "Welcome to http://hive365.co.uk | DJ: %s | Stream Status: %s | News: %s"
    furl = "http://hive365.co.uk/plugin/{}.php"
    try:
        with open("scheduled.txt") as f:
            scheduled = json.loads(f.read())
    except:
        scheduled = {}
        with open("scheduled.txt", "w") as f:
            f.write(json.dumps(scheduled))
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
    try:
        with open("commands.txt") as f:
            commands = json.loads(f.read())
    except:
        commands = {}
        with open("commands.txt", "w") as f:
            f.write(json.dumps(commands))
    print commands
    try:
        with open("admins.txt") as f:
            admins = json.loads(f.read())
    except:
        admins = []
        with open("admins.txt", "w") as f:
            f.write(json.dumps(admins))
    print admins
    try:
        with open("ignore.txt") as f:
            ignore = json.loads(f.read())
    except:
        ignore = []
        with open("ignore.txt", "w") as f:
            f.write(json.dumps(ignore))
    print ignore
    try:
        with open("news.txt") as f:
            news = f.read().strip()
    except:
        with open("news.txt", "w") as f:
            f.write(news)
    print news

# Startup function, run on first connect
    def signedOn(self):
        def restartloop(reason):
            print "Loop crashed: " + reason.getErrorMessage()
            self.loopcall.start(2.0).addErrback(restartloop)
        self.join(self.factory.channel)
        self.loopcall = task.LoopingCall(self.callUpdateData)
        self.loopcall.start(2.0).addErrback(restartloop)
        task.LoopingCall(self.saveData).start(10.0)
        if not self.lastDj in self.djs:
            self.djs[self.lastDj] = {'ftw': [], 'ftl': []}
        self.setTopic()
        print "Signed on as %s." % (self.nickname,)

    def joined(self, channel):
        print "Joined %s." % (channel,)

# Utils
    def checkAdmin(self, user):
        nick, _, host = user.partition('!')
        matches = []
        for i in self.admins:
            if fnmatch.fnmatch(user, i):
                return True
        if user in self.admins:
            return True
        else:
            self._notice("You can't use this command.", nick)
            return False

    def checkVoice(self, user):
        nick, _, host = user.partition('!')
        if ".hive365.co.uk" in host or self.checkAdmin(user) or nick[:5].lower() == "h365|":
            return True
        else:
            return False

    def parseCCommand(self, inp, nick):
        def actualParse(input):
            return input.replace("%user", nick).replace("%song", self.lastSong).replace("%dj", self.lastDj).replace("[b]", "\x02").replace("[/b]", "\x0f")
        if "\\n" in inp:
            inp = inp.split("\\n")
            newlist = []
            for i in inp:
                newlist.append(actualParse(i))
            return newlist
        else:
            return actualParse(inp)

    def uni2str(self, inp):
        if isinstance(inp, unicode):
            return unicodedata.normalize('NFKD', inp).encode('ascii', 'ignore')
        elif isinstance(inp, str):
            return inp
        else:
            raise Exception("Not unicode or string")

    def _send_message(self, msg, target, nick=None):
        if nick:
            msg = '%s: %s' % (nick, msg)
        self.msg(target, self.uni2str(msg))
        self.log("<%s> %s" % (self.nickname, msg), channel=target)

    def _notice(self, msg, target):
        self.notice(target, self.uni2str(msg))
        self.log("-%s- > %s: %s" % (self.nickname, target, msg), channel=target)

    def log(self, msg, channel=None):
        if not channel:
            channel = self.factory.channel
        out = "%s %s: %s" % (time.strftime("%Y-%m-%d-%H:%M:%S"), channel, msg)
        with open("log.txt", "a") as f:
            f.write(out.encode('ascii', 'ignore') + "\n")
        print out

# Vote commands
    def shoutout(self, user, request):
        user = user.encode('base64').strip().replace("\n", "")
        request = request.encode('base64').strip().replace("\n", "")
        wurl = self.furl.format("shoutout") + "?n=" + user + "&s=" + request + "&host=" + config["serverid"].encode('base64').strip()
        try:
            resp = wopen(wurl)
            return resp
        except Exception as e:
            return "An Error Occured, please report it with !bug: " + str(e)

    def choon(self, user):
        user = user.encode('base64').strip().replace("\n", "")
        wurl = self.furl.format("song_rate") + "?n=" + user + "&t=3&host=" + config["serverid"].encode('base64').strip()
        try:
            resp = wopen(wurl)
        except Exception as e:
            return "An Error Occured, please report it with !bug: " + str(e)

    def poon(self, user):
        user = user.encode('base64').strip().replace("\n", "")
        wurl = self.furl.format("song_rate") + "?n=" + user + "&t=4&host=" + config["serverid"].encode('base64').strip()
        try:
            resp = wopen(wurl)
        except Exception as e:
            return "An Error Occured, please report it with !bug: " + str(e)

    def djftw(self, user):
        user = user.encode('base64').strip().replace("\n", "")
        request = self.lastDj.encode('base64').strip().replace("\n", "")
        wurl = self.furl.format("djrate") + "?n=" + user + "&s=" + request + "&host=" + config["serverid"].encode('base64').strip()
        try:
            resp = wopen(wurl)
        except Exception as e:
            return "An Error Occured, please report it with !bug: " + str(e)

    def request(self, user, request):
        user = user.encode('base64').strip().replace("\n", "")
        request = request.encode('base64').strip().replace("\n", "")
        wurl = self.furl.format("request") + "?n=" + user + "&s=" + request + "&host=" + config["serverid"].encode('base64').strip()
        try:
            resp = wopen(wurl)
            if resp == "Shoutout Submitted, Thanks!":
                return "Request Submitted, Thanks!"
            else:
                return "Error sending request: " + resp
        except Exception as e:
            return "An Error Occured, please report it with !bug: " + str(e)

    def tweet(self, status):
        return None
        CONSUMER_KEY = ""
        CONSUMER_SECRET = ""
        ACCESS_TOKEN_KEY = ""
        ACCESS_TOKEN_SECRET = ""
        try:
            with open('lastdj.txt') as f:
                lastdj = f.read()
        except:
            with open('lastdj.txt', 'w') as f:
                f.write(status)
            lastdj = ""
        if lastdj == status or "The BeeKeeper ::" in status:
            return
        if len(status) > 140:
            raise Exception('status message is too long!')
        auth = tweepy.OAuthHandler(CONSUMER_KEY, CONSUMER_SECRET)
        auth.set_access_token(ACCESS_TOKEN_KEY, ACCESS_TOKEN_SECRET)
        api = tweepy.API(auth)
        result = api.update_status(status)
        return result

    def updateAntispam(self, nick, channel):
        return True
        if nick in self.antispam:
            if (int(time.time()) - self.antispam[nick]["ts"]) > 5:
                self.antispam.pop(nick)
                return True
            self.antispam[nick]["attempts"] += 1
            if self.antispam[nick]["attempts"] >= 3:
                self.kick(channel, nick, reason="You're doing that too much.")
            return False
        self.antispam[nick] = {'ts': int(time.time()), 'attempts': 0}
        return True

    def setTopic(self, dj=lastDj, oonline=online, news=news):
        if self.topic(config["channel"]) != self.uni2str(self.topicfmt % (dj, oonline, news)):
            self.topic(config["channel"], topic=self.uni2str(self.topicfmt % (self.lastDj, oonline, self.news)))

# Update function, runs every two seconds
    def updateData(self):
        curtime = time.strftime("%H:%M:%S")
        timeplusone = time.strftime("%H:%M:%S", time.localtime(time.time() + 1))
        if curtime in self.scheduled:
            for a in self.scheduled[curtime]:
                self._send_message(a, config["channel"])
        if timeplusone in self.scheduled:
            for a in self.scheduled[timeplusone]:
                self._send_message(a, config["channel"])
        if (int(time.time()) - self.lastactivity) > 1200 and not self.quiet:
            self._send_message("Noticed inactivity in channel, turning off notifications.", config["channel"])
            self.quiet = True
            return
        try:
            data = json.loads(wopen("http://data.hive365.co.uk/stream/info.php"))["info"]
            if data["status"] != "ON AIR":
                self.setTopic(online=offline)
                return
        except urllib2.HTTPError:
            self.setTopic(online=offline)
            return
        except KeyError:
            return
        #with open("tempdata.txt") as f:
        #    data = json.loads(f.read())["info"]
        msg = None
        data["artist_song"] = data["artist_song"].replace("&amp;", "&")
        if data["status"] == "ON AIR":
            if self.lastDj != data["title"]:
                # New DJ!
                if not data["title"] in self.djs:
                    self.djs[data["title"]] = {'ftw': [], 'ftl': []}
                ddata = self.djs[data["title"]]
                msg = "\x02New DJ Playing:\x02 %s \x02FTW's:\x02 %s \x02FTL's:\x02 %s" % (data["title"], len(ddata["ftw"]), len(ddata["ftl"]))
                self.lastDj = data["title"]
                self.setTopic()
                if not "The BeeKeeper ::" in self.lastDj:
                    try:
                        self.tweet("New DJ Playing: %s [%s]" % (data["title"], str(time.time())[5:]))
                    except tweepy.error.TweepError:
                        """ Do nothing """
            if self.lastSong != data["artist_song"]:
                # New song!
                if data["artist_song"].strip() != "":
                    if not data["artist_song"] in self.songs:
                        self.songs[data["artist_song"]] = {'choons': [], 'poons': [], 'plays': [], 'ratio': 0}
                    sdata = self.songs[data["artist_song"]]
                    if not "plays" in sdata:
                        sdata["plays"] = []
                    sdata["plays"].append(time.time())
                    if sdata["ratio"] in [1,0]:
                        sdata["ratio"] = len(sdata["choons"])
                    msg = "\x02New Song:\x02 %s || \x02Choons:\x02 %s \x02Poons:\x02 %s%s" % (data["artist_song"].replace("&amp;", "&"), len(sdata["choons"]), len(sdata["poons"]), " (Ratio: %.2f)" % sdata["ratio"] if len(sdata["choons"])+len(sdata["poons"]) != 0 else "")
                    self.lastSong = data["artist_song"]
        else:
            topica = self.topic(config["channel"])
            if not offline in topica and online in topica:
                oldtopic = self.topic(config["channel"])
                self.topic(config["channel"], topic=self.uni2str(oldtopic.replace(online, offline)))
        if msg and not self.quiet:
            self._send_message(msg, config["channel"])

    def callUpdateData(self):
        self.updateData()

# Save function, runs every ten seconds
    def saveData(self):
        with open("songs.txt", "w") as f:
            f.write(json.dumps(self.songs))
        with open("djs.txt", "w") as f:
            f.write(json.dumps(self.djs))
        with open("commands.txt", "w") as f:
            f.write(json.dumps(self.commands))
        with open("admins.txt", "w") as f:
            f.write(json.dumps(self.admins))
        with open("news.txt", "w") as f:
            f.write(self.news)
        with open("scheduled.txt", "w") as f:
            f.write(json.dumps(self.scheduled))

    def action(self, user, channel, data):
        self.privmsg(user, channel, data)

    def privmsg(self, user, channel, msg):
        nick, _, host = user.partition('!')
        self.log("<%s> " % nick + msg, channel=channel)
#        if not self.updateAntispam(nick, channel):
#            return
        if nick in self.ignore or user in self.ignore or host in self.ignore:
            return
        if self.quiet and not self.permaquiet and channel == "#hive365" and msg[0] != "-":
            self.quiet = False
            self._send_message("Noticed activity in channel, turning on notifications.", channel)
        elif self.permaquiet:
            if not msg[1:] in ["unquiet", "speak", "youcantalk"] and not self.checkAdmin(user):
                return
        if channel == "#hive365":
            self.lastactivity = time.time()
        if msg[0] == "-":
            msg = msg[1:]
        self.callUpdateData()
        # From CloudBot http://git.io/5IWsPg
        def match_command(command, commands):
            # do some fuzzy matching
            prefix = filter(lambda x: x.startswith(command), commands)
            if len(prefix) == 1:
                return prefix[0]
            elif prefix and command not in prefix:
                return prefix
            return command
        if msg[0] == config["prefix"]:
            split = msg.split(' ')
            cmd = split[0][1:].lower()
            msg = ""
            if len(split) > 1:
                msg = " ".join(split[1:])
            replacements = {'c': 'choon', 's': 'shoutout', 'p': 'poon', 'r': 'request'}
            if cmd in replacements:
                cmd = replacements[cmd]
            commands = ["listen", "stream", "dj", "song", "news", "choon", "poon", "djftw",
                        "djftl", "shoutout", "request", "schedule", "timetable", "tt",
                        "addcmd", "delcmd", "addadmin", "deladmin", "setnews", "save",
                        "utime", "glowsticks", "topicfix", "op", "deop", "voice", "devoice",
                        "kick", "ban", "ignore", "ignored", "djforthewin", "djforthelose",
                        "amianadmin", "bug", "unban", "kickban", "kban", "time",
                        "admins", "getsong", "updatecmd", "getdj",
                        "alldjs", "addsch", "delsch", "restart", "invite"]
            for i in self.commands:
                commands.append(i)
            matches = match_command(cmd, commands)
            if isinstance(matches, list):
                self.notice("Did you mean {} or {}?".format(", ".join(matches[:-1]), matches[-1]), nick)
            elif matches in commands:
                cmd = matches
            if cmd in ["listen", "stream"]:
                self._notice("\x02Webplayer:\x02 http://hive365.co.uk/web_player/", nick)
                self._notice("\x02WinAmp:\x02 http://hive365.co.uk/players/playlist.pls", nick)
                self._notice("\x02Website:\x02 http://hive365.co.uk/", nick)
            if cmd in self.commands:
                ccmd = self.parseCCommand(self.commands[cmd], nick)
                if type(ccmd) is list:
                    for i in ccmd:
                        self._send_message(i, channel)
                else:
                    self._send_message(ccmd, channel)
            elif cmd == "dj":
                ddata = self.djs[self.lastDj]
                out = "\x02Current DJ:\x02 %s \x02FTW's:\x02 %s \x02FTL's:\x02 %s" % (self.lastDj, len(ddata["ftw"]), len(ddata["ftl"]))
                self._send_message(out, channel, nick=nick)
            elif cmd == "song":
                sdata = self.songs[self.lastSong]
                out = "\x02Current Song:\x02 %s || \x02Choons:\x02 %s \x02Poons:\x02 %s%s" % (self.lastSong, len(sdata["choons"]), len(sdata["poons"]), " (Ratio: %.2f)" % sdata["ratio"] if len(sdata["choons"])+len(sdata["poons"]) != 0 else "")
                self._send_message(out, channel, nick=nick)
            elif cmd == "news":
                self._send_message(self.news, channel, nick=nick)
            elif cmd == "choon":
                sdata = self.songs[self.lastSong]
                self._send_message("%s Thinks %s is a banging choon!" % (nick, self.lastSong), channel)
                if not user in sdata["choons"]:
                    sdata["choons"].append(user)
                    sdata["ratio"] = float(len(sdata["choons"])) / len(sdata["poons"]) if len(sdata["poons"]) != 0 else 1
                    self.songs[self.lastSong] = sdata
                    self.choon(nick)
            elif cmd == "poon":
                sdata = self.songs[self.lastSong]
                self._send_message("%s Thinks %s is a bit of a 'naff poon!" % (nick, self.lastSong), channel)
                if not user in sdata["poons"]:
                    sdata["poons"].append(user)
                    sdata["ratio"] = float(len(sdata["choons"])) / len(sdata["poons"]) if len(sdata["poons"]) != 0 else 1
                    self.songs[self.lastSong] = sdata
                    self.poon(nick)
            elif cmd in ["djftw", "djforthewin"]:
                ddata = self.djs[self.lastDj]
                self._send_message("%s Thinks %s is a banging DJ!" % (nick, self.lastDj), channel)
                if not user in ddata["ftw"]:
                    ddata["ftw"].append(user)
                    self.djs[self.lastDj] = ddata
                    self.djftw(nick)
            elif cmd in ["djftl", "djforthelose"]:
                ddata = self.djs[self.lastDj]
                self._send_message("%s Thinks %s is a bad DJ!" % (nick, self.lastDj), channel)
                ddata["ftl"].append(user)
                self.djs[self.lastDj] = ddata
            elif cmd == "shoutout":
                if not msg:
                    self._send_message("Usage: !shoutout <message>", channel, nick)
                else:
                    self._notice("Shoutout submitted, thanks!", nick)
                    self.shoutout(nick, msg)
            elif cmd == "request":
                if not msg:
                     self._send_message("Usage: !request <message>", channel, nick)
                else:
                    self._notice("Request submitted, thanks!", nick)
                    resp = self.request(nick, msg)
            elif cmd in ["schedule", "timetable", "tt"]:
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
                days = {'m': 'monday', 'tu': 'tuesday', 'w': 'wednesday', 'th': 'thursday', 'f': 'friday', 'sa': 'saturday', 'su': 'sunday'}
                if msg:
                    if msg.lower() in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
                        day = msg.lower()
                    elif msg[0] in days:
                        day = days[msg[0]]
                    elif msg[0:1] in days:
                        day = days[msg[0:1]]
                    else:
                        day = time.strftime("%A", time.gmtime()).lower()
                else:
                    day = time.strftime("%A", time.gmtime()).lower()
                todayd = ", ".join(self.schedule[day])
                todayd = todayd.replace("[b]", "\x02").replace("[/b]", "\x0f")
                self._send_message(todayd, channel)
            elif cmd in ["utime", "time"]:
                if not msg:
                    self._send_message("Usage: !%s <timezone> - List: http://en.wikipedia.org/wiki/List_of_tz_database_time_zones" % cmd, channel, nick)
                else:
                    self._send_message(self.parseCCommand(self.utime(msg), nick), channel)
            elif cmd == "addcmd" and self.checkAdmin(user):
                if not msg:
                    self._send_message("Usage: !%s <data>" % cmd, channel, nick)
                else:
                    tcmd = msg.split(" ")[0]
                    content = " ".join(msg.split(" ")[1:])
                    self.commands[tcmd] = content
                    print self.commands
                    self._notice("saved.", nick)
            elif cmd == "delcmd" and self.checkAdmin(user):
                if not msg:
                    self._send_message("Usage: !%s <data>" % cmd, channel, nick)
                else:
                    try:
                        self.commands.pop(msg)
                        self._notice("done.", nick)
                    except KeyError:
                        self._notice("No such custom command.", nick)
            elif cmd == "updatecmd" and self.checkAdmin(user):
                if not msg:
                    self._send_message("Usage: !%s <data>" % cmd, channel, nick)
                else:
                    tcmd = msg.split(" ")[0]
                    content = " ".join(msg.split(" ")[1:])
                    self.commands[tcmd] = content
                    print self.commands
                    self._notice("saved.", nick)
            elif cmd == "invite" and self.checkAdmin(user):
                if not msg:
                    self._send_message("Usage: !%s <data>" % cmd, channel, nick)
                else:
                    if len(msg.split(" ")) > 1:
                        self.invite(msg.split(" ")[0], msg.split(" ")[1])
                    else:
                        self.invite(msg, channel)
            # Admin commands
            elif cmd == "addadmin" and self.checkAdmin(user):
                if not msg:
                    self._send_message("Usage: !%s <data>" % cmd, channel, nick)
                else:
                    self.admins.append(msg)
                    self._notice('done.', nick)
            elif cmd == "deladmin" and self.checkAdmin(user):
                if not msg:
                    self._send_message("Usage: !%s <data>" % cmd, channel, nick)
                else:
                    try:
                        self.admins.remove(msg)
                        self._notice("done.", nick)
                    except KeyError:
                        self._notice("No such admin entry.", nick)
            elif cmd == "admins":
                self._notice("Admins: " + " ; ".join(self.admins), nick)
            elif cmd == "setnews" and self.checkVoice(user):
                self.news = msg.strip() if msg else "None"
                self.setTopic()
            elif cmd == "save" and self.checkVoice(user):
                self.saveData()
                self._notice("done.", nick)
            elif cmd == "glowsticks":
                msga = ""
                if msg:
                    for i in msg:
                        msga += random.choice(colors) + i
                self._send_message(msga, channel, nick=nick)
            elif cmd == "topicfix" and self.checkVoice(user):
                self.setTopic()
            elif cmd == "op" and self.checkAdmin(user):
                if not msg:
                    self._send_message("Usage: !%s <data>" % cmd, channel, nick)
                else:
                    self.mode(channel, True, "o", user=msg)
            elif cmd == "deop" and self.checkAdmin(user):
                if not msg:
                    self._send_message("Usage: !%s <data>" % cmd, channel, nick)
                else:
                    self.mode(channel, False, "o", user=msg)
            elif cmd == "voice" and self.checkVoice(user):
                if not msg:
                    self._send_message("Usage: !%s <data>" % cmd, channel, nick)
                else:
                    self.mode(channel, True, "v", user=msg)
            elif cmd == "devoice" and self.checkVoice(user):
                if not msg:
                    self._send_message("Usage: !%s <data>" % cmd, channel, nick)
                else:
                    self.mode(channel, False, "v", user=msg)
            elif cmd == "kick" and self.checkVoice(user):
                if not msg:
                    self._send_message("Usage: !%s <data>" % cmd, channel, nick)
                else:
                    target = msg.split(" ")[0]
                    if "h365|" in target.lower():
                        self._send_message("I'm not going to kick a Hive365 person, come on.", channel)
                        return
                    if len(msg.split(" ")) > 1:
                        reason = " ".join(msg.split(" ")[1:])
                    else:
                        reason = "Requested"
                    self.kick(channel, target, reason="(%s) " % nick + reason)
                    self._send_message("AHAHAHAH, %s got kicked by %s, AHAHHAHA. HAH. HAHAHA..." % (target, nick), channel)
            elif cmd == "ban" and self.checkAdmin(user):
                if not msg:
                    self._send_message("Usage: !%s <data>" % cmd, channel, nick)
                else:
                    if "h365|" in msg.lower():
                        self._send_message("I'm not going to ban a Hive365 person, come on.", channel)
                        return
                    self.mode(channel, True, "b", user=msg)
            elif cmd in ["kickban", "kban"] and self.checkAdmin(user):
                if not msg:
                    self._send_message("Usage: !%s <data>" % cmd, channel, nick)
                else:
                    target = msg.split(" ")[0]
                    if "h365|" in target.lower():
                        self._send_message("I'm not going to kickban a Hive365 person, come on.", channel)
                        return
                    if len(msg.split(" ")) > 1:
                        reason = " ".join(msg.split(" ")[1:])
                    else:
                        reason = "Requested"
                    self.kick(channel, target, reason="(%s) " % nick + reason)
                    self.mode(channel, True, "b", user=msg)
                    self._send_message("AHAHAHAH, %s got kickbanned by %s, AHAHHAHA. HAH. HAHAHA..." % (target, nick), channel)
            elif cmd == "unban" and self.checkAdmin(user):
                if not msg:
                    self._send_message("Usage: !%s <data>" % cmd, channel, nick)
                else:
                    self.mode(channel, False, "b", user=msg)
            elif cmd == "ignore" and self.checkVoice(user):
                if not msg:
                    self._send_message("Usage: !%s <data>" % cmd, channel, nick)
                else:
                    self.ignore.append(msg)
                    self._notice("OK, I'm ignoring that person now.", channel, nick=nick)
            elif cmd == "unignore" and self.checkVoice(user):
                if not msg:
                    self._send_message("Usage: !%s <data>" % cmd, channel, nick)
                else:
                    try:
                        self.ignore.pop(self.ignore.index(msg))
                        self._notice("Ok, I'm not ignoring that person anymore.", channel, nick=nick)
                    except KeyError:
                        self._notice("I wasn't ignoring that person! Try !ignored to see the ignored list.", channel, nick=nick)
            elif cmd == "ignored" and self.checkVoice(user):
                self._notice("Ignored: " + "; ".join(self.ignore), nick)
            elif cmd == "restart" and self.checkAdmin(user):
                os.system("/home/radiobot/bot/restart.sh")
            elif cmd == "amianadmin":
                self._send_message(str(self.checkAdmin(user)), channel)
            elif cmd == "bug":
                if not msg:
                    self._send_message("Usage: !%s <data>" % cmd, channel, nick)
                else:
                    self._send_message("blha303, bug report from %s > %s" % (nick, msg[0].upper() + msg[1:]), channel)
            elif cmd == "help":
                def split(list):
                    list = list[:]
                    list.sort()
                    x = 0
                    for i in list:
                        if i in self.commands:
                            list[x] = i + "*"
                        x += 1
                    retlist = []
                    while len(list) > 45:
                        retlist.append(", ".join(list[:44]) + ",")
                        list = list[45:]
                    retlist.append(", ".join(list))
                    return retlist
                for out in split(commands):
                    self._notice("Commands: " + out, nick)
#            elif cmd == "dance" and self.checkAdmin(user):
#                moves = ["<\x02(\x02^.^<\x02)\x02",
#                         "<\x02(\x02^.^\x02)\x02>",
#                         "\x02(\x02>^.^\x02)\x02>",
#                         "\x02(\x027^.^\x02)\x027",
#                         "\x02(\x02>^.^<\x02)\x02",
#                         "v\x02(\x02^.^\x02)\x02^",
#                         "^\x02(\x02^.^\x02)\x02v",
#                         "/\x02(\x02^.^\x02)\x02/",
#                         "\\\x02(\x02^.^\x02)\x02\\",
#                         "\\\x02(\x02^.^\x02)\x02/",
#                         "|\x02(\x02^.^\x02)\x02|",
#                         "\\\x02(\x02^.^\x02)\x02|",
#                         "|\x02(\x02^.^\x02)\x02/"]
#                for i in xrange(3):
#                    self._send_message(random.choice(moves), channel)
#                    time.sleep(1)
            elif cmd == "getsong":
                if not msg:
                    self._send_message("Usage: !%s <data>" % cmd, channel, nick)
                else:
                    if msg in self.songs:
                        sdata = self.songs[msg]
                        song = msg
                    else:
                        closenames = difflib.get_close_matches(msg, self.songs, 1)
                        if len(closenames) == 1:
                            sdata = self.songs[closenames[0]]
                            song = closenames[0]
                        else:
                            sdata = {}
                    if sdata:
                        outmsg = "\x02Song:\x02 %s || \x02Choons:\x02 %s \x02Poons:\x02 %s%s" % (song, len(sdata["choons"]), len(sdata["poons"]), " (Ratio: %.2f)" % sdata["ratio"] if len(sdata["choons"])+len(sdata["poons"]) != 0 else "") + " Last played: " + ago.human(datetime.fromtimestamp(int(sdata["plays"][-1])))
                        self._send_message(outmsg, channel)
                    else:
                        self._send_message("Can't find that song in the database :(", channel, nick=nick)
            elif cmd == "getdj":
                if not msg:
                    self._send_message("Usage: !%s <data>" % cmd, channel, nick)
                else:
                    if msg in self.djs:
                        ddata = self.djs[msg]
                        outmsg = "\x02DJ:\x02 %s \x02FTW's:\x02 %s \x02FTL's:\x02 %s" % (msg, len(ddata["ftw"]), len(ddata["ftl"]))
                        self._send_message(outmsg, channel)
                    else:
                        self._send_message("Can't find that DJ in the database :(", channel, nick=nick)
            elif cmd == "alldjs":
                self._notice(",".join(self.djs), nick)
            elif cmd == "addsch" and self.checkAdmin(user):
                if not msg:
                    self._send_message("Usage: !%s <data>" % cmd, channel, nick)
                else:
                    try:
                        timemsg = msg.split(" ")[0]
                        ts = time.strptime(timemsg, "%H:%M:%S")
                        if not timemsg in self.scheduled:
                            self.scheduled[timemsg] = []
                        self.scheduled[timemsg].append(" ".join(msg.split(" ")[1:]))
                        self._send_message("Added.", channel)
                    except ValueError:
                        self._send_message("Invalid time provided. Must be of format HH:MM:SS.", channel)
            elif cmd == "delsch" and self.checkAdmin(user):
                if not msg:
                    self._send_message("Usage: !%s <data>" % cmd, channel, nick)
                else:
                    try:
                        timemsg = msg.split(" ")[0]
                        ts = time.strptime(timemsg, "%H:%M:%S")
                        self.scheduled.pop(timemsg)
                        self._send_message("Deleted.", channel)
                    except ValueError:
                        self._send_message("Invalid time provided. Must be of format HH:MM:SS.", channel)
                    except KeyError:
                        self._send_message("Entry matching %s cannot be found." % timemsg, channel)
            elif cmd == "listsch":
                self._notice("Current time: " + time.strftime("%H:%M:%S"), nick)
                for k,v in self.scheduled.items():
                    self._notice("%s: %s" % (k,v), nick)

    def utime(self, input):
        with open("timezones.txt") as f:
            timezones = json.loads(f.read())
 
        if input == "":
            input = time.time()
 
        error = False
        try:
            ts = int(input.split(" ")[0])
            tz = "UTC"
            if len(input.split(" ")) > 1:
                tz = input.split(" ")[1]
                if input.split(" ")[1] in timezones:
                    modifier = timezones[input.split(" ")[1]] * 3600
                else:
                    modifier = int(input.split(" ")[1]) * 3600
                ts = int(input.split(" ")[0]) + modifier
        except ValueError:
            ts = time.time()
            tz = input.split(" ")[0]
            if input.split(" ")[0] in timezones:
                modifier = timezones[input.split(" ")[0]] * 3600
            else:
                try:
                    modifier = int(input.split(" ")[0]) * 3600
                except:
                    closenames = difflib.get_close_matches(input.split(" ")[0], timezones, 1)
                    if len(closenames) == 1:
                        tz = closenames[0]
                        modifier = timezones[tz] * 3600
                    else:
                        error = True
                        modifier = 0
            ts = ts + modifier
        except AttributeError:
            ts = input
            tz = "UTC"
 
        if error:
            return "Invalid timezone (%s) List: http://is.gd/fKuZKC" % input
        else:
            try:
                return time.strftime("[b]%H:%M:%S %d %b %Y[/b]", time.gmtime(ts + 345)) + " in " + tz
            except Exception:
                return "Usage: !utime [timestamp] [timezone]"

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
