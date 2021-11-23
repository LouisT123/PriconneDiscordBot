from Priconne.notification import Notification

import discord

class Priconne(discord.Client):
    def __init__(self, config):
        super().__init__(
            activity=discord.Game(name=config.get("playing_status", "with Dragon Veins")),
            intents=discord.Intents.all()
        )
        self.config = config
        self.notification = Notification(self)

    async def on_ready(self):
        print("[Priconne Discord Bot by EndenDragon#1337]")
        print("For Ahjin Priconne Guild")
        print(self.user.name)
        print(self.user.id)
        print('------')
