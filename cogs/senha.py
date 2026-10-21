
import asyncio
import hashlib
import json
import secrets
import os
import sys
from datetime import timedelta
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands


# =========================================================
# CONFIGURAÇÃO GERAL
# =========================================================

DONO_ID = 1402833240246714408
DONO2_ID = 1398655615995351072
ARQUIVO = Path("senha_config.json")
COR = 0x6A00FF

COMANDOS = {
    "painel staff": "Painel Staff",
    "painel bot": "Painel Bot",
}


def config_padrao():
    return {
        "global": {
            "senha_dono": None,
            "protecao_dono": [],
        },
        "guilds": {},
    }


def carregar():
    if not ARQUIVO.exists():
        return config_padrao()

    try:
        with ARQUIVO.open("r", encoding="utf-8") as f:
            dados = json.load(f)

        base = config_padrao()
        base["global"].update(dados.get("global", {}))
        base["guilds"] = dados.get("guilds", {})
        return base
    except (OSError, json.JSONDecodeError):
        return config_padrao()


DADOS = carregar()


def salvar():
    temporario = ARQUIVO.with_suffix(".tmp")
    with temporario.open("w", encoding="utf-8") as f:
        json.dump(DADOS, f, indent=4, ensure_ascii=False)
    temporario.replace(ARQUIVO)


def config_guild(guild_id):
    chave = str(guild_id)

    if chave not in DADOS["guilds"]:
        DADOS["guilds"][chave] = {
            "senha_adm": None,
            "cargo_adm": None,
            "protecao_adm": [],
        }

    return DADOS["guilds"][chave]


def hash_senha(senha):
    sal = secrets.token_hex(16)
    resultado = hashlib.sha256(
        (sal + senha).encode("utf-8")
    ).hexdigest()
    return f"{sal}:{resultado}"


def validar_senha(senha, armazenada):
    if not armazenada or ":" not in armazenada:
        return False

    sal, esperado = armazenada.split(":", 1)
    recebido = hashlib.sha256(
        (sal + senha).encode("utf-8")
    ).hexdigest()

    return secrets.compare_digest(recebido, esperado)


def eh_dono_bot(interaction):
    return interaction.user.id in (DONO_ID, DONO2_ID)


def eh_dono_servidor(interaction):
    return bool(
        interaction.guild
        and interaction.guild.owner_id == interaction.user.id
    )


def tem_cargo_adm(interaction):
    if not interaction.guild:
        return False

    if eh_dono_servidor(interaction):
        return True

    if not isinstance(interaction.user, discord.Member):
        return False

    if interaction.user.guild_permissions.administrator:
        return True

    config = config_guild(interaction.guild.id)
    cargo_id = config.get("cargo_adm")

    return bool(
        cargo_id
        and any(
            cargo.id == cargo_id
            for cargo in interaction.user.roles
        )
    )


async def avisar(interaction, mensagem):
    if interaction.response.is_done():
        await interaction.followup.send(
            mensagem, ephemeral=True
        )
    else:
        await interaction.response.send_message(
            mensagem, ephemeral=True
        )


# =========================================================
# MODAIS DE SENHA
# =========================================================

class ModalSenhaAdm(discord.ui.Modal):
    def __init__(self, guild_id, continuar):
        super().__init__(title="Verificação da equipe")
        self.guild_id = guild_id
        self.continuar = continuar

        self.senha = discord.ui.TextInput(
            label="Senha ADM deste servidor",
            placeholder="Digite a senha configurada pelo dono",
            required=True,
            min_length=1,
            max_length=100,
        )
        self.add_item(self.senha)

    async def on_submit(self, interaction):
        if not interaction.guild or interaction.guild.id != self.guild_id:
            await avisar(interaction, "❌ Servidor inválido.")
            return

        config = config_guild(self.guild_id)

        if not config.get("senha_adm"):
            await avisar(
                interaction,
                "🔒 O dono deste servidor ainda não configurou a senha ADM."
            )
            return

        if not tem_cargo_adm(interaction):
            await avisar(
                interaction,
                "❌ Você não tem o cargo ou as permissões necessárias."
            )
            return

        if not validar_senha(str(self.senha), config["senha_adm"]):
            await avisar(interaction, "❌ Senha ADM incorreta.")
            return

        await self.continuar(interaction)


