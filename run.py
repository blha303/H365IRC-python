from twisted.words.protocols import irc
from twisted.internet import protocol, task, reactor
from twisted.application import internet, service
import yaml, urllib2, json, sys, unicodedata, time, random
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
    lastDj = "Default"
    lastSong = "Default"
    news = "No news."
    schedule = None
    status = online
    quiet = False
    permaquiet = False
    lastactivity = int(time.time())
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
    try:
        with open("commands.txt") as f:
            commands = json.loads(f.read())
    except:
        commands = {}
        with open("commands.txt", "w") as f:
            f.write(json.dumps(commands))
    try:
        with open("admins.txt") as f:
            admins = json.loads(f.read())
    except:
        admins = []
        with open("admins.txt", "w") as f:
            f.write(json.dumps(admins))
    try:
        with open("ignore.txt") as f:
            ignore = json.loads(f.read())
    except:
        ignore = []
        with open("ignore.txt", "w") as f:
            f.write(json.dumps(ignore))
    try:
        with open("news.txt") as f:
            news = f.read().strip()
    except:
        with open("news.txt", "w") as f:
            f.write(news)

# Startup function, run on first connect
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

# Utils
    def checkAdmin(self, user):
        nick, _, host = user.partition('!')
        whois = self.whois(nick)
        if host.split("@")[1] == "bnc.hive365.co.uk":
            return True
        elif user in self.admins:
            return True
        else:
            print str(whois)
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
        self.log("<%s> %s" % (self.nickname, msg))

    def _notice(self, msg, target):
        self.notice(target, self.uni2str(msg))
        print "-%s- > %s: %s" % (self.nickname, target, msg.encode('ascii', 'ignore'))

    def log(self, msg, channel=None):
        if not channel:
            channel = self.factory.channel
        out = "%s %s: %s" % (time.strftime("%Y-%m-%d-%H:%M:%S"), channel, msg)
        with open("log.txt", "a") as f:
            f.write(out + "\n")
        print out

# Vote commands
    def shoutout(self, user, request):
        user = user.encode('base64').strip()
        request = request.encode('base64').strip()
        wurl = self.furl.format("shoutout") + "?n=" + user + "&s=" + request + "&host=" + config["serverid"].encode('base64').strip()
        try:
            resp = wopen(wurl)
            return resp
        except Exception as e:
            return "An Error Occured: " + str(e)

    def choon(self, user):
        user = user.encode('base64').strip()
        wurl = self.furl.format("song_rate") + "?n=" + user + "&t=3&host=" + config["serverid"].encode('base64').strip()
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
        try:
            resp = wopen(wurl)
            print resp
        except Exception as e:
            print str(e)

    def djftw(self, user):
        user = user.encode('base64').strip()
        request = self.lastDj.encode('base64').strip()
        wurl = self.furl.format("djrate") + "?n=" + user + "&s=" + request + "&host=" + config["serverid"].encode('base64').strip()
        try:
            resp = wopen(wurl)
            print resp
        except Exception as e:
            print str(e)

    def request(self, user, request):
        user = user.encode('base64').strip()
        request = request.encode('base64').strip()
        wurl = self.furl.format("request") + "?n=" + user + "&s=" + request + "&host=" + config["serverid"].encode('base64').strip()
        try:
            resp = wopen(wurl)
            return resp
        except Exception as e:
            return "An Error Occured: " + str(e)

# Update function, runs every two seconds
    def updateData(self):
        if (int(time.time()) - self.lastactivity) > 1200 and self.quiet == False:
            self._send_message("Noticed inactivity in channel, turning off notifications.", config["channel"])
            self.quiet = True
            return
        elif self.quiet == True:
            return
        self.updateData()
        try:
            data = json.loads(wopen("http://data.hive365.co.uk/stream/info.php"))["info"]
        except:
            print "Update failed."
            return
        #with open("tempdata.txt") as f:
        #    data = json.loads(f.read())["info"]
        msg = None
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
                    self.songs[data["artist_song"]] = {'choons': [], 'poons': [], 'plays': []}
                sdata = self.songs[data["artist_song"]]
                if not "plays" in sdata:
                    sdata["plays"] = []
                sdata["plays"].append(time.time())
                msg = "\x02New Song:\x02 %s || \x02Choons:\x02 %s \x02Poons:\x02 %s" % (data["artist_song"], len(sdata["choons"]), len(sdata["poons"]))
                self.lastSong = data["artist_song"]
