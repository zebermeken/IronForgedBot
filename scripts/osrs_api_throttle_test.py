#!/usr/bin/env python3
import os
import sys

# Add the parent directory to sys.path to allow absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
import time

from ironforgedbot.commands.hiscore.calculator import (
    HiscoresNotFound,
    get_player_points_total,
)
from ironforgedbot.common.helpers import normalize_discord_string
from ironforgedbot.http import HTTP, HttpException

osrs_player_names = [
    "Lynx Titan",
    "Hey Jase",
    "ShawnBay",
    "Zezima",
    "Lelador",
    "Alkan",
    "WoopDooDoo",
    "A Friend",
    "B0aty",
    "Framed",
    "Torvesta",
    "SirPugger",
    "Settled",
    "C Engineer",
    "Faux",
    "Mmorpg",
    "Soup",
    "KempQ",
    "Rhys",
    "TorvestaRS",
    "Sparc Mac",
    "Mr Mammal",
    "Sick Nerd",
    "Skill Specs",
    "Slayermusiq1",
    "Woox",
    "Rendi",
    "Jebrim",
    "Faux",
    "Manked",
    "Mote Plox",
    "Rajj Patel",
    "Vio",
    "Acid Soul",
    "Bradfordly",
    "Clayton",
    "Destiny",
    "Du Old Pker",
    "Eetsk",
    "Evil Oak",
    "Heur",
    "Home Page",
    "Itz Hickton",
    "KrimsonKueen",
    "Martin 2007",
    "Malt Lickeys",
    "Metal Shad0w",
    "NoToAfkPray",
    "Paulrat 3",
    "Randalicious",
    "Runes",
    "Sathon",
    "suckitlosers",
    "Talk-to",
    "Unohdettu2",
    "Aspersion",
    "Calisme",
    "iDrizzay",
    "Mini Finbarr",
    "Pur",
    "Sc0ooby Doo",
    "Sjoerd nl",
    "Stupidman990",
    "unik4kosova",
    "Vestfold",
    "Word man",
    "Xav777",
    "Yalps",
    "Zezima",
    "Lynx Titan",
    "Hey Jase",
    "ShawnBay",
    "Lelador",
    "Alkan",
    "WoopDooDoo",
    "A Friend",
    "B0aty",
    "Framed",
    "Torvesta",
    "SirPugger",
    "Settled",
    "C Engineer",
    "Faux",
    "Mmorpg",
    "Soup",
    "KempQ",
    "Rhys",
    "TorvestaRS",
    "Sparc Mac",
    "Mr Mammal",
    "Sick Nerd",
    "Skill Specs",
    "Slayermusiq1",
    "Woox",
    "Rendi",
    "Jebrim",
    "Faux",
    "Manked",
    "Mote Plox",
    "Rajj Patel",
    "Vio",
    "Acid Soul",
    "Bradfordly",
    "Clayton",
    "Destiny",
    "Du Old Pker",
    "Eetsk",
    "Evil Oak",
    "Heur",
    "Home Page",
    "Itz Hickton",
    "KrimsonKueen",
    "Martin 2007",
    "Malt Lickeys",
    "Metal Shad0w",
    "NoToAfkPray",
    "Paulrat 3",
    "Randalicious",
    "Runes",
    "Sathon",
    "suckitlosers",
    "Talk-to",
    "Unohdettu2",
    "Aspersion",
    "Calisme",
    "iDrizzay",
    "Mini Finbarr",
    "Pur",
    "Sc0ooby Doo",
    "Sjoerd nl",
    "Stupidman990",
    "unik4kosova",
    "Vestfold",
    "Word man",
    "Xav777",
    "Yalps",
    "Zezima",
    "Lynx Titan",
    "Hey Jase",
    "ShawnBay",
    "Lelador",
    "Alkan",
    "WoopDooDoo",
    "A Friend",
    "B0aty",
    "Framed",
    "Torvesta",
    "SirPugger",
    "Settled",
    "C Engineer",
    "Faux",
    "Mmorpg",
    "Soup",
    "KempQ",
    "Rhys",
    "TorvestaRS",
    "Sparc Mac",
    "Mr Mammal",
    "Sick Nerd",
    "Skill Specs",
    "Slayermusiq1",
    "Woox",
    "Rendi",
    "Jebrim",
    "Faux",
    "Manked",
    "Mote Plox",
    "Rajj Patel",
    "Vio",
    "Acid Soul",
    "Bradfordly",
    "Clayton",
    "Destiny",
    "Du Old Pker",
    "Eetsk",
    "Evil Oak",
    "Heur",
    "Home Page",
    "Itz Hickton",
    "KrimsonKueen",
    "Martin 2007",
    "Malt Lickeys",
    "Metal Shad0w",
    "NoToAfkPray",
    "Paulrat 3",
    "Randalicious",
    "Runes",
    "Sathon",
    "suckitlosers",
    "Talk-to",
    "Unohdettu2",
    "Aspersion",
    "Calisme",
    "iDrizzay",
    "Mini Finbarr",
    "Pur",
    "Sc0ooby Doo",
    "Sjoerd nl",
    "Stupidman990",
    "unik4kosova",
    "Vestfold",
    "Word man",
    "Xav777",
    "Yalps",
]


async def main():
    start_time = time.time()
    for player in osrs_player_names:
        points = 0

        try:
            points = await get_player_points_total(normalize_discord_string(player))
        except HttpException as e:
            points = "HttpException"
            print(e)
        except HiscoresNotFound:
            points = "Not Found on Hiscores"
        except Exception as e:
            print(e)

        print(f"{player}: {points}")

    await HTTP.cleanup()
    end_time = time.time()

    print(
        f"\n\nProcessed {len(osrs_player_names)} players in {end_time- start_time:.4f} seconds"
    )
    exit()


asyncio.run(main())
