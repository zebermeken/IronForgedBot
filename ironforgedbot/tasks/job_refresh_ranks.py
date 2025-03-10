import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone

import discord

from ironforgedbot.commands.hiscore.calculator import (
    HiscoresError,
    HiscoresNotFound,
    get_player_points_total,
)
from ironforgedbot.common.helpers import find_emoji
from ironforgedbot.common.ranks import (
    GOD_ALIGNMENT,
    RANK,
    get_rank_from_member,
    get_rank_from_points,
)
from ironforgedbot.common.roles import ROLE, check_member_has_role
from ironforgedbot.common.text_formatters import text_bold
from ironforgedbot.http import HttpException
from ironforgedbot.storage.sheets import STORAGE

logger = logging.getLogger(__name__)

PROBATION_DAYS = 14


async def _sleep():
    sleep = round(random.uniform(0.2, 1.5), 2)
    logger.info(f"...sleeping {sleep}s")
    await asyncio.sleep(sleep)


async def job_refresh_ranks(guild: discord.Guild, report_channel: discord.TextChannel):
    progress_message = await report_channel.send(
        f"Rank check progress: [0/{guild.member_count}]"
    )

    for index, member in enumerate(guild.members):
        if index > 0:
            await _sleep()

        logger.info(f"Processing member: {member.display_name}")

        await progress_message.edit(
            content=f"Rank check progress: [{index + 1}/{guild.member_count}]"
        )

        if (
            member.bot
            or check_member_has_role(member, ROLE.APPLICANT)
            or check_member_has_role(member, ROLE.GUEST)
        ):
            logger.info("...ignoring bot/applicant/guest")
            continue

        if member.nick is None or len(member.nick) < 1:
            logger.info("...has no nickname")
            message = f"{member.mention} has no nickname set, ignoring..."
            await report_channel.send(message)
            continue

        current_rank = get_rank_from_member(member)

        if current_rank in GOD_ALIGNMENT:
            logger.info("...has God alignment")
            continue

        if current_rank == RANK.GOD:
            logger.info("...has God role but no alignment")
            message = f"{member.mention} has {find_emoji(None, current_rank)} God rank but no alignment."
            await report_channel.send(message)
            continue

        current_points = 0
        try:
            current_points = await get_player_points_total(member.display_name)
        except HttpException as e:
            await report_channel.send(
                f"HttpException getting points for {member.mention}.\n> {e}"
            )
            continue
        except HiscoresError:
            await report_channel.send(
                f"Unhandled error getting points for {member.mention}."
            )
            continue
        except HiscoresNotFound:
            current_points = 0
            if (
                not check_member_has_role(member, ROLE.PROSPECT)
                and current_rank != RANK.IRON
            ):
                logger.info("...suspected name change or ban")
                await report_channel.send(
                    f"{member.mention} has no presence on the hiscores. This member has either "
                    "changed their rsn, or been banned."
                )
                continue

        correct_rank = get_rank_from_points(current_points)

        if check_member_has_role(member, ROLE.PROSPECT):
            storage_member = await STORAGE.read_member(member.display_name)

            if not storage_member:
                logger.info("...not found in storage")
                await report_channel.send(f"{member.mention} not found in storage.")
                continue

            if not isinstance(storage_member.joined_date, datetime):
                logger.info("...has invalid join date")
                await report_channel.send(
                    f"{member.mention} is a {text_bold(ROLE.PROSPECT)} with an invalid join date."
                )
                continue

            if datetime.now(timezone.utc) >= storage_member.joined_date + timedelta(
                days=PROBATION_DAYS
            ):
                logger.info("...completed probation")
                await report_channel.send(
                    f"{member.mention} has completed their {text_bold(f'{PROBATION_DAYS} day')} probation period and "
                    f"is now eligible for {find_emoji(None,correct_rank)} {text_bold(correct_rank)} rank."
                )
                continue

            logger.info("...still on probation")
            continue

        if current_rank is None:
            logger.info("...has no rank set")
            await report_channel.send(
                f"{member.mention} detected without any rank. Should have "
                f"{find_emoji(None,correct_rank)} {text_bold(correct_rank)}."
            )
            continue

        if current_rank != str(correct_rank):
            logger.info("...needs upgrading")
            message = (
                f"{member.mention} needs upgrading {find_emoji(None, current_rank)} "
                f"→ {find_emoji(None, correct_rank)} ({text_bold(f"{current_points:,}")} points)"
            )
            await report_channel.send(message)
            continue

        logger.info("...no change")

    logger.info("Rank check completed")
    await report_channel.send(
        f"Finished rank check: [{guild.member_count}/{guild.member_count}]"
    )
