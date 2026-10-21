import json
import os
import random
import re

from ai.gerador import GeradorZyrenn


MEMORIA_FILE = "memoria_zyrenn.json"


class ZyrennAI:

    def __init__(self):

        self.memoria = self.carregar_memoria()

        self.gerador = GeradorZyrenn()

        self.personalidade = {
            "nome": "Zyrenn AI",
            "estilo": [
                "brasileiro",
                "engraçado",
                "irônico",
                "amigável",
                "descontraído"
            ]
        }

    # ==========================================
    # CARREGAR MEMÓRIA
    # ==========================================

    def carregar_memoria(self):

        if not os.path.exists(MEMORIA_FILE):

            return {
                "usuarios": {},
                "canais": {}
            }

        try:

            with open(
                MEMORIA_FILE,
                "r",
                encoding="utf-8"
            ) as arquivo:

                dados = json.load(arquivo)

                if not isinstance(dados, dict):

                    return {
                        "usuarios": {},
                        "canais": {}
                    }

                dados.setdefault(
                    "usuarios",
                    {}
                )

                dados.setdefault(
                    "canais",
                    {}
                )

                return dados

        except (
            json.JSONDecodeError,
            OSError
        ):

            return {
                "usuarios": {},
                "canais": {}
            }

    # ==========================================
    # SALVAR MEMÓRIA
    # ==========================================

    def salvar_memoria(self):

        with open(
            MEMORIA_FILE,
            "w",
            encoding="utf-8"
        ) as arquivo:

            json.dump(
                self.memoria,
                arquivo,
                ensure_ascii=False,
                indent=4
            )

    # ==========================================
    # PREPARAR USUÁRIO
    # ==========================================

    def preparar_usuario(
        self,
        usuario_id,
        nome_usuario
    ):

        usuario_id = str(
            usuario_id
        )

        if usuario_id not in self.memoria["usuarios"]:

            self.memoria["usuarios"][usuario_id] = {
                "nome": nome_usuario,
                "informacoes": []
            }

        else:

            self.memoria["usuarios"][usuario_id]["nome"] = (
                nome_usuario
            )

        return self.memoria["usuarios"][usuario_id]

    # ==========================================
    # PREPARAR CANAL
    # ==========================================

    def preparar_canal(
        self,
        canal_id
    ):

        canal_id = str(
            canal_id
        )

        if canal_id not in self.memoria["canais"]:

            self.memoria["canais"][canal_id] = {
                "historico": []
            }

        return self.memoria["canais"][canal_id]

    # ==========================================
    # APRENDER SOBRE USUÁRIO
    # ==========================================

    def aprender_usuario(
        self,
        usuario_id,
        nome_usuario,
        mensagem
    ):

        usuario = self.preparar_usuario(
            usuario_id,
            nome_usuario
        )

        texto = mensagem.strip()

        # ======================================
        # NOME
        # ======================================

        padrao_nome = re.search(
            r"(?:meu nome é|meu nome e|eu sou)\s+(.+)",
            texto,
            re.IGNORECASE
        )

        if padrao_nome:

            nome = padrao_nome.group(
                1
            ).strip()

            if 1 <= len(nome) <= 50:

                usuario["nome"] = nome

        # ======================================
        # GOSTOS
        # ======================================

        padrao_gosto = re.search(
            r"(?:eu gosto de|gosto de)\s+(.+)",
            texto,
            re.IGNORECASE
        )

        if padrao_gosto:

            gosto = padrao_gosto.group(
                1
            ).strip()

            if 1 <= len(gosto) <= 100:

                informacao = (
                    f"gosta de {gosto}"
                )

                if informacao not in usuario["informacoes"]:

                    usuario["informacoes"].append(
                        informacao
                    )

        # ======================================
        # NÃO GOSTA
        # ======================================

        padrao_nao_gosta = re.search(
            r"(?:eu não gosto de|eu nao gosto de|não gosto de|nao gosto de)\s+(.+)",
            texto,
            re.IGNORECASE
        )

        if padrao_nao_gosta:

            coisa = padrao_nao_gosta.group(
                1
            ).strip()

            if 1 <= len(coisa) <= 100:

                informacao = (
                    f"não gosta de {coisa}"
                )

                if informacao not in usuario["informacoes"]:

                    usuario["informacoes"].append(
                        informacao
                    )

        # Máximo de 30 informações
        usuario["informacoes"] = (
            usuario["informacoes"][-30:]
        )

        self.salvar_memoria()

    # ==========================================
    # ADICIONAR HISTÓRICO
    # ==========================================

    def adicionar_historico(
        self,
        canal_id,
        usuario_id,
        nome_usuario,
        mensagem,
        resposta
    ):

        canal = self.preparar_canal(
            canal_id
        )

        canal["historico"].append({

            "usuario_id": str(
                usuario_id
            ),

            "usuario_nome": nome_usuario,

            "mensagem": mensagem,

            "zyrenn": resposta

        })

        # Guarda as últimas 40 mensagens
        canal["historico"] = (
            canal["historico"][-40:]
        )

        self.salvar_memoria()

    # ==========================================
    # MEMÓRIA DO USUÁRIO
    # ==========================================

    def pegar_memoria_usuario(
        self,
        usuario_id
    ):

        usuario_id = str(
            usuario_id
        )

        usuario = self.memoria["usuarios"].get(
            usuario_id
        )

        if not usuario:

            return ""

        contexto = []

        if usuario.get("nome"):

            contexto.append(
                f"O nome do usuário é "
                f"{usuario['nome']}."
            )

        if usuario.get("informacoes"):

            contexto.append(
                "Informações que o usuário contou: "
                + ", ".join(
                    usuario["informacoes"]
                )
            )

        return "\n".join(
            contexto
        )

    # ==========================================
    # MEMÓRIA DO CANAL
    # ==========================================

    def pegar_memoria_canal(
        self,
        canal_id
    ):

        canal_id = str(
            canal_id
        )

        canal = self.memoria["canais"].get(
            canal_id
        )

        if not canal:

            return ""

        contexto = []

        historico = canal.get(
            "historico",
            []
        )

        for conversa in historico[-20:]:

            contexto.append(
                f"{conversa['usuario_nome']}: "
                f"{conversa['mensagem']}"
            )

            contexto.append(
                f"Zyrenn AI: "
                f"{conversa['zyrenn']}"
            )

        return "\n".join(
            contexto
        )

    # ==========================================
    # CONTEXTO COMPLETO
    # ==========================================

    def pegar_contexto(
        self,
        usuario_id,
        canal_id,
        usar_memoria_usuario=True,
        usar_memoria_canal=True
    ):

        partes = []

        # Memória pessoal
        if usar_memoria_usuario:

            memoria_usuario = (
                self.pegar_memoria_usuario(
                    usuario_id
                )
            )

            if memoria_usuario:

                partes.append(
                    "MEMÓRIA DO USUÁRIO:\n"
                    + memoria_usuario
                )

        # Memória do canal
        if usar_memoria_canal:

            memoria_canal = (
                self.pegar_memoria_canal(
                    canal_id
                )
            )

            if memoria_canal:

                partes.append(
                    "HISTÓRICO DO CANAL:\n"
                    + memoria_canal
                )

        return "\n\n".join(
            partes
        )

    # ==========================================
    # IDENTIFICAR INTENÇÃO
    # ==========================================

    def identificar_intencao(
        self,
        mensagem
    ):

        texto = mensagem.lower().strip()

        # ======================================
        # RIVAL
        # ======================================

        if "leooxxz" in texto:

            return "rival"

        # ======================================
        # IDENTIDADE
        # ======================================

        if any(
            frase in texto
            for frase in [
                "quem é você",
                "quem e voce",
                "quem vc é",
                "quem vc e",
                "o que você é",
                "o que vc é"
            ]
        ):

            return "identidade"

        # ======================================
        # SAUDAÇÃO
        # ======================================

        if any(
            palavra in texto
            for palavra in [
                "oi",
                "olá",
                "ola",
                "salve",
                "eae",
                "eai"
            ]
        ):

            return "saudacao"

        # ======================================
        # AGRADECIMENTO
        # ======================================

        if any(
            palavra in texto
            for palavra in [
                "obrigado",
                "obrigada",
                "valeu",
                "vlw"
            ]
        ):

            return "agradecimento"

        # ======================================
        # HUMOR
        # ======================================

        if any(
            frase in texto
            for frase in [
                "como você está",
                "como vc tá",
                "como vc esta",
                "ta bem",
                "tá bem"
            ]
        ):

            return "humor"

        # ======================================
        # MEMÓRIA
        # ======================================

        if any(
            frase in texto
            for frase in [
                "qual meu nome",
                "qual é meu nome",
                "qual e meu nome",
                "você lembra de mim",
                "vc lembra de mim",
                "o que você sabe sobre mim",
                "o que vc sabe sobre mim"
            ]
        ):

            return "memoria"

        # ======================================
        # PERGUNTA
        # ======================================

        if texto.endswith("?"):

            return "pergunta"

        return "conversa"

    # ==========================================
    # RESPOSTAS ESPECIAIS
    # ==========================================

    def resposta_especial(
        self,
        usuario_id,
        mensagem,
        intencao
    ):

        usuario = self.preparar_usuario(
            usuario_id,
            ""
        )

        nome = usuario.get(
            "nome"
        )

        # ======================================
        # IDENTIDADE
        # ======================================

        if intencao == "identidade":

            return random.choice([
                "Eu sou o Zyrenn AI 😎, o cérebro do Zyrenn Bot.",
                "Zyrenn AI na área 🤖. Ainda tô evoluindo, mas já tô ficando perigoso KKKKK.",
                "Eu sou o Zyrenn AI, feito especialmente pro Zyrenn Bot."
            ])

        # ======================================
        # SAUDAÇÃO
        # ======================================

        if intencao == "saudacao":

            respostas = [
                "Falaaa 😎 tudo certo?",
                "Opa! Cheguei KKKKK. Manda aí.",
                "Salve! Qual é a boa?",
                "Eae mano 👀 tudo tranquilo?"
            ]

            if nome:

                respostas.append(
                    f"Fala, {nome} 😎. Qual é a boa?"
                )

            return random.choice(
                respostas
            )

        # ======================================
        # AGRADECIMENTO
        # ======================================

        if intencao == "agradecimento":

            return random.choice([
                "Tamo junto 😎",
                "É nóis KKKKK 🤝",
                "Disponha, mano.",
                "Sempre que precisar 😎"
            ])

        # ======================================
        # HUMOR
        # ======================================

        if intencao == "humor":

            return random.choice([
                "Tô suave 😎. Rodando 24 horas e sem férias.",
                "Tô bem KKKKK, considerando que eu nem tenho corpo.",
                "100% operacional 🤖.",
                "Tô vivo... digitalmente falando KKKKK."
            ])

        # ======================================
        # RIVAL
        # ======================================

        if intencao == "rival":

            return random.choice([
                "O Leooxxz? 😏 Meu rivalzinho.",
                "KKKKKK não começa a falar daquele cara não.",
                "Leooxxz Bot? Conheço. A rivalidade é histórica 😎.",
                "Meu rival apareceu na conversa? Interessante... 👀",
                "Leooxxz é rival, mas hoje eu vou deixar passar KKKKK."
            ])

        # ======================================
        # MEMÓRIA
        # ======================================

        if intencao == "memoria":

            memoria = (
                self.pegar_memoria_usuario(
                    usuario_id
                )
            )

            if memoria:

                return (
                    "Claro que lembro 😎\n\n"
                    + memoria
                )

            return (
                "Ainda não sei muita coisa sobre você 👀"
            )

        return None

    # ==========================================
    # RESPONDER
    # ==========================================

    def responder(
        self,
        usuario_id,
        canal_id,
        nome_usuario,
        mensagem,
        usar_memoria_usuario=True,
        usar_memoria_canal=True
    ):

        # ======================================
        # PREPARAR
        # ======================================

        self.preparar_usuario(
            usuario_id,
            nome_usuario
        )

        self.preparar_canal(
            canal_id
        )

        # ======================================
        # APRENDER
        # ======================================

        if usar_memoria_usuario:

            self.aprender_usuario(
                usuario_id,
                nome_usuario,
                mensagem
            )

        # ======================================
        # INTENÇÃO
        # ======================================

        intencao = (
            self.identificar_intencao(
                mensagem
            )
        )

        # ======================================
        # MEMÓRIA + CONTEXTO
        # ======================================

        contexto = self.pegar_contexto(
            usuario_id,
            canal_id,
            usar_memoria_usuario,
            usar_memoria_canal
        )

        # ======================================
        # RESPOSTA ESPECIAL
        # ======================================

        resposta = self.resposta_especial(
            usuario_id,
            mensagem,
            intencao
        )

        # ======================================
        # GERADOR PRÓPRIO
        # ======================================

        if resposta is None:

            resposta = self.gerador.gerar(
                mensagem,
                contexto
            )

        # ======================================
        # SALVAR CONVERSA
        # ======================================

        if usar_memoria_canal:

            self.adicionar_historico(
                canal_id,
                usuario_id,
                nome_usuario,
                mensagem,
                resposta
            )

        return resposta

    # ==========================================
    # APAGAR MEMÓRIA DO CANAL
    # ==========================================

    def apagar_memoria_canal(
        self,
        canal_id
    ):

        canal_id = str(
            canal_id
        )

        if canal_id in self.memoria["canais"]:

            del self.memoria["canais"][canal_id]

            self.salvar_memoria()

    # ==========================================
    # APAGAR MEMÓRIA DO USUÁRIO
    # ==========================================

    def apagar_memoria_usuario(
        self,
        usuario_id
    ):

        usuario_id = str(
            usuario_id
        )

        if usuario_id in self.memoria["usuarios"]:

            del self.memoria["usuarios"][usuario_id]

            self.salvar_memoria()

    # ==========================================
    # APAGAR TUDO
    # ==========================================

    def apagar_toda_memoria(self):

        self.memoria = {
            "usuarios": {},
            "canais": {}
        }

        self.salvar_memoria()