class ModalSenhaDono(discord.ui.Modal):
    def __init__(self, continuar):
        super().__init__(title="Verificação do criador")
        self.continuar = continuar

        self.senha = discord.ui.TextInput(
            label="Senha de dono",
            placeholder="Senha exclusiva do criador do bot",
            required=True,
            min_length=1,
            max_length=100,
        )
        self.add_item(self.senha)

    async def on_submit(self, interaction):
        if not eh_dono_bot(interaction):
            await avisar(interaction, "❌ Acesso exclusivo do criador.")
            return

        armazenada = DADOS["global"].get("senha_dono")

        if not validar_senha(str(self.senha), armazenada):
            await avisar(interaction, "❌ Senha de dono incorreta.")
            return

        await self.continuar(interaction)


# =========================================================
# CONFIGURAÇÃO DA SENHA ADM POR SERVIDOR
# =========================================================

class ModalConfigAdm(discord.ui.Modal):
    def __init__(self, guild_id):
        super().__init__(title="Configurar senha ADM")
        self.guild_id = guild_id

        self.senha = discord.ui.TextInput(
            label="Nova senha ADM",
            placeholder="Use uma senha diferente da de outros servidores",
            min_length=4,
            max_length=100,
            required=True,
        )
        self.add_item(self.senha)

    async def on_submit(self, interaction):
        if not interaction.guild or interaction.guild.id != self.guild_id:
            await avisar(interaction, "❌ Servidor inválido.")
            return

        if not eh_dono_servidor(interaction):
            await avisar(
                interaction,
                "❌ Somente o dono deste servidor pode configurar a senha ADM."
            )
            return

        config = config_guild(self.guild_id)
        config["senha_adm"] = hash_senha(str(self.senha))
        salvar()

        await interaction.response.send_message(
            "✅ Senha ADM configurada para este servidor.",
            ephemeral=True,
        )


class SeletorCargoAdm(discord.ui.RoleSelect):
    def __init__(self, guild_id):
        super().__init__(
            placeholder="Selecione o cargo de staff",
            min_values=1,
            max_values=1,
        )
        self.guild_id = guild_id

    async def callback(self, interaction):
        if not interaction.guild or interaction.guild.id != self.guild_id:
            await avisar(interaction, "❌ Servidor inválido.")
            return

        if not eh_dono_servidor(interaction):
            await avisar(
                interaction,
                "❌ Somente o dono do servidor pode escolher o cargo."
            )
            return

        cargo = self.values[0]
        config = config_guild(self.guild_id)
        config["cargo_adm"] = cargo.id
        salvar()

        await interaction.response.send_message(
            f"✅ Cargo de staff definido: {cargo.mention}",
            ephemeral=True,
        )


class SeletorProtecaoAdm(discord.ui.Select):
    def __init__(self, guild_id):
        self.guild_id = guild_id
        config = config_guild(guild_id)

        opcoes = [
            discord.SelectOption(
                label=nome,
                value=nome_comando,
                default=nome_comando in config["protecao_adm"],
            )
            for nome_comando, nome in COMANDOS.items()
            if nome_comando == "painel staff"
        ]

        super().__init__(
            placeholder="Escolha os comandos com senha ADM",
            min_values=0,
            max_values=len(opcoes),
            options=opcoes,
        )

    async def callback(self, interaction):
        if not interaction.guild or interaction.guild.id != self.guild_id:
            await avisar(interaction, "❌ Servidor inválido.")
            return

        if not eh_dono_servidor(interaction):
            await avisar(interaction, "❌ Apenas o dono pode alterar isso.")
            return

        config = config_guild(self.guild_id)
        config["protecao_adm"] = list(self.values)
        salvar()

        await interaction.response.send_message(
            "✅ Proteções ADM atualizadas.",
            ephemeral=True,
        )


class SeletorProtecaoDono(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Comandos que exigem senha de dono",
            min_values=0,
            max_values=len(COMANDOS),
            options=[
                discord.SelectOption(
                    label=nome,
                    value=chave,
                    default=chave in DADOS["global"]["protecao_dono"],
                )
                for chave, nome in COMANDOS.items()
            ],
        )

    async def callback(self, interaction):
        if not eh_dono_bot(interaction):
            await avisar(interaction, "❌ Apenas o criador pode alterar isso.")
            return

        DADOS["global"]["protecao_dono"] = list(self.values)
        salvar()

        await interaction.response.send_message(
            "✅ Proteções de dono atualizadas.",
            ephemeral=True,
        )


