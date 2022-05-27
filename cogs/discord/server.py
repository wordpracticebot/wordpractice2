import discord
from discord.ext import commands

import icons
from config import SUPPORT_GUILD_ID
from helpers.checks import cooldown
from helpers.user import get_typing_average
from roles import SERVER_ROLES


class Server(commands.Cog):
    """Commands for the community server"""

    emoji = "\N{CLOUD}"
    order = 5

    def __init__(self, bot):
        self.bot = bot

    def get_role_from_id(self, roles, role_id: int):
        return discord.utils.get(roles, id=role_id)

    @cooldown(10, 3)
    @commands.slash_command(guild_ids=[SUPPORT_GUILD_ID])
    async def roles(self, ctx):
        """Update your wordPractice roles on the server"""

        if SERVER_ROLES is False:
            embed = ctx.error_embed(title=f"{icons.caution} Roles have been disabled")

            return await ctx.respond(embed=embed)

        user = await self.bot.mongo.fetch_user(ctx.author)

        if len(user.scores) == 0:
            embed = ctx.error_embed(
                title=f"{icons.caution} User does not have any scores saved",
                description="> Complete at least 1 typing test using `/tt` to update your roles.",
            )
            return await ctx.respond(embed=embed)

        word_roles = SERVER_ROLES.get("words", None)
        wpm_roles = SERVER_ROLES.get("wpm", None)

        avg_wpm = get_typing_average(user)[0]

        guild_roles = ctx.guild.roles

        roles_added = []
        roles_removed = []

        # Roles that the user has
        current_roles = {role.id: role for role in ctx.author.roles}

        # Wpm roles
        if wpm_roles is not None:
            # Getting the roles that need to be added
            role_id = next(
                (n for n, r in reversed(wpm_roles.items()) if r[0] <= avg_wpm <= r[1]),
                None,
            )

            if role_id is not None and role_id not in current_roles:
                role_obj = self.get_role_from_id(guild_roles, role_id)

                roles_added.append(role_obj)

            # Getting the roles that need to be removed
            roles_removed += [
                current_roles[r]
                for r in wpm_roles.keys()
                if r != role_id and r in current_roles
            ]

        # Word roles
        if word_roles is not None:
            for role_id, amt in word_roles.items():
                if role_id not in current_roles:
                    if user.words >= amt:
                        role_obj = self.get_role_from_id(guild_roles, role_id)

                        roles_added.append(role_obj)
                else:
                    if user.words < amt:
                        roles_removed.append(current_roles[role_id])

        if roles_added or roles_removed:
            # Adding and removing roles
            await ctx.author.add_roles(*roles_added)
            await ctx.author.remove_roles(*roles_removed)

            role_logs_added = "\n".join(f"+ {r}" for r in roles_added)
            role_logs_removed = "\n".join(f"- {r}" for r in roles_removed)

            role_logs = f"```diff\n{role_logs_added}\n{role_logs_removed}```"

        else:
            role_logs = "No roles updated"

        embed = ctx.embed(title="Roles", description=role_logs)

        await ctx.respond(embed=embed)


def setup(bot):
    bot.add_cog(Server(bot))
