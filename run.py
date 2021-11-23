from Priconne.bot import Priconne
from config import CONFIG

priconne = Priconne(CONFIG)
priconne.run(CONFIG["bot_token"])