class ModalConfigDono(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Configurar senha de dono")

        self.senha = discord.ui.TextInput(
            label="Nova senha de dono",
            placeholder="Somente o criador pode configurar",
            min_length=4,
            max_length=100,
            required=True,
        )
        self.add_item(self.senha)

    async def on_submit(self, interaction):
        if not eh_dono_bot(interaction):
            await avisar(interaction, "❌ Apenas o criador pode configurar isso.")
            return

        DADOS["global"]["senha_dono"] = hash_senha(str(self.senha))
        salvar()

        await interaction.response.send_message(
            "✅ Senha de dono configurada.",
            ephemeral=True,
        )


# =========================================================
# MENU /SENHA
# =========================================================

class ViewSenha(discord.ui.View):
    def __init__(self, guild_id, mostrar_dono):
        super().__init__(timeout=180)
        self.guild_id = guild_id

        if mostrar_dono:
            self.add_item(BotaoConfigDono())
            self.add_item(BotaoProtecaoDono())

        self.add_item(BotaoConfigAdm(guild_id))
        self.add_item(BotaoCargoAdm(guild_id))
        self.add_item(BotaoProtecaoAdm(guild_id))


class BotaoConfigDono(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Configurar senha de dono",
            style=discord.ButtonStyle.danger,
        )

    async def callback(self, interaction):
        if not eh_dono_bot(interaction):
            await avisar(interaction, "❌ Acesso exclusivo do criador.")
            return

        await interaction.response.send_modal(ModalConfigDono())


class BotaoProtecaoDono(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Proteção de dono",
            style=discord.ButtonStyle.danger,
        )

    async def callback(self, interaction):
        if not eh_dono_bot(interaction):
            await avisar(interaction, "❌ Acesso exclusivo do criador.")
            return

        view = discord.ui.View(timeout=120)
        view.add_item(SeletorProtecaoDono())

        await interaction.response.send_message(
            "Escolha os comandos que exigirão a senha de dono:",
            view=view,
            ephemeral=True,
        )


class BotaoConfigAdm(discord.ui.Button):
    def __init__(self, guild_id):
        super().__init__(
            label="Configurar senha ADM",
            style=discord.ButtonStyle.primary,
        )
        self.guild_id = guild_id

    async def callback(self, interaction):
        if not eh_dono_servidor(interaction):
            await avisar(
                interaction,
                "❌ Somente o dono do servidor pode configurar a senha ADM."
            )
            return

        await interaction.response.send_modal(
            ModalConfigAdm(self.guild_id)
        )


class BotaoCargoAdm(discord.ui.Button):
    def __init__(self, guild_id):
        super().__init__(
            label="Definir cargo de staff",
            style=discord.ButtonStyle.secondary,
        )
        self.guild_id = guild_id

    async def callback(self, interaction):
        if not eh_dono_servidor(interaction):
            await avisar(interaction, "❌ Apenas o dono do servidor.")
            return

        view = discord.ui.View(timeout=120)
        view.add_item(SeletorCargoAdm(self.guild_id))

        await interaction.response.send_message(
            "Selecione o cargo que poderá usar o painel staff:",
            view=view,
            ephemeral=True,
        )


class BotaoProtecaoAdm(discord.ui.Button):
    def __init__(self, guild_id):
        super().__init__(
            label="Proteção ADM",
            style=discord.ButtonStyle.success,
        )
        self.guild_id = guild_id

    async def callback(self, interaction):
        if not eh_dono_servidor(interaction):
            await avisar(interaction, "❌ Apenas o dono do servidor.")
            return

        config = config_guild(self.guild_id)
        if not config.get("senha_adm"):
            await avisar(
                interaction,
                "Configure a senha ADM antes de definir as proteções."
            )
            return

        view = discord.ui.View(timeout=120)
        view.add_item(SeletorProtecaoAdm(self.guild_id))

        await interaction.response.send_message(
            "Escolha os comandos protegidos pela senha ADM:",
            view=view,
            ephemeral=True,
        )


# =========================================================
# MODERAÇÃO
# =========================================================

def duracao(texto):
    texto = texto.strip().lower()

    if texto == "perm":
        return None

    if len(texto) < 2:
        raise ValueError("Use 30s, 10m, 2h ou perm.")

    unidade = texto[-1]
    numero = int(texto[:-1])

    if numero <= 0:
        raise ValueError("A duração deve ser maior que zero.")

    fatores = {"s": 1, "m": 60, "h": 3600}
    if unidade not in fatores:
        raise ValueError("Unidades válidas: s, m, h ou perm.")

    segundos = numero * fatores[unidade]
    if segundos > 365 * 86400:
        raise ValueError("A duração máxima é de 365 dias.")

    return segundos


class ModalBan(discord.ui.Modal):
    def __init__(self, membro):
        super().__init__(title="Banir membro")
        self.membro = membro

        self.tempo = discord.ui.TextInput(
            label="Duração",
            placeholder="30s, 10m, 2h ou perm",
            required=True,
            max_length=20,
        )
        self.motivo = discord.ui.TextInput(
            label="Motivo (opcional)",
            required=False,
            max_length=300,
        )
        self.add_item(self.tempo)
        self.add_item(self.motivo)

    async def on_submit(self, interaction):
        if not tem_cargo_adm(interaction):
            await avisar(interaction, "❌ Sem permissão.")
            return

        membro = self.membro
        guild = interaction.guild

        if not guild or membro.id in (DONO_ID, guild.owner_id):
            await avisar(interaction, "❌ Não é permitido banir esse membro.")
            return

        if not eh_dono_bot(interaction):
            if (
                not isinstance(interaction.user, discord.Member)
                or membro.top_role >= interaction.user.top_role
            ):
                await avisar(interaction, "❌ Seu cargo não está acima do membro.")
                return

        try:
            segundos = duracao(str(self.tempo))
        except (ValueError, TypeError) as erro:
            await avisar(interaction, f"❌ {erro}")
            return

        motivo = str(self.motivo).strip() or "Sem motivo informado"

        try:
            await guild.ban(
                membro,
                reason=motivo,
                delete_message_seconds=0,
            )

            if segundos is not None:
                async def desbanir():
                    await asyncio.sleep(segundos)
                    try:
                        await guild.unban(
                            discord.Object(id=membro.id),
                            reason="Fim do banimento temporário",
                        )
                    except discord.HTTPException:
                        pass

                asyncio.create_task(desbanir())

            await interaction.response.send_message(
                f"✅ Banimento aplicado em **{membro}**.",
                ephemeral=True,
            )
        except discord.Forbidden:
            await avisar(interaction, "❌ Não tenho permissão para banir.")
        except discord.HTTPException:
            await avisar(interaction, "❌ O Discord não conseguiu aplicar o banimento.")


class ModalCastigo(discord.ui.Modal):
    def __init__(self, membro):
        super().__init__(title="Aplicar castigo")
        self.membro = membro

        self.tempo = discord.ui.TextInput(
            label="Duração",
            placeholder="10m, 2h ou 1d",
            required=True,
            max_length=20,
        )
        self.motivo = discord.ui.TextInput(
            label="Motivo (opcional)",
            required=False,
            max_length=300,
        )
        self.add_item(self.tempo)
        self.add_item(self.motivo)

    async def on_submit(self, interaction):
        if not tem_cargo_adm(interaction):
            await avisar(interaction, "❌ Sem permissão.")
            return

        texto = str(self.tempo).strip().lower()

        try:
            if texto.endswith("d"):
                segundos = int(texto[:-1]) * 86400
            else:
                segundos = duracao(texto)

            if segundos is None or segundos <= 0 or segundos > 28 * 86400:
                raise ValueError("O castigo deve durar até 28 dias.")

            membro = self.membro
            guild = interaction.guild

            if not guild or membro.id == guild.owner_id:
                await avisar(interaction, "❌ Não é possível castigar esse membro.")
                return

            if not eh_dono_bot(interaction):
                if (
                    not isinstance(interaction.user, discord.Member)
                    or membro.top_role >= interaction.user.top_role
                ):
                    await avisar(interaction, "❌ Seu cargo não está acima do membro.")
                    return

            await membro.timeout(
                discord.utils.utcnow() + timedelta(seconds=segundos),
                reason=str(self.motivo).strip() or "Sem motivo informado",
            )

            await interaction.response.send_message(
                f"✅ Castigo aplicado em {membro.mention}.",
                ephemeral=True,
            )
        except (ValueError, TypeError) as erro:
            await avisar(interaction, f"❌ {erro}")
        except discord.Forbidden:
            await avisar(interaction, "❌ Não tenho permissão para aplicar castigo.")
        except discord.HTTPException:
            await avisar(interaction, "❌ Não consegui aplicar o castigo.")


class ModalAviso(discord.ui.Modal):
    def __init__(self, membro):
        super().__init__(title="Aviso por mensagem privada")
        self.membro = membro

        self.texto = discord.ui.TextInput(
            label="Mensagem",
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=True,
        )
        self.add_item(self.texto)

    async def on_submit(self, interaction):
        if not tem_cargo_adm(interaction):
            await avisar(interaction, "❌ Sem permissão.")
            return

        embed = discord.Embed(
            title="⚠️ Aviso da equipe",
            description=str(self.texto),
            color=COR,
        )

        if interaction.guild:
            embed.set_footer(text=interaction.guild.name)

        try:
            await self.membro.send(embed=embed)
            await interaction.response.send_message(
                f"✅ Aviso enviado para {self.membro.mention}.",
                ephemeral=True,
            )
        except discord.Forbidden:
            await avisar(
                interaction,
                "❌ Não consegui enviar DM. O membro pode ter fechado as mensagens privadas."
            )
        except discord.HTTPException:
            await avisar(interaction, "❌ Falha ao enviar o aviso.")


class SeletorCargoMembro(discord.ui.RoleSelect):
    def __init__(self, membro, acao):
        super().__init__(
            placeholder="Escolha um cargo",
            min_values=1,
            max_values=1,
        )
        self.membro = membro
        self.acao = acao

    async def callback(self, interaction):
        if not tem_cargo_adm(interaction):
            await avisar(interaction, "❌ Sem permissão.")
            return

        cargo = self.values[0]
        guild = interaction.guild

        if not guild or cargo.is_default() or cargo.managed:
            await avisar(interaction, "❌ Esse cargo não pode ser alterado.")
            return

        if not eh_dono_bot(interaction):
            if (
                not isinstance(interaction.user, discord.Member)
                or cargo >= interaction.user.top_role
            ):
                await avisar(interaction, "❌ Seu cargo precisa estar acima do cargo escolhido.")
                return

        try:
            if self.acao == "adicionar":
                await self.membro.add_roles(
                    cargo, reason=f"Alteração por {interaction.user}"
                )
                mensagem = f"✅ Cargo {cargo.mention} adicionado."
            else:
                await self.membro.remove_roles(
                    cargo, reason=f"Alteração por {interaction.user}"
                )
                mensagem = f"✅ Cargo {cargo.mention} removido."

            await interaction.response.send_message(
                mensagem, ephemeral=True
            )
        except discord.Forbidden:
            await avisar(interaction, "❌ Não tenho permissão para alterar esse cargo.")
        except discord.HTTPException:
            await avisar(interaction, "❌ Não consegui alterar o cargo.")


class ViewCargos(discord.ui.View):
    def __init__(self, membro):
        super().__init__(timeout=120)
        self.membro = membro

    @discord.ui.button(label="Adicionar cargo", style=discord.ButtonStyle.success)
    async def adicionar(self, interaction, button):
        view = discord.ui.View(timeout=120)
        view.add_item(SeletorCargoMembro(self.membro, "adicionar"))
        await interaction.response.send_message(
            "Escolha o cargo para adicionar:",
            view=view,
            ephemeral=True,
        )

    @discord.ui.button(label="Remover cargo", style=discord.ButtonStyle.danger)
    async def remover(self, interaction, button):
        view = discord.ui.View(timeout=120)
        view.add_item(SeletorCargoMembro(self.membro, "remover"))
        await interaction.response.send_message(
            "Escolha o cargo para remover:",
            view=view,
            ephemeral=True,
        )


class ViewStaff(discord.ui.View):
    def __init__(self, membro):
        super().__init__(timeout=180)
        self.membro = membro

    async def verificar(self, interaction):
        if not tem_cargo_adm(interaction):
            await avisar(interaction, "❌ Você não tem permissão.")
            return False
        return True

    @discord.ui.button(label="Banir", style=discord.ButtonStyle.danger)
    async def banir(self, interaction, button):
        if await self.verificar(interaction):
            await interaction.response.send_modal(ModalBan(self.membro))

    @discord.ui.button(label="Expulsar", style=discord.ButtonStyle.danger)
    async def expulsar(self, interaction, button):
        if not await self.verificar(interaction):
            return

        guild = interaction.guild
        membro = self.membro

        if not guild or membro.id in (DONO_ID, guild.owner_id):
            await avisar(interaction, "❌ Não é permitido expulsar esse membro.")
            return

        if not eh_dono_bot(interaction):
            if (
                not isinstance(interaction.user, discord.Member)
                or membro.top_role >= interaction.user.top_role
            ):
                await avisar(interaction, "❌ Seu cargo não está acima do membro.")
                return

        try:
            await membro.kick(reason=f"Expulsão por {interaction.user}")
            await interaction.response.send_message(
                f"✅ {membro} foi expulso.",
                ephemeral=True,
            )
        except discord.Forbidden:
            await avisar(interaction, "❌ Não tenho permissão para expulsar.")
        except discord.HTTPException:
            await avisar(interaction, "❌ Não consegui expulsar.")

    @discord.ui.button(label="Castigo", style=discord.ButtonStyle.secondary)
    async def castigo(self, interaction, button):
        if await self.verificar(interaction):
            await interaction.response.send_modal(ModalCastigo(self.membro))

    @discord.ui.button(label="Aviso", style=discord.ButtonStyle.primary)
    async def aviso(self, interaction, button):
        if await self.verificar(interaction):
            await interaction.response.send_modal(ModalAviso(self.membro))

    @discord.ui.button(label="Cargos", style=discord.ButtonStyle.success)
    async def cargos(self, interaction, button):
        if not await self.verificar(interaction):
            return

        cargos = [
            cargo.mention
            for cargo in self.membro.roles
            if not cargo.is_default()
        ]

        embed = discord.Embed(
            title=f"Cargos de {self.membro.display_name}",
            description="\n".join(cargos) if cargos else "Nenhum cargo.",
            color=COR,
        )

        await interaction.response.send_message(
            embed=embed,
            view=ViewCargos(self.membro),
            ephemeral=True,
        )


# =========================================================
# CONFIRMAÇÃO DE REINÍCIO — EXCLUSIVA DO CRIADOR
# =========================================================

class ConfirmarReinicioView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)

    async def interaction_check(self, interaction):
        if not eh_dono_bot(interaction):
            await avisar(
                interaction,
                "❌ Apenas o criador do Zyrenn Bot pode reiniciá-lo."
            )
            return False

        return True

    @discord.ui.button(
        label="Confirmar reinício",
        emoji="🔄",
        style=discord.ButtonStyle.danger,
    )
    async def confirmar(self, interaction, button):
        if not eh_dono_bot(interaction):
            await avisar(
                interaction,
                "❌ Apenas o criador do Zyrenn Bot pode reiniciá-lo."
            )
            return

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(
            content="🔄 Reiniciando o Zyrenn Bot...",
            view=self,
        )

        await asyncio.sleep(2)

        try:
            # Localiza a pasta do projeto usando este arquivo.
            pasta_bot = Path(__file__).resolve().parent.parent
            arquivo_principal = pasta_bot / "main.py"
            print("ARQUIVO PRINCIPAL:", arquivo_principal)
            print("PYTHON:", sys.executable)    

            if not arquivo_principal.is_file():
                raise FileNotFoundError(
                    f"Não encontrei o arquivo: {arquivo_principal}"
                )

            # Reinicia o main.py pelo caminho absoluto.
            import subprocess

            subprocess.Popen(
                [sys.executable, str(arquivo_principal)],
                cwd=str(pasta_bot),
                shell=False,
            )

            await interaction.followup.send(
                "✅ Novo processo iniciado. Verifique se o bot voltou.",
                ephemeral=True,
            )

            await interaction.client.close()

        except Exception as erro:
            try:
                await interaction.followup.send(
                    f"❌ Não consegui reiniciar o bot:\n"
                    f"`{type(erro).__name__}: {erro}`",
                    ephemeral=True,
                )
            except discord.HTTPException:
                pass


    @discord.ui.button(
        label="Cancelar",
        emoji="❌",
        style=discord.ButtonStyle.secondary,
    )
    async def cancelar(self, interaction, button):
        await interaction.response.edit_message(
            content="✅ Reinício cancelado.",
            view=None,
        )
        self.stop()


