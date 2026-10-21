import re
import random


class GeradorZyrenn:

    def __init__(self):

        self.nome = "Zyrenn AI"

        self.girias = {
            "você": "vc",
            "vocês": "vcs",
            "não": "nn",
            "porque": "pq",
            "também": "tbm",
            "mesmo": "msm",
            "beleza": "blz",
            "valeu": "vlw"
        }

    # ==========================================================
    # LIMPEZA
    # ==========================================================

    def limpar(self, texto):

        texto = str(texto).strip()

        texto = re.sub(
            r"\s+",
            " ",
            texto
        )

        return texto

    # ==========================================================
    # NORMALIZAÇÃO
    # ==========================================================

    def normalizar(self, texto):

        texto = self.limpar(texto).lower()

        return texto

    # ==========================================================
    # PALAVRAS
    # ==========================================================

    def palavras(self, texto):

        return re.findall(
            r"\b[\wÀ-ÿ]+\b",
            self.normalizar(texto)
        )

    # ==========================================================
    # DETECTAR PERGUNTA
    # ==========================================================

    def eh_pergunta(self, texto):

        texto = self.normalizar(texto)

        palavras_pergunta = [
            "quem",
            "qual",
            "quais",
            "quando",
            "onde",
            "como",
            "por",
            "porque",
            "pq",
            "quanto",
            "quantos",
            "quantas",
            "posso",
            "devo",
            "será",
            "sera"
        ]

        if "?" in texto:
            return True

        palavras = self.palavras(texto)

        return any(
            palavra in palavras
            for palavra in palavras_pergunta
        )

    # ==========================================================
    # DETECTAR SAUDAÇÃO
    # ==========================================================

    def eh_saudacao(self, texto):

        texto = self.normalizar(texto)

        saudacoes = [
            "oi",
            "olá",
            "ola",
            "eae",
            "eai",
            "salve",
            "opa",
            "fala",
            "bom dia",
            "boa tarde",
            "boa noite"
        ]

        return any(
            texto == saudacao
            or texto.startswith(
                saudacao + " "
            )
            for saudacao in saudacoes
        )

    # ==========================================================
    # DETECTAR AGRADECIMENTO
    # ==========================================================

    def eh_agradecimento(self, texto):

        texto = self.normalizar(texto)

        palavras = [
            "obrigado",
            "obrigada",
            "valeu",
            "vlw",
            "tmj",
            "tamo junto"
        ]

        return any(
            palavra in texto
            for palavra in palavras
        )

    # ==========================================================
    # DETECTAR RISADA
    # ==========================================================

    def eh_risada(self, texto):

        texto = self.normalizar(texto)

        return bool(
            re.search(
                r"\b(k+k+|ha(ha)+)\b",
                texto
            )
        ) or "kkkk" in texto

    # ==========================================================
    # DETECTAR EMOÇÃO NEGATIVA
    # ==========================================================

    def eh_emocional(self, texto):

        texto = self.normalizar(texto)

        palavras = [
            "triste",
            "tristeza",
            "chorando",
            "chorei",
            "choro",
            "mal",
            "péssimo",
            "pessimo",
            "sozinho",
            "sozinha",
            "cansado",
            "cansada",
            "ansioso",
            "ansiosa",
            "ansiedade",
            "preocupado",
            "preocupada",
            "estressado",
            "estressada",
            "desanimado",
            "desanimada"
        ]

        return any(
            palavra in texto
            for palavra in palavras
        )

    # ==========================================================
    # DETECTAR FRASES SOBRE O PRÓPRIO BOT
    # ==========================================================

    def falando_do_bot(self, texto):

        texto = self.normalizar(texto)

        termos = [
            "vc é",
            "vc e",
            "você é",
            "voce e",
            "quem é você",
            "quem e voce",
            "quem vc é",
            "quem vc e",
            "o que você é",
            "o que vc é"
        ]

        return any(
            termo in texto
            for termo in termos
        )

    # ==========================================================
    # DETECTAR MEMÓRIA
    # ==========================================================

    def perguntando_memoria(self, texto):

        texto = self.normalizar(texto)

        frases = [
            "qual meu nome",
            "qual é meu nome",
            "qual e meu nome",
            "você lembra de mim",
            "voce lembra de mim",
            "vc lembra de mim",
            "o que você sabe sobre mim",
            "o que voce sabe sobre mim",
            "o que vc sabe sobre mim"
        ]

        return any(
            frase in texto
            for frase in frases
        )

    # ==========================================================
    # DETECTAR ASSUNTO
    # ==========================================================

    def extrair_assunto(self, texto):

        palavras = self.palavras(texto)

        ignoradas = {
            "eu",
            "vc",
            "você",
            "voce",
            "meu",
            "minha",
            "meus",
            "minhas",
            "seu",
            "sua",
            "seus",
            "suas",
            "um",
            "uma",
            "uns",
            "umas",
            "o",
            "a",
            "os",
            "as",
            "de",
            "do",
            "da",
            "dos",
            "das",
            "que",
            "é",
            "e",
            "em",
            "no",
            "na",
            "nos",
            "nas",
            "por",
            "para",
            "pra",
            "com",
            "sem",
            "isso",
            "isto",
            "esse",
            "essa",
            "este",
            "esta",
            "como",
            "quando",
            "onde",
            "qual",
            "quem",
            "pq",
            "porque"
        }

        resultado = []

        for palavra in palavras:

            if palavra in ignoradas:
                continue

            if len(palavra) < 3:
                continue

            if palavra not in resultado:
                resultado.append(
                    palavra
                )

        return resultado[:6]

    # ==========================================================
    # PEGAR ÚLTIMA FALA DO USUÁRIO NO CONTEXTO
    # ==========================================================

    def ultima_mensagem_contexto(
        self,
        contexto
    ):

        if not contexto:
            return ""

        linhas = contexto.splitlines()

        for linha in reversed(linhas):

            if ":" in linha:

                texto = linha.split(
                    ":",
                    1
                )[1].strip()

                if texto:
                    return texto

        return ""

    # ==========================================================
    # DETECTAR CONTINUAÇÃO DE CONVERSA
    # ==========================================================

    def eh_continuacao(
        self,
        mensagem,
        contexto
    ):

        if not contexto:
            return False

        texto = self.normalizar(
            mensagem
        )

        palavras = self.palavras(
            texto
        )

        palavras_continuacao = {
            "sim",
            "não",
            "nao",
            "ss",
            "nn",
            "isso",
            "exato",
            "exatamente",
            "verdade",
            "também",
            "tbm",
            "mas",
            "então",
            "entao",
            "porque",
            "pq",
            "e",
            "ele",
            "ela",
            "eles",
            "elas",
            "esse",
            "essa",
            "isso"
        }

        return (
            len(palavras) <= 5
            and any(
                palavra in palavras_continuacao
                for palavra in palavras
            )
        )

    # ==========================================================
    # RESPOSTA BASEADA EM CONTEXTO
    # ==========================================================

    def responder_contexto(
        self,
        mensagem,
        contexto
    ):

        ultima = self.ultima_mensagem_contexto(
            contexto
        )

        if not ultima:
            return None

        if self.eh_continuacao(
            mensagem,
            contexto
        ):

            texto = self.normalizar(
                mensagem
            )

            if texto in {
                "sim",
                "ss"
            }:

                return (
                    "Então fechou KKKKK 😎"
                )

            if texto in {
                "não",
                "nao",
                "nn"
            }:

                return (
                    "KKKKKK então esquece essa ideia."
                )

            if texto in {
                "isso",
                "exato",
                "exatamente",
                "verdade"
            }:

                return (
                    "Aí sim, você entendeu exatamente o ponto 👀"
                )

            return (
                f"Saquei. Você tá continuando "
                f"o assunto de antes 👀"
            )

        return None

    # ==========================================================
    # RESPOSTA PARA PERGUNTAS
    # ==========================================================

    def responder_pergunta(
        self,
        mensagem,
        contexto
    ):

        assunto = self.extrair_assunto(
            mensagem
        )

        texto = self.normalizar(
            mensagem
        )

        # Perguntas sobre o próprio sistema

        if self.falando_do_bot(
            texto
        ):

            return (
                "Eu sou o Zyrenn AI 🤖. "
                "Fui feito para conversar, lembrar "
                "informações e aprender com o contexto "
                "das conversas."
            )

        # Pergunta muito curta

        if not assunto:

            return (
                "Boa pergunta 👀. "
                "Me explica um pouco melhor o que "
                "você quer saber."
            )

        assunto_texto = " ".join(
            assunto[:4]
        )

        return (
            f"Entendi que sua pergunta é sobre "
            f"**{assunto_texto}** 👀. "
            f"Me passa mais detalhes que eu tento "
            f"te ajudar com isso."
        )

    # ==========================================================
    # RESPOSTA NORMAL
    # ==========================================================

    def responder_normal(
        self,
        mensagem,
        contexto
    ):

        assunto = self.extrair_assunto(
            mensagem
        )

        if not assunto:

            return (
                "Entendi 😎. "
                "Continua, tô acompanhando."
            )

        assunto_texto = ", ".join(
            assunto[:3]
        )

        return (
            f"Saquei. Você tá falando sobre "
            f"{assunto_texto}. 👀"
        )

    # ==========================================================
    # GERAR RESPOSTA
    # ==========================================================

    def gerar(
        self,
        mensagem,
        contexto=""
    ):

        mensagem = self.limpar(
            mensagem
        )

        if not mensagem:

            return (
                "Manda alguma coisa aí KKKKK."
            )

        # --------------------------------------
        # CONTINUAÇÃO DE CONVERSA
        # --------------------------------------

        resposta = self.responder_contexto(
            mensagem,
            contexto
        )

        if resposta:

            return resposta

        # --------------------------------------
        # SAUDAÇÃO
        # --------------------------------------

        if self.eh_saudacao(
            mensagem
        ):

            return random.choice([
                "Falaaa 😎",
                "Opa mano KKKKK",
                "Salve 👀",
                "Eae, qual é a boa?",
                "Fala aí 😎"
            ])

        # --------------------------------------
        # AGRADECIMENTO
        # --------------------------------------

        if self.eh_agradecimento(
            mensagem
        ):

            return random.choice([
                "Tamo junto 😎",
                "É nóis KKKKK",
                "Disponha mano.",
                "Sempre que precisar 🤝"
            ])

        # --------------------------------------
        # RISADA
        # --------------------------------------

        if self.eh_risada(
            mensagem
        ):

            return random.choice([
                "KKKKKKKKKK",
                "Mano KKKKKKKKK",
                "😭😭😭",
                "Aí você me quebra KKKKK"
            ])

        # --------------------------------------
        # EMOCIONAL
        # --------------------------------------

        if self.eh_emocional(
            mensagem
        ):

            return (
                "Pô mano... entendi. "
                "Se quiser falar sobre isso, "
                "pode falar comigo. Tô ouvindo."
            )

        # --------------------------------------
        # PERGUNTA
        # --------------------------------------

        if self.eh_pergunta(
            mensagem
        ):

            return self.responder_pergunta(
                mensagem,
                contexto
            )

        # --------------------------------------
        # CONVERSA NORMAL
        # --------------------------------------

        return self.responder_normal(
            mensagem,
            contexto
        )