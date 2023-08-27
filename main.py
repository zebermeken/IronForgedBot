from typing import Dict, List, Union

import argparse
from datetime import datetime
import os
import sys
from pytz import timezone

import discord
from discord import app_commands
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError
from common import point_values


# Don't care about line length for URLs & constants.
# pylint: disable=line-too-long
HISCORES_PLAYER_URL = 'https://secure.runescape.com/m=hiscore_oldschool/index_lite.ws?player={player}'
LEVEL_99_EXPERIENCE = 13034431

SHEETS_SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
# Skip header in read.
SHEET_RANGE = 'ClanIngots!A2:B'
SHEET_RANGE_WITH_DISCORD_IDS = 'ClanIngots!A2:C'
CHANGELOG_RANGE = 'ChangeLog!A2:F'
# pylint: enable=line-too-long


def read_dotenv(path: str) -> Dict[str, str]:
    """Read config from a file of k=v entries."""
    config = {}
    with open(path, 'r') as f:
        for line in f:
            tmp = line.partition('=')
            config[tmp[0]] = tmp[2].removesuffix('\n')

    return config


def validate_initial_config(config: Dict[str, str]) -> bool:
    if config.get('SHEETID') is None:
        print('validation failed; SHEETID required but not present in env')
        return False
    if config.get('GUILDID') is None:
        print('validation failed; GUILDID required but not present in env')
        return False
    if config.get('BOT_TOKEN') is None:
        print('validation failed; ' +
              'BOT_TOKEN required but not present in env')
        return False

    return True


def validate_player_name(player: str) -> bool:
    if len(player) > 12:
        return False
    return True


def compute_clan_icon(points: int):
    """Determine Icon name to include in response."""
    if points >= 13000:
        return "Myth"
    if points >= 9000:
        return "Legend"
    if points >= 5000:
        return "Dragon"
    if points >= 3000:
        return "Rune"
    if points >= 1500:
        return "Adamant"
    if points >= 700:
        return "Mithril"
    return "Iron"


def is_admin(member: discord.Member) -> bool:
    """Check if a member has a leadership role."""
    roles = member.roles
    for role in roles:
        if role.name == "Leadership":
            return True

    return False


class DiscordClient(discord.Client):
    """Client class for bot to handle slashcommands.

    There is a chicken&egg relationship between a discord client & the
    command tree. The tree needs a client during init, but the easiest
    way to upload commands is during client.setup_hook. So, initialize
    the client first, then the tree, then add the tree property before
    calling client.run.

    intents = discord.Intents.default()
    guild = discord.Object(id=$ID)
    client = DiscordClient(intents=intents, upload=true, guild=guild)
    tree = BuildCommandTree(client)
    client.tree = tree

    client.run('token')

    Attributes:
        upload: Whether or not to upload commands to guild.
        guild: Guild for this client to upload commands to.
        tree: CommandTree to use for uploading commands.
    """
    def __init__(
        self, *, intents: discord.Intents, upload: bool,
        guild: discord.Object):
        super().__init__(intents=intents)
        self.upload=upload
        self.guild=guild

    @property
    def tree(self):
        return self._tree

    @tree.setter
    def tree(self, value: app_commands.CommandTree):
        self._tree = value

    async def setup_hook(self):
        # Copy commands to the guild (Discord server)
        # TODO: Move this to a separate CLI solely for uploading commands.
        if self.upload:
            self._tree.copy_global_to(guild=self.guild)
            await self._tree.sync(guild=self.guild)

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        print('------')