# =========================================================
# PAINEL DO BOT — EXCLUSIVO DO CRIADOR
# =========================================================

class SeletorCog(discord.ui.Select):
    def __init__(self, extensoes, acao):
        self.acao = acao

        opcoes = [
            discord.SelectOption(label=nome, value=nome)
            for nome in extensoes[:25]
        ]

        super().__init__(
            placeholder="Selecione um cog",
            min_values=1,
            max_values=1,
            options=opcoes,
        )

    async def callback(self, interaction):
        if not eh_dono_bot(interaction):
            await avisar(interaction, "❌ Apenas o criador.")
            return

        nome = self.values[0]
        caminho = f"cogs.{nome}"

        try:
            if self.acao == "recarregar":
                await interaction.client.reload_extension(caminho)
                mensagem = f"✅ `{caminho}` recarregado."
            elif self.acao == "descarregar":
                if nome == "senha":
                    await avisar(
                        interaction,
                        "❌ Não é permitido descarregar o cog senha por este painel."
                    )
                    return
                await interaction.client.unload_extension(caminho)
                mensagem = f"✅ `{caminho}` descarregado."
            else:
                await interaction.client.load_extension(caminho)
                mensagem = f"✅ `{caminho}` carregado."

            await interaction.response.send_message(
                mensagem, ephemeral=True
            )
        except Exception as erro:
            await avisar(
                interaction,
                f"❌ Erro: {type(erro).__name__}: {erro}"
            )


