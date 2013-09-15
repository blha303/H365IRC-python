from twisted.words.protocols import irc
from twisted.internet import protocol, task, reactor
import yaml, urllib2, json

with open("config.yml") as file:
    config = yaml.load(file.read())

class Bot(irc.IRCClient):
    nickname = config["nickname"]
    username = config["username"]
    lastDj = "Default"
    lastSong = "Default"
    
    def updateData(self):
        data = json.loads(urllib2.urlopen("http://data.hive365.co.uk/stream/info.php").read())["info"]
        choons, poons = ("not yet", "implemented")
        msg = None
        if self.lastDj != data["title"]:
            # New DJ!
            msg = "DJ Change! %s >> %s" % (self.lastDj, data["title"])
            self.lastDj = data["title"]
        if self.lastSong != data["artist_song"]:
            # New song!
            msg = "New Song: %s || Choons: %s Poons: %s" % (data["artist_song"], choons, poons)
            self.lastSong = data["artist_song"]
        if msg:
            self._send_message(msg, config["channel"])

    def signedOn(self):
        self.join(self.factory.channel)
        task.LoopingCall(self.updateData).start(2.0)
        print "Signed on as %s." % (self.nickname,)

    def joined(self, channel):
        print "Joined %s." % (channel,)

    def _send_message(self, msg, target, nick=None):
        if nick:
            msg = '%s, %s' % (nick, msg)
        self.msg(target, msg.encode('ascii', 'ignore'))

    def privmsg(self, user, channel, msg):
        nick, _, host = user.partition('!')
        print msg
        if msg[0] == "!":
            if msg[0:3] == "!dj":
                out = "Current DJ: %s" % self.lastDj
                self._send_message(out, channel, nick=nick)
                

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