class IronForgedCommands:
    def __init__(
        self,
        tree: discord.app_commands.CommandTree,
        discord_client: DiscordClient,
        # TODO: replace sheets client with a storage interface &
        # pass in a sheets impl.
        sheets_client: Resource,
        sheet_id: str,
        breakdown_dir_path: str,
        clock: datetime = None):
        self._tree = tree
        self._discord_client = discord_client
        self._sheets_client = sheets_client
        self._sheet_id = sheet_id
        self._breakdown_dir_path = breakdown_dir_path
        if clock is None:
            self._clock = datetime
        else:
            self._clock = clock

        # Description only sets the brief description.
        # Arg descriptions are pulled from function definition.
        score_command = app_commands.Command(
            name="score",
            description="Compute clan score for a player.",
            callback=self.score,
            nsfw=False,
            parent=None,
            auto_locale_strings=True,
        )
        self._tree.add_command(score_command)

        breakdown_command = app_commands.Command(
            name="breakdown",
            description="Get full breakdown of score for a player.",
            callback=self.breakdown,
            nsfw=False,
            parent=None,
            auto_locale_strings=True,
        )
        self._tree.add_command(breakdown_command)

        ingots_command = app_commands.Command(
            name="ingots",
            description="View current ingots for a player.",
            callback=self.ingots,
            nsfw=False,
            parent=None,
            auto_locale_strings=True,
        )
        self._tree.add_command(ingots_command)

        addingots_command = app_commands.Command(
            name="addingots",
            description="Add or remove ingots to a player.",
            callback=self.addingots,
            nsfw=False,
            parent=None,
            auto_locale_strings=True,
        )
        self._tree.add_command(addingots_command)

        updateingots_command = app_commands.Command(
            name="updateingots",
            description="Set a player's ingot count to a new value.",
            callback=self.updateingots,
            nsfw=False,
            parent=None,
            auto_locale_strings=True,
        )
        self._tree.add_command(updateingots_command)

        syncmembers_command = app_commands.Command(
            name="syncmembers",
            description="Sync members of Discord server with ingots storage.",
            callback=self.syncmembers,
            nsfw=False,
            parent=None,
            auto_locale_strings=True,
        )
        self._tree.add_command(syncmembers_command)


    async def score(self,
                    interaction: discord.Interaction,
                    player: str):
        """Compute clan score for a Runescape player name.

        Arguments:
            interaction: Discord Interaction from CommandTree.
            player: Runescape playername to look up score for.
        """
        if not validate_player_name(player):
            await interaction.response.send_message(
                f'FAILED_PRECONDITION: RSNs can only be 12 characters long.')
            return

        await interaction.response.defer()
        resp = requests.get(HISCORES_PLAYER_URL.format(player=player),
                            timeout=15)
        if resp.status_code != 200:
            await interaction.followup.send(
                f'Looking up {player} on hiscores failed. Got status code {resp.status_code}')
            return
        # Omit the first line of the response, which is total level & xp.
        lines = resp.text.split('\n')[1:]

        points_by_skill = skill_score(lines)
        skill_points = 0
        for _, v in points_by_skill.items():
            skill_points += v

        points_by_activity = activity_score(lines)
        activity_points = 0
        for _, v in points_by_activity.items():
            activity_points += v

        points = skill_points + activity_points

        emoji_name = compute_clan_icon(points)
        icon = ''
        for emoji in self._discord_client.get_guild(
            self._discord_client.guild.id).emojis:
            if emoji.name == emoji_name:
                icon = emoji
                break
        content=f"""{player} has {points:,}{icon}
Points from skills: {skill_points:,}
Points from minigames & bossing: {activity_points:,}"""

        await interaction.followup.send(content)


    async def breakdown(
        self,
        interaction: discord.Interaction,
        player: str):
        """Compute player score with complete source enumeration.

        Arguments:
            interaction: Discord Interaction from CommandTree.
            player: Runescape username to break down clan score for.
        """
        if not validate_player_name(player):
            await interaction.response.send_message(
                f'FAILED_PRECONDITION: RSNs can only be 12 characters long.')
            return

        await interaction.response.defer()

        resp = requests.get(HISCORES_PLAYER_URL.format(player=player),
                            timeout=15)
        if resp.status_code != 200:
            await interaction.followup.send(
                f'Looking up {player} on hiscores failed. Got status code {resp.status_code}')
            return
        # Omit the first line of the response, which is total level & xp.
        lines = resp.text.split('\n')[1:]

        points_by_skill = skill_score(lines)
        skill_points = 0
        for _, v in points_by_skill.items():
            skill_points += v

        points_by_activity = activity_score(lines)
        activity_points = 0
        for _, v in points_by_activity.items():
            activity_points += v

        total_points = skill_points + activity_points

        output = '---Points from Skills---\n'
        for i in point_values.skills():
            if points_by_skill.get(i, 0) > 0:
                output += f'{i}: {points_by_skill.get(i):,}\n'
        output += (f'Total Skill Points: {skill_points:,} ' +
            f'({round((skill_points / total_points) * 100, 2)}% of total)\n\n')
        output += '---Points from Minigames & Bossing---\n'
        for i in point_values.activities():
            if points_by_activity.get(i, 0) > 0:
                output += f'{i}: {points_by_activity.get(i):,}\n'
        output += (
            f'Total Minigame & Bossing Points: {activity_points} ' +
            f'({round((activity_points / total_points) * 100, 2)}% of total)\n\n')
        output += f'Total Points: {total_points:,}\n'

        # Now we have all of the data that we need for a full point breakdown.
        # If we write a single file though, there is a potential race
        # condition if multiple users try to run breakdown at once.
        # text files are cheap - use the player name as a good-enough amount
        # of uniquity.
        path = os.path.join(self._breakdown_dir_path, f'{player}.txt')
        with open(path, 'w') as f:
            f.write(output)

        emoji_name = compute_clan_icon(total_points)
        icon = ''
        for emoji in self._discord_client.get_guild(
            self._discord_client.guild.id).emojis:
            if emoji.name == emoji_name:
                icon = emoji
                break


        with open(path, 'rb') as f:
            discord_file = discord.File(f, filename='breakdown.txt')
            await interaction.followup.send(
                f'Total Points for {player}: {total_points}{icon}\n',
                file=discord_file)


    async def ingots(
        self, interaction: discord.Interaction, player: str):
        """View ingots for a Runescape playername.

        Arguments:
            interaction: Discord Interaction from CommandTree.
            player: Runescape username to view ingot count for.
        """
        if not validate_player_name(player):
            await interaction.response.send_message(
                f'FAILED_PRECONDITION: RSNs can only be 12 characters long.')
            return

        await interaction.response.defer()
        result = {}

        try:
            result = self._sheets_client.spreadsheets().values().get(
                spreadsheetId=self._sheet_id, range=SHEET_RANGE).execute()
        except HttpError as e:
            await interaction.followup.send(
                f'Encountered error reading from sheets: {e}')
            return

        values = result.get('values', [])

        # Response is a list of lists, all of which have 2
        # entries: ['username', count]. Transform that into
        # a dictionary.
        ingots_by_player = {}
        for i in values:
            ingots_by_player[i[0]] = i[1]

        ingots = int(ingots_by_player.get(player, 0))
        icon = ''
        for emoji in self._discord_client.get_guild(
            self._discord_client.guild.id).emojis:
            if emoji.name == 'Ingot':
                icon = emoji
        await interaction.followup.send(
            f'{player} has {ingots:,} ingots{icon}')


    async def addingots(
        self,
        interaction: discord.Interaction,
        player: str,
        ingots: int):
        """Add ingots to a Runescape alias.

        Arguments:
            interaction: Discord Interaction from CommandTree.
            player: Runescape username to view ingot count for.
            ingots: number of ingots to add to this player.
        """
        # interaction.user can be a User or Member, but we can only
        # rely on permission checking for a Member.
        member = interaction.user
        if isinstance(member, discord.User):
            await interaction.response.send_message(
                f'PERMISSION_DENIED: {member.name} is not in this guild.')
            return

        if not is_admin(member):
            await interaction.response.send_message(
                f'PERMISSION_DENIED: {member.name} is not in a leadership role.')
            return

        if not validate_player_name(player):
            await interaction.response.send_message(
                f'FAILED_PRECONDITION: RSNs can only be 12 characters long.')
            return

        await interaction.response.defer()
        result = {}

        try:
            result = self._sheets_client.spreadsheets().values().get(
                spreadsheetId=self._sheet_id, range=SHEET_RANGE).execute()
        except HttpError as e:
            await interaction.followup.send(
                f'Encountered error reading from sheets: {e}')
            return

        values = result.get('values', [])

        # Start at 2 since we skip header
        row_index = 2
        found = False
        new_value = 0
        old_value = 0
        for i in values:
            if i[0] == player:
                found = True
                old_value = int(i[1])
                new_value = int(i[1]) + ingots
                break
            row_index += 1

        if not found:
            await interaction.followup.send(
                f'{player} wasn\'t found.')
            return

        write_range = f'ClanIngots!B{row_index}:B{row_index}'
        body = {'values': [[new_value]]}

        try:
            _ = self._sheets_client.spreadsheets().values().update(
                spreadsheetId=self._sheet_id, range=write_range,
                valueInputOption="RAW", body=body).execute()
        except HttpError as e:
            await interaction.followup.send(
                f'Encountered error writing to sheets: {e}')
            return

        icon = ''
        for emoji in self._discord_client.get_guild(
            self._discord_client.guild.id).emojis:
            if emoji.name == 'Ingot':
                icon = emoji
        await interaction.followup.send(
            f'Added {ingots:,} ingots to {player}{icon}')

        tz = timezone('EST')
        dt = self._clock.now(tz)
        modification_timestamp = dt.strftime('%m/%d/%Y, %H:%M:%S')
        change = [[player, modification_timestamp, old_value, new_value, interaction.user.nick, '']]

        try:
            self._log_change(change)
        except HttpError as e:
            await interaction.followup.send(
                f'Encountered error in logging changes: {e}')


    async def updateingots(
        self,
        interaction: discord.Interaction,
        player: str,
        ingots: int):
        """Set ingots for a Runescape alias.

        Arguments:
            interaction: Discord Interaction from CommandTree.
            player: Runescape username to view ingot count for.
            ingots: New ingot count for this user.
        """
        # interaction.user can be a User or Member, but we can only
        # rely on permission checking for a Member.
        member = interaction.user
        if isinstance(member, discord.User):
            await interaction.response.send_message(
                f'PERMISSION_DENIED: {member.name} is not in this guild.')
            return

        if not is_admin(member):
            await interaction.response.send_message(
                f'PERMISSION_DENIED: {member.name} is not in a leadership role.')
            return

        if not validate_player_name(player):
            await interaction.response.send_message(
                'FAILED_PRECONDITION: RSNs can only be 12 characters long.')
            return

        await interaction.response.defer()
        result = {}

        try:
            result = self._sheets_client.spreadsheets().values().get(
                spreadsheetId=self._sheet_id, range=SHEET_RANGE).execute()
        except HttpError as e:
            await interaction.followup.send(
                f'Encountered error reading from sheets: {e}')
            return

        values = result.get('values', [])

        # Start at 2 since we skip header
        row_index = 2
        found = False
        old_value = 0
        for i in values:
            if i[0] == player:
                found = True
                old_value = i[1]
                break
            row_index += 1

        if not found:
            await interaction.followup.send(
                f'{player} wasn\'t found.')
            return

        write_range = f'ClanIngots!B{row_index}:B{row_index}'
        body = {'values': [[ingots]]}

        try:
            _ = self._sheets_client.spreadsheets().values().update(
                spreadsheetId=self._sheet_id, range=write_range,
                valueInputOption="RAW", body=body).execute()
        except HttpError as e:
            await interaction.followup.send(
                f'Encountered error writing to sheets: {e}')
            return

        icon = ''
        for emoji in self._discord_client.get_guild(
            self._discord_client.guild.id).emojis:
            if emoji.name == 'Ingot':
                icon = emoji
        await interaction.followup.send(
            f'Set ingot count to {ingots:,} for {player}{icon}')

        tz = timezone('EST')
        dt = self._clock.now(tz)
        modification_timestamp = dt.strftime('%m/%d/%Y, %H:%M:%S')
        change = [[player, modification_timestamp, old_value, ingots, interaction.user.nick, '']]

        try:
            self._log_change(change)
        except HttpError as e:
            await interaction.followup.send(
                f'Encountered error in logging changes: {e}')


    async def syncmembers(self, interaction: discord.Interaction):

        mutator = interaction.user
        if isinstance(mutator, discord.User):
            await interaction.response.send_message(
                f'PERMISSION_DENIED: {mutator.name} is not in this guild.')
            return

        if not is_admin(mutator):
            await interaction.response.send_message(
                f'PERMISSION_DENIED: {mutator.name} is not in a leadership role.')
            return

        await interaction.response.defer()
        # Perform a cross join between current Discord members and
        # entries in the sheet.
        # First, read all members from Discord.
        members = []
        member_ids = []
        for member in self._discord_client.get_guild(
            self._discord_client.guild.id).members:
            members.append(member)
            member_ids.append(str(member.id))

        # Then, get all current entries from sheets.
        try:
            result = self._sheets_client.spreadsheets().values().get(
                spreadsheetId=self._sheet_id,
                range=SHEET_RANGE_WITH_DISCORD_IDS).execute()
        except HttpError as e:
            await interaction.followup.send(
                f'Encountered error reading ClanIngots from sheets: {e}')
            return

        # All Changes are done in a single bulk pass.
        # Get the current timestamp once for convenience.
        tz = timezone('EST')
        dt = self._clock.now(tz)
        modification_timestamp = dt.strftime('%m/%d/%Y, %H:%M:%S')

        values = result.get('values', [])
        # Used in determining if we need to buffer response with empty rows.
        original_length = len(values)
        written_ids = [value[2] for value in values]
        # Keep track of changes in the same schema as the changeLog sheet.
        changes = []

        # Now for the actual diffing.
        # First, what new members are in Discord but not the sheet?
        # Append to the end, we'll sort before a write.
        for member in members:
            if str(member.id) not in written_ids:
                if member.nick is None:
                    continue
                values.append([member.nick, 0, str(member.id)])

                changes.append([member.nick, modification_timestamp, 0, 0, 'User Joined Server', ''])

        new_values = []
        # Okay, now for all the users who have left.
        for value in values:
            if value[2] not in member_ids:
                changes.append([value[0], modification_timestamp, value[1], 0, 'User Left Server', ''])
                continue

            new_values.append([value[0], int(value[1]), value[2]])

        # Now we have a fully cross joined set of values.
        # Update all users that have changed their RSN.
        for member in members:
            for value in new_values:
                if str(member.id) == value[2]:
                    if member.nick != value[0]:
                        changes.append(
                            [value[0], modification_timestamp, value[0], member.nick, 'Name Change',
                            ''])

                        value[0] = member.nick

        # Sort by RSN for output stability
        new_values.sort(key=lambda x: x[0])

        # We have to fill the request with empty data for the rows we want to go away
        if original_length > len(new_values):
            diff = original_length - len(new_values)
            for _ in range(diff):
                new_values.append(['', '', ''])
        buf = max(original_length, len(new_values))
        write_range = f'ClanIngots!A2:C{2 + buf}'
        body = {'values': new_values}
        try:
            _ = self._sheets_client.spreadsheets().values().update(
                spreadsheetId=self._sheet_id, range=write_range,
                valueInputOption="RAW", body=body).execute()
        except HttpError as e:
            await interaction.followup.send(
                f'Encountered error writing to sheets: {e}')
            return

        try:
            self._log_change(changes)
        except HttpError as e:
            await interaction.followup.send(
                f'Encountered error in logging changes: {e}')
            return

        await interaction.followup.send(
            'Successfully synced ingots storage with current members!')

    def _log_change(
        self, changes: List[List[Union[str, int]]]):
        """Log change to ChangeLog sheet.

        Arguments:
            changes: Values to prepend to current changelog. Expected
                format: [user, timestamp, old value, new value, mutator, note]

        Raises:
            HttpError: Any error is encountered interacting with sheets.
        """
        changelog_response = self._sheets_client.spreadsheets().values().get(
                spreadsheetId=self._sheet_id,
                range=CHANGELOG_RANGE).execute()

        # We want newest changes first
        changelog_values = changelog_response.get('values', [])
        changes.extend(changelog_values)

        change_range = f'ChangeLog!A2:F{2 + len(changes)}'
        body = {'values': changes}

        _ = self._sheets_client.spreadsheets().values().update(
            spreadsheetId=self._sheet_id, range=change_range,
            valueInputOption="RAW", body=body).execute()


