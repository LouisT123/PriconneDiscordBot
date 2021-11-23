import datetime
import aiohttp
import asyncio
from Crypto.Cipher import AES
import codecs
from Crypto.Util import Counter
import json
from dateutil import tz

# https://stackoverflow.com/questions/12524994/encrypt-decrypt-using-pycrypto-aes-256
# https://github.com/beenotung/compress-json

class JSONDecompressor:
    def __init__(self):
        i_to_s = ""
        for i in range(0, 10, 1):
            c = chr(48 + i)
            i_to_s = i_to_s + c
        for i in range(0, 26, 1):
            c = chr(65 + i)
            i_to_s = i_to_s + c
        for i in range(0, 26, 1):
            c = chr(65 + 32 + i)
            i_to_s = i_to_s + c
        self.N = len(i_to_s)
        self.s_to_i = {}
        for i in range(0, self.N, 1):
            s = i_to_s[i]
            self.s_to_i[s] = i

    def s_to_int(self, s):
        acc = 0
        pow = 1
        for i in range(len(s) - 1, -1, -1):
            c = s[i]
            x = self.s_to_i[c]
            x *= pow
            acc += x
            pow *= self.N
        return acc

    def s_to_big_int(self, s):
        return self.s_to_int(s)

    def decodeKey(self, key):
        if isinstance(key, int):
            return key
        return self.s_to_int(key)

    def decodeBool(self, s):
        if s == "b|T":
            return True
        elif s == "b|F":
            return False
        return bool(s)

    def decodeObject(self, values, s):
        if s == "o|":
            return {}
        o = {}
        vs = s.split("|")
        key_id = vs[1]
        keys = self.decode(values, key_id)
        n = len(vs)
        if (n - 2 == 1 and not isinstance(keys, list)):
            keys = [keys]
        for i in range(2, n, 1):
            k = keys[i - 2]
            v = vs[i]
            v = self.decode(values, v)
            o[k] = v
        return o

    def s_to_int_str(self, s):
        if s[0] == ":":
            return str(self.s_to_big_int(s[1:]))
        return str(self.s_to_int(s))

    def reverse(self, s):
        return s[::-1]

    def s_to_num(self, s):
        if s[0] == "-":
            return -1 * self.s_to_num(s[1:])
        if "." not in s:
            return self.s_to_int(s)
        a = self.s_to_int_str(a)
        b = self.s_to_int_str(b)
        b = self.reverse(b)
        return float(a + "." + b)

    def decodeNum(self, s):
        s = s.replace("n|", "")
        return self.s_to_num(s)

    # list, index, value
    def set_list(self, l, i, v):
      try:
          l[i] = v
      except IndexError:
          for _ in range(i-len(l)+1):
              l.append(None)
          l[i] = v

    def decodeArray(self, values, s):
        if s == "a|":
            return []
        vs = s.split("|")
        n = len(vs) - 1
        xs = []
        for i in range(0, n, 1):
            v = vs[i + 1]
            v = self.decode(values, v)
            self.set_list(xs, i, v) # xs[i] = v
        return xs

    def decodeStr(self, s):
        prefix = s[0] + s[1]
        if prefix == "s|":
            return s[2:]
        return s

    def decode(self, values, key):
        if key == "" or key == "_":
            return None
        id = self.decodeKey(key)
        try:
            v = values[id]
        except IndexError:
            v = None
        if v is None:
            return v
        if isinstance(v, int):
            return v
        elif isinstance(v, str):
            prefix = v[0] + v[1]
            if prefix == "b|":
                return self.decodeBool(v)
            elif prefix == "o|":
                return self.decodeObject(values, v)
            elif prefix == "n|":
                return self.decodeNum(v)
            elif prefix == "a|":
                return self.decodeArray(values, v)
            else:
                return self.decodeStr(v)
    
    def decompress(self, c):
        values, root = c
        return self.decode(values, root)

class Notification:
    def __init__(self, client):
        self.client = client
        self.channel_id = self.client.config.get("notification_channelid", None)
        self.httpsession = aiohttp.ClientSession()
        self.decompressor = JSONDecompressor()

        self.bg_task = self.client.loop.create_task(self.background_task())

    async def background_task(self):
        await self.client.wait_until_ready()
        utc = datetime.datetime.utcnow()
        wait = 0
        if utc.second > 5:
            wait = 60 - utc.second + 5
        else:
            wait = 5 - utc.second
        await asyncio.sleep(wait)
        while not self.client.is_closed():
            utc = datetime.datetime.utcnow()
            if utc.hour == 13 and utc.minute == 0:
                await self.run_reminders()
                await asyncio.sleep(120)
            await asyncio.sleep(30)

    async def fetch_events(self):
        url = "https://kenofnz.github.io/priconne-en-event-timer/data/data.json"
        async with self.httpsession.get(url) as resp:
            if resp.status < 200 or resp.status >= 300:
                return []
            req = await resp.json()

            iv = req["iv"]
            content = req["content"]
            content = codecs.decode(content, 'hex')

            key = "vOVH6sdmpNWjRRIqCc7rdxs01lwHzfr3"
            iv_int = int(iv, 16)
            ctr = Counter.new(AES.block_size * 8, initial_value=iv_int)
            aes = AES.new(key, AES.MODE_CTR, counter=ctr)
            plaintext = aes.decrypt(content).decode("utf-8")

            data = json.loads(plaintext)
            decompressed = self.decompressor.decompress(data)
            return decompressed["events"]
        return []

    async def run_reminders(self):
        events = await self.fetch_events()
        utc = datetime.datetime.utcnow()
        output = "**Princess Connect Schedule**"
        starting_events = []
        ending_events = []
        for event in events:
            name = event["event_name"]
            icon_src = event.get("icon_src", "")
            start_time = datetime.datetime.strptime(event["start_time"], '%Y/%m/%d %H:%M:%S')
            start_time.replace(tzinfo=tz.tzutc())
            end_time = datetime.datetime.strptime(event["end_time"], '%Y/%m/%d %H:%M:%S')
            end_time.replace(tzinfo=tz.tzutc())
            if start_time > utc - datetime.timedelta(hours=1) and start_time < utc + datetime.timedelta(hours=23):
                # "StartDate > DATE_SUB(NOW(), INTERVAL 1 HOUR) AND StartDate < DATE_ADD(NOW(), INTERVAL 23 HOUR)"
                starting_events.append(event)
            elif end_time < utc + datetime.timedelta(hours=24) and end_time > utc:
                # "EndDate < DATE_ADD(NOW(), INTERVAL 1 DAY) AND EndDate > NOW()"
                ending_events.append(event)
        if len(starting_events):
            output = output + "\n__Events Starting Today:__"
            for event in starting_events:
                output = output + "\n{}".format(event["event_name"])
            output = output + "\n"
        if len(ending_events):
            output = output + "\n__Events Ending Today:__"
            for event in ending_events:
                output = output + "\n{}".format(event["event_name"])
            output = output + "\n"
        if len(starting_events) or len(ending_events):
            channel = self.client.get_channel(self.channel_id)
            if channel:
                await channel.send(output)