class ViewBot(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="Informações", style=discord.ButtonStyle.primary)
    async def info(self, interaction, button):
        if not eh_dono_bot(interaction):
            await avisar(interaction, "❌ Apenas o criador.")
            return

        bot = interaction.client
        embed = discord.Embed(
            title="⚙️ Zyrenn Bot — Informações",
            color=COR,
        )
        embed.add_field(name="Nome", value=bot.user.name, inline=True)
        embed.add_field(name="Servidores", value=str(len(bot.guilds)), inline=True)
        embed.add_field(name="Cogs carregados", value=str(len(bot.extensions)), inline=True)
        embed.add_field(name="Comandos slash", value=str(len(bot.tree.get_commands())), inline=True)
        embed.add_field(name="Latência", value=f"{round(bot.latency * 1000)} ms", inline=True)
        embed.add_field(name="Versão", value="v5.0 — Python/Discord.py", inline=True)

        await interaction.response.send_message(
            embed=embed, ephemeral=True
        )

    @discord.ui.button(label="Sincronizar comandos", style=discord.ButtonStyle.secondary)
    async def sincronizar(self, interaction, button):
        if not eh_dono_bot(interaction):
            await avisar(interaction, "❌ Apenas o criador.")
            return

        try:
            comandos = await interaction.client.tree.sync()
            await interaction.response.send_message(
                f"✅ {len(comandos)} comandos principais sincronizados.",
                ephemeral=True,
            )
        except Exception as erro:
            await avisar(interaction, f"❌ Erro ao sincronizar: {erro}")

    @discord.ui.button(label="Listar cogs", style=discord.ButtonStyle.secondary)
    async def listar(self, interaction, button):
        if not eh_dono_bot(interaction):
            await avisar(interaction, "❌ Apenas o criador.")
            return

        nomes = sorted(
            nome.removeprefix("cogs.")
            for nome in interaction.client.extensions
        )

        embed = discord.Embed(
            title="📦 Cogs carregados",
            description="\n".join(f"• `{nome}`" for nome in nomes) or "Nenhum cog.",
            color=COR,
        )
        await interaction.response.send_message(
            embed=embed, ephemeral=True
        )

    async def abrir_seletor(self, interaction, acao):
        if not eh_dono_bot(interaction):
            await avisar(interaction, "❌ Apenas o criador.")
            return

        nomes = sorted(
            nome.removeprefix("cogs.")
            for nome in interaction.client.extensions
            if nome.startswith("cogs.")
        )

        if acao == "carregar":
            pasta = Path("cogs")
            existentes = {
                nome.removeprefix("cogs.")
                for nome in interaction.client.extensions
            }
            nomes = sorted(
                arquivo.stem
                for arquivo in pasta.glob("*.py")
                if not arquivo.stem.startswith("_")
                and arquivo.stem not in existentes
            )

        if acao == "descarregar":
            nomes = [nome for nome in nomes if nome != "senha"]

        if not nomes:
            await avisar(interaction, "Nenhum cog disponível para essa ação.")
            return

        view = discord.ui.View(timeout=120)
        view.add_item(SeletorCog(nomes, acao))

        await interaction.response.send_message(
            f"Selecione o cog que deseja {acao}:",
            view=view,
            ephemeral=True,
        )

    @discord.ui.button(label="Recarregar cog", style=discord.ButtonStyle.success)
    async def recarregar(self, interaction, button):
        await self.abrir_seletor(interaction, "recarregar")

    @discord.ui.button(label="Carregar cog", style=discord.ButtonStyle.success)
    async def carregar(self, interaction, button):
        await self.abrir_seletor(interaction, "carregar")

    @discord.ui.button(label="Descarregar cog", style=discord.ButtonStyle.danger)
    async def descarregar(self, interaction, button):
        await self.abrir_seletor(interaction, "descarregar")

    @discord.ui.button(label="Ver servidores", style=discord.ButtonStyle.secondary)
    async def servidores(self, interaction, button):
        if not eh_dono_bot(interaction):
            await avisar(interaction, "❌ Apenas o criador.")
            return

        nomes = [
            f"• {guild.name} — `{guild.id}`"
            for guild in interaction.client.guilds
        ]

        texto = "\n".join(nomes) or "Nenhum servidor conectado."
        if len(texto) > 4000:
            texto = texto[:3900] + "\n… lista cortada."

        embed = discord.Embed(
            title="🌐 Servidores conectados",
            description=texto,
            color=COR,
        )
        await interaction.response.send_message(
            embed=embed, ephemeral=True
        )

    # -----------------------------------------------------
    # NOVO BOTÃO: REINICIAR BOT
    # -----------------------------------------------------

    @discord.ui.button(
        label="Reiniciar bot",
        emoji="🔄",
        style=discord.ButtonStyle.danger,
        row=4,
    )
    async def reiniciar_bot(self, interaction, button):
        if not eh_dono_bot(interaction):
            await avisar(
                interaction,
                "❌ Apenas o criador do Zyrenn Bot pode reiniciá-lo."
            )
            return

        await interaction.response.send_message(
            "⚠️ **Deseja realmente reiniciar o Zyrenn Bot?**\n\n"
            "O bot ficará temporariamente offline enquanto o processo reinicia.",
            view=ConfirmarReinicioView(),
            ephemeral=True,
        )