def skill_score(hiscores: List[str]) -> Dict[str, int]:
    """Compute score from skills portion of hiscores response."""
    score = {}
    skills = point_values.skills()
    for i, _ in enumerate(skills):
        line = hiscores[i].split(',')
        skill = skills[i]
        experience = int(line[2])
        points = 0
        # API response returns -1 if user is not on hiscores.
        if experience >= 0:
            if experience < LEVEL_99_EXPERIENCE:
                points = int(
                    experience / point_values.pre99SkillValue().get(
                        skill, 0))
            else:
                points = int(
                    LEVEL_99_EXPERIENCE /
                    point_values.pre99SkillValue().get(skill, 0)) + int(
                    (experience - LEVEL_99_EXPERIENCE) /
                     point_values.post99SkillValue().get(skill, 0))
        score[skill] = points

    return score


def activity_score(hiscores: List[str]) -> Dict[str, int]:
    """Compute score from activities portion of hiscores response."""
    score = {}
    skills = point_values.skills()
    activities = point_values.activities()
    for i, _ in enumerate(activities):
        line = hiscores[len(skills) + i]
        count = int(line.split(',')[1])
        activity = activities[i]
        if count > 0 and point_values.activityPointValues().get(
                activity, 0) > 0:
            score[activity] = int(
                count / point_values.activityPointValues().get(activity))

    return score


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='A discord bot for Iron Forged.')
    parser.add_argument('--dotenv_path', default='./.env', required=False,
                        help='Filepath for .env with startup k/v pairs.')
    parser.add_argument(
        '--upload_commands', action='store_true',
        help='If supplied, will upload commands to discord server.')
    parser.add_argument(
        '--breakdown_tmp_dir', default='./breakdown_tmp', required=False,
        help='Directory path for where to store point break downs to upload to discord.')
    args = parser.parse_args()


    # Fail out early if our required args are not present.
    init_config = read_dotenv(args.dotenv_path)
    if not validate_initial_config(init_config):
        sys.exit(1)

    # TODO: We lock the bot down with oauth perms; can we shrink intents to match?
    intents = discord.Intents.default()
    intents.members = True
    guild = discord.Object(id=init_config.get('GUILDID'))
    client = DiscordClient(intents=intents, upload=args.upload_commands,
                           guild=guild)
    tree = discord.app_commands.CommandTree(client)


    creds = service_account.Credentials.from_service_account_file(
        'service.json', scopes=SHEETS_SCOPES)
    service = build('sheets', 'v4', credentials=creds)

    commands = IronForgedCommands(
        tree, client, service, init_config.get('SHEETID'), args.breakdown_tmp_dir)
    client.tree = tree

    client.run(init_config.get('BOT_TOKEN'))