#            if not self.lastDj in str(self.topic(config["channel"])):
#                self.topic(config["channel"], topic=self.uni2str(self.topicfmt % (self.lastDj, online, self.news)))
        else:
            topica = self.topic(config["channel"])
            if not offline in topica and online in topica:
                oldtopic = self.topic(config["channel"])
                self.topic(config["channel"], topic=self.uni2str(oldtopic.replace(online, offline)))
        if msg and not self.quiet:
            self._send_message(msg, config["channel"])

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

    def privmsg(self, user, channel, msg):
        nick, _, host = user.partition('!')
        self.log("<%s> " % nick + msg)
        if nick in self.ignore or user in self.ignore or host in self.ignore:
            return
        if self.quiet and not self.permaquiet:
            self.quiet = False
            self.lastactivity = time.time()
        elif self.permaquiet:
            if not msg[1:] in ["unquiet", "speak", "youcantalk"] and not self.checkAdmin(user):
                return
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
            cmd = split[0][1:]
            msg = ""
            if len(split) > 1:
                msg = " ".join(split[1:])
            if cmd == "s":
                cmd = "shoutout"
            commands = ["listen", "stream", "dj", "song", "news", "choon", "poon", "djftw",
                        "djftl", "shoutout", "request", "schedule", "timetable", "tt",
                        "addcmd", "delcmd", "addadmin", "deladmin", "setnews", "save",
                        "utime", "glowsticks", "topicfix", "op", "deop", "voice", "devoice",
                        "kick", "ban", "quiet", "shutup", "shhhhhh", "unquiet", "speak",
                        "youcantalk", "ignore", "ignored"]
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
                out = "\x02Current Song:\x02 %s || \x02Choons:\x02 %s \x02Poons:\x02 %s" % (self.lastSong, len(sdata["choons"]), len(sdata["poons"]))
                self._send_message(out, channel, nick=nick)
            elif cmd == "news":
                self._send_message(self.news, channel, nick=nick)
            elif cmd == "choon":
                sdata = self.songs[self.lastSong]
                if not user in sdata["choons"]:
                    sdata["choons"].append(user)
                    self.songs[self.lastSong] = sdata
                    self.choon(nick)
                    self._send_message("%s Thinks %s is a banging choon!" % (nick, self.lastSong), channel)
                else:
                    self._notice("You've already voted on this song!", nick)
            elif cmd == "poon":
                sdata = self.songs[self.lastSong]
                if not user in sdata["poons"]:
                    sdata["poons"].append(user)
                    self.songs[self.lastSong] = sdata
                    self.poon(nick)
                    self._send_message("%s Thinks %s is a bit of a 'naff poon!" % (nick, self.lastSong), channel)
                else:
                    self._notice("You've already voted on this song!", nick)
            elif cmd == "djftw":
                ddata = self.djs[self.lastDj]
                if not user in ddata["ftw"]:
                    ddata["ftw"].append(user)
                    self.djs[self.lastDj] = ddata
                    self.djftw(nick)
                    self._send_message("%s Thinks %s is a banging DJ!" % (nick, self.lastDj), channel)
                else:
                    self._notice("You've already voted on this DJ!", nick)
            elif cmd == "djftl":
                ddata = self.djs[self.lastDj]
                if not user in ddata["ftl"]:
                    ddata["ftl"].append(user)
                    self.djs[self.lastDj] = ddata
                    self._send_message("%s Thinks %s is a bad DJ!" % (nick, self.lastDj), channel)
                else:
                    self._notice("You've already voted on this DJ!", nick)
            elif cmd == "shoutout":
                resp = self.shoutout(nick, msg)
                if resp:
                    self._send_message(resp, nick)
            elif cmd == "request":
                resp = self.request(nick, msg)
                if resp:
                    self.notice(resp, nick)
            elif cmd in ["schedule", "timetable", "tt"]:
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
                    day = time.strftime("%A", time.gmtime()).lower()
                todayd = ", ".join(self.schedule[day])
                todayd = todayd.replace("[b]", "\x02").replace("[/b]", "\x0f")
                self._send_message(todayd, channel)
            elif cmd == "utime":
                self._send_message(self.parseCCommand(self.utime(msg), nick), channel)
            elif cmd == "addcmd" and self.checkAdmin(user):
                tcmd = msg.split(" ")[0]
                content = " ".join(msg.split(" ")[1:])
                self.commands[tcmd] = content
                self._notice("saved.", nick)
            elif cmd == "delcmd" and self.checkAdmin(user):
                try:
                    self.commands.pop(msg)
                    self._notice("done.", nick)
                except KeyError:
                    self._notice("No such custom command.", nick)
            # Admin commands
            elif cmd == "addadmin" and self.checkAdmin(user):
                admins.append(msg)
                self._notice('done.', nick)
            elif cmd == "deladmin" and self.checkAdmin(user):
                try:
                    admins.pop(msg)
                    self._notice("done.", nick)
                except KeyError:
                    self._notice("No such admin entry.", nick)
            elif cmd == "setnews" and self.checkAdmin(user):
                self.news = msg.strip()
                self.topic(config["channel"], topic=self.uni2str(self.topicfmt % (self.lastDj, self.status, self.news)))
            elif cmd == "save" and self.checkAdmin(user):
                self.saveData()
                self._notice("done.", nick)
            elif cmd == "fuckyou":
                self._send_message(self.parseCCommand("No, fuck YOU, %user", nick), channel)
            elif cmd == "glowsticks":
                msga = ""
                if msg:
                    for i in msg:
                        msga += random.choice(colors) + i
                self._send_message(msga, channel, nick=nick)
            elif cmd == "topicfix" and self.checkAdmin(user):
                self.topic(config["channel"], topic=self.uni2str(self.topicfmt % (self.lastDj, self.status, self.news)))
            elif cmd == "op" and self.checkAdmin(user):
                self.mode(self.factory.channel, True, "o", user=msg)
            elif cmd == "deop" and self.checkAdmin(user):
                self.mode(self.factory.channel, False, "o", user=msg)
            elif cmd == "voice" and self.checkAdmin(user):
                self.mode(self.factory.channel, True, "v", user=msg)
            elif cmd == "devoice" and self.checkAdmin(user):
                self.mode(self.factory.channel, False, "v", user=msg)
            elif cmd == "kick" and self.checkAdmin(user):
                self.kick(self.factory.channel, msg, reason="Requested by " + nick)
            elif cmd == "ban" and self.checkAdmin(user):
                self.kick(self.factory.channel, msg, reason="Requested by " + nick)
                self.mode(self.factory.channel, True, "b", user=msg)
            elif cmd == "unban" and self.checkAdmin(user):
                self.mode(self.factory.channel, False, "b", user=msg)
            elif cmd in ["quiet", "shutup", "shhhhhh"]:
                self.quiet = True
                self.permaquiet = True
                self._send_message("OK, I'll be quiet.", channel, nick=nick)
            elif cmd in ["unquiet", "speak", "youcantalk"]:
                self.quiet = False
                self.permaquiet = False
                self._send_message("Thanks :)", channel, nick=nick)
            elif cmd == "ignore" and self.checkAdmin(user):
                self.ignore.append(msg)
                self._send_message("OK, I'm ignoring that person now.", channel, nick=nick)
            elif cmd == "unignore" and self.checkAdmin(user):
                try:
                    self.ignore.pop(self.ignore.index(msg))
                    self._send_message("Ok, I'm not ignoring that person anymore.", channel, nick=nick)
                except KeyError:
                    self._send_message("I wasn't ignoring that person! Try !ignored to see the ignored list.", channel, nick=nick)
            elif cmd == "ignored" and self.checkAdmin(user):
                self._send_message("; ".join(self.ignore), nick)
                

    def utime(self, input):
        timezones = {"Pacific/Midway": -11, "Pacific/Niue": -11, "Pacific/Pago_Pago": -11, "Pacific/Samoa": -11, "US/Samoa": -11, 
            "America/Adak": -10, "America/Atka": -10, "HST": -10, "Pacific/Honolulu": -10, "Pacific/Johnston": -10, 
            "Pacific/Rarotonga": -10, "Pacific/Tahiti": -10, "US/Aleutian": -10, "US/Hawaii": -10, "Pacific/Marquesas": -9.5, 
            "AKST9AKDT": -9, "America/Anchorage": -9, "America/Juneau": -9, "America/Nome": -9, "America/Sitka": -9, 
            "America/Yakutat": -9, "Pacific/Gambier": -9, "US/Alaska": -9, "America/Dawson": -8, "America/Ensenada": -8, 
            "America/Los_Angeles": -8, "America/Metlakatla": -8, "America/Santa_Isabel": -8, "America/Tijuana": -8, "America/Vancouver": -8, 
            "America/Whitehorse": -8, "Canada/Pacific": -8, "Canada/Yukon": -8, "Mexico/BajaNorte": -8, "Pacific/Pitcairn": -8, 
            "PST8PDT": -8, "US/Pacific": -8, "US/Pacific-New": -8, "America/Boise": -7, "America/Cambridge_Bay": -7, "America/Chihuahua": -7, 
            "America/Creston": -7, "America/Dawson_Creek": -7, "America/Denver": -7, "America/Edmonton": -7, "America/Hermosillo": -7, 
            "America/Inuvik": -7, "America/Mazatlan": -7, "America/Ojinaga": -7, "America/Phoenix": -7, "America/Shiprock": -7, 
            "America/Yellowknife": -7, "Canada/Mountain": -7, "Mexico/BajaSur": -7, "MST": -7, "MST7MDT": -7, "Navajo": -7, 
            "US/Arizona": -7, "US/Mountain": -7, "America/Bahia_Banderas": -6, "America/Belize": -6, "America/Cancun": -6, 
            "America/Chicago": -6, "America/Costa_Rica": -6, "America/El_Salvador": -6, "America/Guatemala": -6, "America/Indiana/Knox": -6, 
            "America/Indiana/Tell_City": -6, "America/Knox_IN": -6, "America/Managua": -6, "America/Matamoros": -6, "America/Menominee": -6, 
            "America/Merida": -6, "America/Mexico_City": -6, "America/Monterrey": -6, "America/North_Dakota/Beulah": -6, 
            "America/North_Dakota/Center": -6, "America/North_Dakota/New_Salem": -6, "America/Rainy_River": -6, "America/Rankin_Inlet": -6, 
            "America/Regina": -6, "America/Resolute": -6, "America/Swift_Current": -6, "America/Tegucigalpa": -6, "America/Winnipeg": -6, 
            "Canada/Central": -6, "Canada/East-Saskatchewan": -6, "Canada/Saskatchewan": -6, "Chile/EasterIsland": -6, "CST6CDT": -6, 
            "Mexico/General": -6, "Pacific/Easter": -6, "Pacific/Galapagos": -6, "US/Central": -6, "US/Indiana-Starke": -6, 
            "America/Atikokan": -5, "America/Bogota": -5, "America/Cayman": -5, "America/Coral_Harbour": -5, "America/Detroit": -5, 
            "America/Fort_Wayne": -5, "America/Grand_Turk": -5, "America/Guayaquil": -5, "America/Havana": -5, 
            "America/Indiana/Indianapolis": -5, "America/Indiana/Marengo": -5, "America/Indiana/Petersburg": -5, "America/Indiana/Vevay": -5, 
            "America/Indiana/Vincennes": -5, "America/Indiana/Winamac": -5, "America/Indianapolis": -5, "America/Iqaluit": -5, 
            "America/Jamaica": -5, "America/Kentucky/Louisville": -5, "America/Kentucky/Monticello": -5, "America/Lima": -5, 
            "America/Louisville": -5, "America/Montreal": -5, "America/Nassau": -5, "America/New_York": -5, "America/Nipigon": -5, 
            "America/Panama": -5, "America/Pangnirtung": -5, "America/Port-au-Prince": -5, "America/Thunder_Bay": -5, "America/Toronto": -5, 
            "Canada/Eastern": -5, "Cuba": -5, "EST": -5, "EST5EDT": -5, "Jamaica": -5, "US/Eastern": -5, "US/East-Indiana": -5, 
            "US/Michigan": -5, "America/Caracas": -4.5, "America/Anguilla": -4, "America/Antigua": -4, "America/Aruba": -4, 
            "America/Asuncion": -4, "America/Barbados": -4, "America/Blanc-Sablon": -4, "America/Boa_Vista": -4, "America/Campo_Grande": -4, 
            "America/Cuiaba": -4, "America/Curacao": -4, "America/Dominica": -4, "America/Eirunepe": -4, "America/Glace_Bay": -4, 
            "America/Goose_Bay": -4, "America/Grenada": -4, "America/Guadeloupe": -4, "America/Guyana": -4, "America/Halifax": -4, 
            "America/Kralendijk": -4, "America/La_Paz": -4, "America/Lower_Princes": -4, "America/Manaus": -4, "America/Marigot": -4, 
            "America/Martinique": -4, "America/Moncton": -4, "America/Montserrat": -4, "America/Port_of_Spain": -4, 
            "America/Porto_Acre": -4, "America/Porto_Velho": -4, "America/Puerto_Rico": -4, "America/Rio_Branco": -4, 
            "America/Santiago": -4, "America/Santo_Domingo": -4, "America/St_Barthelemy": -4, "America/St_Kitts": -4, 
            "America/St_Lucia": -4, "America/St_Thomas": -4, "America/St_Vincent": -4, "America/Thule": -4, "America/Tortola": -4, 
            "America/Virgin": -4, "Antarctica/Palmer": -4, "Atlantic/Bermuda": -4, "Brazil/Acre": -4, "Brazil/West": -4, 
            "Canada/Atlantic": -4, "Chile/Continental": -4, "America/St_Johns": -3.5, "Canada/Newfoundland": -3.5, "America/Araguaina": -3, 
            "America/Argentina/Buenos_Aires": -3, "America/Argentina/Catamarca": -3, "America/Argentina/ComodRivadavia": -3, 
            "America/Argentina/Cordoba": -3, "America/Argentina/Jujuy": -3, "America/Argentina/La_Rioja": -3, 
            "America/Argentina/Mendoza": -3, "America/Argentina/Rio_Gallegos": -3, "America/Argentina/Salta": -3, 
            "America/Argentina/San_Juan": -3, "America/Argentina/San_Luis": -3, "America/Argentina/Tucuman": -3, 
            "America/Argentina/Ushuaia": -3, "America/Bahia": -3, "America/Belem": -3, "America/Buenos_Aires": -3, 
            "America/Catamarca": -3, "America/Cayenne": -3, "America/Cordoba": -3, "America/Fortaleza": -3, "America/Godthab": -3, 
            "America/Jujuy": -3, "America/Maceio": -3, "America/Mendoza": -3, "America/Miquelon": -3, "America/Montevideo": -3, 
            "America/Paramaribo": -3, "America/Recife": -3, "America/Rosario": -3, "America/Santarem": -3, "America/Sao_Paulo": -3, 
            "Antarctica/Rothera": -3, "Atlantic/Stanley": -3, "Brazil/East": -3, "America/Noronha": -2, "Atlantic/South_Georgia": -2, 
            "Brazil/DeNoronha": -2, "America/Scoresbysund": -1, "Atlantic/Azores": -1, "Atlantic/Cape_Verde": -1, 
            "Pacific/Kiritimati": +14, "Pacific/Apia": +13, "Pacific/Enderbury": +13, "Pacific/Fakaofo": +13, 
            "Pacific/Tongatapu": +13, "NZ-CHAT": +12.75, "Pacific/Chatham": +12.75, "Antarctica/McMurdo": +12, 
            "Antarctica/South_Pole": +12, "Asia/Anadyr": +12, "Asia/Kamchatka": +12, "Asia/Magadan": +12, "Kwajalein": +12, 
            "NZ": +12, "Pacific/Auckland": +12, "Pacific/Fiji": +12, "Pacific/Funafuti": +12, "Pacific/Kwajalein": +12, 
            "Pacific/Majuro": +12, "Pacific/Nauru": +12, "Pacific/Tarawa": +12, "Pacific/Wake": +12, "Pacific/Wallis": +12, 
            "Pacific/Norfolk": +11.5, "Antarctica/Casey": +11, "Antarctica/Macquarie": +11, "Asia/Sakhalin": +11, 
            "Asia/Vladivostok": +11, "Pacific/Efate": +11, "Pacific/Guadalcanal": +11, "Pacific/Kosrae": +11, "Pacific/Noumea": +11, 
            "Pacific/Pohnpei": +11, "Pacific/Ponape": +11, "Australia/LHI": +10.5, "Australia/Lord_Howe": +10.5, 
            "Antarctica/DumontDUrville": +10, "Asia/Yakutsk": +10, "Australia/ACT": +10, "Australia/Brisbane": +10, 
            "Australia/Canberra": +10, "Australia/Currie": +10, "Australia/Hobart": +10, "Australia/Lindeman": +10, 
            "Australia/Melbourne": +10, "Australia/NSW": +10, "Australia/Queensland": +10, "Australia/Sydney": +10, 
            "Australia/Tasmania": +10, "Australia/Victoria": +10, "Pacific/Chuuk": +10, "Pacific/Guam": +10, 
            "Pacific/Port_Moresby": +10, "Pacific/Saipan": +10, "Pacific/Truk": +10, "Pacific/Yap": +10, "Australia/Adelaide": 9.5, 
            "Australia/Broken_Hill": 9.5, "Australia/Darwin": 9.5, "Australia/North": 9.5, "Australia/South": 9.5, 
            "Australia/Yancowinna": 9.5, "Asia/Dili": 9, "Asia/Irkutsk": 9, "Asia/Jayapura": 9, "Asia/Pyongyang": 9, 
            "Asia/Seoul": 9, "Asia/Tokyo": 9, "Japan": 9, "JST-9": 9, "Pacific/Palau": 9, "ROK": 9, "Australia/Eucla": 8.75, 
            "Asia/Brunei": 8, "Asia/Choibalsan": 8, "Asia/Chongqing": 8, "Asia/Chungking": 8, "Asia/Harbin": 8, 
            "Asia/Hong_Kong": 8, "Asia/Kashgar": 8, "Asia/Krasnoyarsk": 8, "Asia/Kuala_Lumpur": 8, "Asia/Kuching": 8, 
            "Asia/Macao": 8, "Asia/Macau": 8, "Asia/Makassar": 8, "Asia/Manila": 8, "Asia/Shanghai": 8, "Asia/Singapore": 8, 
            "Asia/Taipei": 8, "Asia/Ujung_Pandang": 8, "Asia/Ulaanbaatar": 8, "Asia/Ulan_Bator": 8, "Asia/Urumqi": 8, 
            "Australia/Perth": 8, "Australia/West": 8, "Hong Kong": 8, "PRC": 8, "ROC": 8, "Singapore": 8, "Asia/Bangkok": 7, 
            "Asia/Ho_Chi_Minh": 7, "Asia/Hovd": 7, "Asia/Jakarta": 7, "Asia/Novokuznetsk": 7, "Asia/Novosibirsk": 7, "Asia/Omsk": 7, 
            "Asia/Phnom_Penh": 7, "Asia/Pontianak": 7, "Asia/Saigon": 7, "Asia/Vientiane": 7, "Indian/Christmas": 7, "Asia/Rangoon": 6.5, 
            "Indian/Cocos": 6.5, "Antarctica/Vostok": 6, "Asia/Almaty": 6, "Asia/Bishkek": 6, "Asia/Dacca": 6, "Asia/Dhaka": 6, 
            "Asia/Qyzylorda": 6, "Asia/Thimbu": 6, "Asia/Thimphu": 6, "Asia/Yekaterinburg": 6, "Indian/Chagos": 6, "Asia/Kathmandu": 5.75, 
            "Asia/Katmandu": 5.75, "Asia/Calcutta": 5.5, "Asia/Colombo": 5.5, "Asia/Kolkata": 5.5, "Antarctica/Davis": 5, 
            "Antarctica/Mawson": 5, "Asia/Aqtau": 5, "Asia/Aqtobe": 5, "Asia/Ashgabat": 5, "Asia/Ashkhabad": 5, "Asia/Dushanbe": 5, 
            "Asia/Karachi": 5, "Asia/Oral": 5, "Asia/Samarkand": 5, "Asia/Tashkent": 5, "Indian/Kerguelen": 5, "Indian/Maldives": 5, 
            "Asia/Kabul": 4.5, "Asia/Baku": 4, "Asia/Dubai": 4, "Asia/Muscat": 4, "Asia/Tbilisi": 4, "Asia/Yerevan": 4, "Europe/Moscow": 4, 
            "Europe/Samara": 4, "Europe/Volgograd": 4, "Indian/Mahe": 4, "Indian/Mauritius": 4, "Indian/Reunion": 4, "W-SU": 4, 
            "Asia/Tehran": 3.5, "Iran": 3.5, "Africa/Addis_Ababa": 3, "Africa/Asmara": 3, "Africa/Asmera": 3, "Africa/Dar_es_Salaam": 3, 
            "Africa/Djibouti": 3, "Africa/Juba": 3, "Africa/Kampala": 3, "Africa/Khartoum": 3, "Africa/Mogadishu": 3, "Africa/Nairobi": 3, 
            "Antarctica/Syowa": 3, "Asia/Aden": 3, "Asia/Amman": 3, "Asia/Baghdad": 3, "Asia/Bahrain": 3, "Asia/Kuwait": 3, "Asia/Qatar": 3, 
            "Asia/Riyadh": 3, "Europe/Kaliningrad": 3, "Europe/Minsk": 3, "Indian/Antananarivo": 3, "Indian/Comoro": 3, "Indian/Mayotte": 3, 
            "Africa/Blantyre": 2, "Africa/Bujumbura": 2, "Africa/Cairo": 2, "Africa/Gaborone": 2, "Africa/Harare": 2, 
            "Africa/Johannesburg": 2, "Africa/Kigali": 2, "Africa/Lubumbashi": 2, "Africa/Lusaka": 2, "Africa/Maputo": 2, "Africa/Maseru": 2, 
            "Africa/Mbabane": 2, "Asia/Beirut": 2, "Asia/Damascus": 2, "Asia/Gaza": 2, "Asia/Hebron": 2, "Asia/Istanbul": 2, 
            "Asia/Jerusalem": 2, "Asia/Nicosia": 2, "Asia/Tel_Aviv": 2, "EET": 2, "Egypt": 2, "Europe/Athens": 2, "Europe/Bucharest": 2, 
            "Europe/Chisinau": 2, "Europe/Helsinki": 2, "Europe/Istanbul": 2, "Europe/Kiev": 2, "Europe/Mariehamn": 2, "Europe/Nicosia": 2, 
            "Europe/Riga": 2, "Europe/Simferopol": 2, "Europe/Sofia": 2, "Europe/Tallinn": 2, "Europe/Tiraspol": 2, "Europe/Uzhgorod": 2, 
            "Europe/Vilnius": 2, "Europe/Zaporozhye": 2, "Israel": 2, "Libya": 2, "Turkey": 2, "Africa/Algiers": 1, "Africa/Bangui": 1, 
            "Africa/Brazzaville": 1, "Africa/Ceuta": 1, "Africa/Douala": 1, "Africa/Kinshasa": 1, "Africa/Lagos": 1, "Africa/Libreville": 1, 
            "Africa/Luanda": 1, "Africa/Malabo": 1, "Africa/Ndjamena": 1, "Africa/Niamey": 1, "Africa/Porto-Novo": 1, "Africa/Tripoli": 1, 
            "Africa/Tunis": 1, "Africa/Windhoek": 1, "Arctic/Longyearbyen": 1, "Atlantic/Jan_Mayen": 1, "CET": 1, "Europe/Amsterdam": 1, 
            "Europe/Andorra": 1, "Europe/Belgrade": 1, "Europe/Berlin": 1, "Europe/Bratislava": 1, "Europe/Brussels": 1, "Europe/Budapest": 1, 
            "Europe/Copenhagen": 1, "Europe/Gibraltar": 1, "Europe/Ljubljana": 1, "Europe/Luxembourg": 1, "Europe/Madrid": 1, 
            "Europe/Malta": 1, "Europe/Monaco": 1, "Europe/Oslo": 1, "Europe/Paris": 1, "Europe/Podgorica": 1, "Europe/Prague": 1, 
            "Europe/Rome": 1, "Europe/San_Marino": 1, "Europe/Sarajevo": 1, "Europe/Skopje": 1, "Europe/Stockholm": 1, "Europe/Tirane": 1, 
            "Europe/Vaduz": 1, "Europe/Vatican": 1, "Europe/Vienna": 1, "Europe/Warsaw": 1, "Europe/Zagreb": 1, "Europe/Zurich": 1, "MET": 1, 
            "Poland": 1, "Africa/Abidjan": 0, "Africa/Accra": 0, "Africa/Bamako": 0, "Africa/Banjul": 0, "Africa/Bissau": 0, 
            "Africa/Casablanca": 0, "Africa/Conakry": 0, "Africa/Dakar": 0, "Africa/El_Aaiun": 0, "Africa/Freetown": 0, "Africa/Lome": 0, 
            "Africa/Monrovia": 0, "Africa/Nouakchott": 0, "Africa/Ouagadougou": 0, "Africa/Sao_Tome": 0, "Africa/Timbuktu": 0, 
            "America/Danmarkshavn": 0, "Atlantic/Canary": 0, "Atlantic/Faeroe": 0, "Atlantic/Faroe": 0, "Atlantic/Madeira": 0, 
            "Atlantic/Reykjavik": 0, "Atlantic/St_Helena": 0, "Eire": 0, "Etc./GMT": 0, "Etc./GMT+0": 0, "Etc./UCT": 0, "Etc./Universal": 0, 
            "Etc./UTC": 0, "Etc./Zulu": 0, "Europe/Belfast": 0, "Europe/Dublin": 0, "Europe/Guernsey": 0, "Europe/Isle_of_Man": 0, 
            "Europe/Jersey": 0, "Europe/Lisbon": 0, "Europe/London": 0, "GB": 0, "GB-Eire": 0, "GMT": 0, "GMT+0": 0, "GMT0": 0, "GMT-0": 0, 
            "Greenwich": 0, "Iceland": 0, "Portugal": 0, "UCT": 0, "Universal": 0, "UTC": 0, "WET": 0, "Zulu": 0}
 
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
                    import difflib
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
                return time.strftime("[b]%H:%M:%S %d %b %Y[/b]", time.gmtime(ts)) + " in " + tz
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