# =========================================================
# COG E GRUPO /PAINEL
# =========================================================

class Senha(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="senha",
        description="Configurar senhas e proteções deste servidor",
    )
    async def senha(self, interaction: discord.Interaction):
        if not interaction.guild:
            await avisar(interaction, "Use este comando dentro de um servidor.")
            return

        if not (
            eh_dono_servidor(interaction)
            or eh_dono_bot(interaction)
        ):
            await avisar(
                interaction,
                "❌ Somente o dono deste servidor pode configurar as senhas."
            )
            return

        embed = discord.Embed(
            title="🔐 Configurações de segurança",
            description=(
                "As configurações ADM pertencem a este servidor.\n"
                "A senha de dono pertence ao criador do bot.\n\n"
                "• Configure a senha ADM.\n"
                "• Escolha o cargo da equipe.\n"
                "• Selecione os comandos protegidos."
            ),
            color=COR,
        )

        await interaction.response.send_message(
            embed=embed,
            view=ViewSenha(
                interaction.guild.id,
                mostrar_dono=eh_dono_bot(interaction),
            ),
            ephemeral=True,
        )

    painel = app_commands.Group(
        name="painel",
        description="Painéis de administração do Zyrenn Bot",
    )

    @painel.command(
        name="staff",
        description="Abrir o painel de moderação de um membro",
    )
    @app_commands.describe(membro="Membro que será moderado")
    async def painel_staff(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
    ):
        if not interaction.guild:
            await avisar(interaction, "Use este comando dentro de um servidor.")
            return

        config = config_guild(interaction.guild.id)

        if not config.get("senha_adm"):
            await avisar(
                interaction,
                "🔒 O dono deste servidor ainda não configurou a senha ADM."
            )
            return

        if not tem_cargo_adm(interaction):
            await avisar(
                interaction,
                "❌ Você precisa ser administrador ou possuir o cargo de staff configurado."
            )
            return

        async def abrir(inter):
            embed = discord.Embed(
                title="🛡️ Painel Staff",
                description=(
                    f"**Membro:** {membro.mention}\n"
                    "Selecione a ação que deseja realizar."
                ),
                color=COR,
            )
            embed.set_thumbnail(url=membro.display_avatar.url)

            await inter.response.send_message(
                embed=embed,
                view=ViewStaff(membro),
                ephemeral=True,
            )

        await interaction.response.send_modal(
            ModalSenhaAdm(interaction.guild.id, abrir)
        )

    @painel.command(
        name="bot",
        description="Abrir o painel avançado do criador do bot",
    )
    async def painel_bot(self, interaction: discord.Interaction):
        if not eh_dono_bot(interaction):
            await avisar(
                interaction,
                "❌ Este painel é exclusivo do criador do Zyrenn Bot."
            )
            return

        async def abrir(inter):
            embed = discord.Embed(
                title="⚙️ Zyrenn Bot — Painel do Criador",
                description=(
                    "Ferramentas administrativas do bot.\n\n"
                    "• Informações e latência\n"
                    "• Sincronização de comandos\n"
                    "• Listagem de servidores\n"
                    "• Carregar, recarregar e descarregar cogs\n"
                    "• Reiniciar o bot com confirmação\n\n"
                    "Use as ferramentas de manutenção com cuidado."
                ),
                color=COR,
            )

            await inter.response.send_message(
                embed=embed,
                view=ViewBot(),
                ephemeral=True,
            )

        if "painel bot" in DADOS["global"]["protecao_dono"]:
            if not DADOS["global"].get("senha_dono"):
                await avisar(
                    interaction,
                    "Configure a senha de dono antes de usar este painel."
                )
                return

            await interaction.response.send_modal(
                ModalSenhaDono(abrir)
            )
        else:
            await abrir(interaction)


async def setup(bot):
    await bot.add_cog(Senha(bot))
