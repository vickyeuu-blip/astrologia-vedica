"""
gemini_interpretador.py
=======================
Integração (opcional) com a API do Google Gemini para INTERPRETAR o mapa.

Princípio do projeto:
  * quem CALCULA é o Swiss Ephemeris (astrologia.py);
  * o Gemini apenas LÊ o JSON pronto e escreve um texto explicativo.
  O prompt proíbe o Gemini de recalcular ou inventar posições.

Chave da API (gratuita no Google AI Studio: https://aistudio.google.com/apikey)
Nunca escreva a chave dentro do código! Use uma destas formas:
  1) arquivo .streamlit/secrets.toml   ->  GEMINI_API_KEY = "sua_chave"
  2) variável de ambiente GEMINI_API_KEY
  3) campo de senha na barra lateral do site (só vale enquanto a página estiver aberta)
"""

from __future__ import annotations

import copy
import json
import os
import time

# Os nomes de modelos do Gemini mudam com frequência.
MODELO_PADRAO = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
MODELOS_RESERVA = [
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-4-hydrogen",
]

PROMPT_SISTEMA = """\
Você é um assistente que explica mapas natais de astrologia védica (Jyotish)
em português do Brasil, para estudantes e curiosos.

REGRAS OBRIGATÓRIAS
1. Use SOMENTE os dados do JSON fornecido. Não recalcule nem corrija posições
   planetárias, signos, casas, nakshatras ou padas. Não invente dados.
2. Se algo não estiver no JSON (dashas, Navamsa completo, aspectos, yogas,
   trânsitos etc.), diga que esse dado não foi calculado. Não o deduza.
3. O JSON usa zodíaco sideral, ayanamsa Lahiri, nodo lunar médio e casas
   Whole Sign (casa 1 = signo inteiro do Lagna).
4. Explique os termos sânscritos na primeira vez em que aparecerem.
5. Tom respeitoso e prudente: nada de previsões absolutas, nem conselhos
   médicos, jurídicos ou financeiros. Apresente como leitura simbólica e
   cultural, não como fato científico.
6. Cite sempre de onde vem cada afirmação (ex.: "Chandra em Rohini, pada 2,
   casa 5").

FORMATO DA RESPOSTA (Markdown)
## Sua essência
## Seu universo emocional
## Amor e relacionamentos
## Carreira e talentos
## Desafios e crescimento
## Seu Nakshatra lunar
## Limites desta leitura
Use parágrafos curtos, linguagem cotidiana e referências às posições calculadas.
"""


class ErroGemini(Exception):
    """Erro com mensagem amigável para mostrar na tela."""


def obter_chave_api(secrets=None) -> str | None:
    """Procura a chave em st.secrets (se fornecido) e depois no ambiente."""
    if secrets is not None:
        try:
            valor = secrets.get("GEMINI_API_KEY")
            if valor:
                return str(valor).strip()
        except Exception:
            pass  # não existe arquivo secrets.toml: tudo bem
    valor = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    return valor.strip() if valor else None


def preparar_json_para_ia(mapa: dict) -> dict:
    """
    Cópia do mapa SEM dados pessoais (nome e endereço completo), para enviar
    ao Gemini apenas o que é necessário para a interpretação.
    """
    copia = copy.deepcopy(mapa)
    copia.pop("pessoa", None)
    copia.pop("nascimento", None)
    copia.pop("metadados", None)
    return copia


def _cliente(chave: str):
    try:
        from google import genai
    except ImportError as erro:
        raise ErroGemini(
            "A biblioteca do Gemini não está instalada. Rode: pip install google-genai"
        ) from erro
    return genai.Client(api_key=chave)


def _traduzir_erro(erro: Exception) -> ErroGemini:
    codigo = getattr(erro, "code", None)
    texto = str(erro)
    print(f"[Gemini] Falha na API | code={codigo} | detalhe={texto}", flush=True)

    if codigo in (400, 401, 403) or "API key" in texto:
        return ErroGemini("Chave de API inválida ou sem permissão. Confira a chave.")
    if codigo == 404:
        return ErroGemini(
            "Modelo não encontrado. Atualize o modelo configurado no projeto."
        )
    if codigo == 429:
        return ErroGemini(
            "Limite gratuito de uso atingido. Espere alguns minutos e tente de novo."
        )
    if codigo in (500, 503):
        return ErroGemini("Os servidores do Gemini estão ocupados. Tente novamente.")
    return ErroGemini(f"Erro ao chamar o Gemini: {texto}")


def interpretar_mapa(
    mapa: dict, chave: str, modelo: str = MODELO_PADRAO, pergunta: str = ""
) -> str:
    """Envia o JSON ao Gemini e devolve o texto da interpretação (Markdown)."""
    if not chave:
        raise ErroGemini("Informe a chave da API do Gemini.")
    from google.genai import types

    dados = json.dumps(preparar_json_para_ia(mapa), ensure_ascii=False, indent=2)
    pedido = "Dados calculados do mapa natal (JSON):\n```json\n" + dados + "\n```\n\n"
    if pergunta.strip():
        pedido += "Foco pedido pelo usuário: " + pergunta.strip()
    else:
        pedido += "Faça a interpretação geral do mapa seguindo o formato indicado."

    fila_modelos = [modelo] + [m for m in MODELOS_RESERVA if m != modelo]
    ultimo_erro: Exception | None = None
    resposta = None

    with _cliente(chave) as cliente:
        for indice, nome_modelo in enumerate(fila_modelos):
            try:
                resposta = cliente.models.generate_content(
                    model=nome_modelo,
                    contents=pedido,
                    config=types.GenerateContentConfig(
                        system_instruction=PROMPT_SISTEMA, temperature=0.4
                    ),
                )
                break
            except ErroGemini:
                raise
            except Exception as erro:
                ultimo_erro = erro
                codigo = getattr(erro, "code", None)
                print(
                    f"[Gemini] Erro no modelo '{nome_modelo}' (code={codigo}): {erro}",
                    flush=True,
                )
                if codigo in (404, 500, 503) and indice < len(fila_modelos) - 1:
                    time.sleep(1)
                    continue
                raise _traduzir_erro(erro) from erro

    if resposta is None and ultimo_erro is not None:
        raise _traduzir_erro(ultimo_erro) from ultimo_erro

    texto = getattr(resposta, "text", None)
    if not texto:
        raise ErroGemini(
            "O Gemini não devolveu texto (a resposta pode ter sido bloqueada). "
            "Tente novamente ou mude o modelo."
        )
    return texto


def listar_modelos(chave: str) -> list[str]:
    """Lista os modelos que aceitam generateContent para a chave informada."""
    if not chave:
        raise ErroGemini("Informe a chave da API do Gemini.")
    try:
        nomes = []
        with _cliente(chave) as cliente:
            for modelo in cliente.models.list():
                acoes = getattr(modelo, "supported_actions", None) or []
                if "generateContent" in acoes:
                    nomes.append(str(modelo.name).replace("models/", ""))
        return sorted(nomes)
    except ErroGemini:
        raise
    except Exception as erro:
        raise _traduzir_erro(erro) from erro
