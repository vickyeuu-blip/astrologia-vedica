"""
app.py
======
Arquivo principal do site (Streamlit). Para rodar:

    streamlit run app.py

Fluxo do site:
  1. A pessoa digita nome, data, horário e cidade  -> botão "Buscar local"
  2. Confere o local e o fuso horário encontrados  -> botão "Calcular mapa"
  3. Vê as tabelas, o JSON (e baixa o arquivo) e, se quiser, pede uma
     interpretação ao Gemini.
"""

import json
import re
import unicodedata
from datetime import date, time

import pandas as pd
import streamlit as st

from constantes import APP_VERSAO, CONFIGURACAO_TEXTO
import gemini_interpretador as gem
from geolocalizacao import (
    ErroLocalizacao,
    analisar_horario,
    buscar_locais,
    descobrir_fuso,
)

st.set_page_config(page_title="Astrologia Védica (Jyotish)", page_icon="🪐", layout="centered")

# O PySwissEph é importado aqui com proteção, para dar uma mensagem clara
# caso a instalação tenha falhado.
try:
    from astrologia import ErroCalculo, gerar_json_mapa
except ImportError as erro_importacao:
    st.error(
        "Não consegui carregar o PySwissEph (módulo 'swisseph'). "
        "Provavelmente a instalação não foi concluída ou o Python é uma versão "
        "sem pacote pronto. Releia o passo 'Instalar as bibliotecas' do README.\n\n"
        f"Detalhe técnico: {erro_importacao}"
    )
    st.stop()


# ---------------------------------------------------------------------------
# Funções de apoio
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False, ttl=3600)
def buscar_locais_em_cache(consulta: str) -> list:
    """Guarda o resultado da busca por 1 hora (evita repetir pedidos ao Nominatim)."""
    return buscar_locais(consulta)


def nome_de_arquivo(nome: str) -> str:
    """'João da Silva' -> 'joao_da_silva' (seguro para nome de arquivo)."""
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    limpo = re.sub(r"[^a-zA-Z0-9]+", "_", sem_acento).strip("_").lower()
    return limpo or "mapa"


def tabela_grahas(mapa: dict) -> pd.DataFrame:
    linhas = []
    for g in mapa["grahas"]:
        linhas.append({
            "Graha": g["graha"],
            "Planeta": g["nome_pt"],
            "Signo": f'{g["signo"]} ({g["signo_pt"]})',
            "Grau no signo": g["grau_no_signo_dms"],
            "Casa": g["casa"],
            "Nakshatra": g["nakshatra"],
            "Pada": g["pada"],
            "Regente do nakshatra": g["regente_do_nakshatra"],
            "Retrógrado": "Sim" if g["retrogrado"] else "Não",
            "Longitude sideral": g["longitude_sideral"],
        })
    return pd.DataFrame(linhas)


def tabela_casas(mapa: dict) -> pd.DataFrame:
    linhas = []
    for c in mapa["casas"]:
        linhas.append({
            "Casa": c["casa"],
            "Signo": f'{c["signo"]} ({c["signo_pt"]})',
            "Regente": c["regente_do_signo"],
            "Regente está na casa": c["regente_esta_na_casa"],
            "Grahas na casa": ", ".join(c["grahas_na_casa"]) or "—",
        })
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------------------
# Estado da sessão (a "memória" da página entre um clique e outro)
# ---------------------------------------------------------------------------
st.session_state.setdefault("busca_id", 0)

# ---------------------------------------------------------------------------
# Barra lateral
# ---------------------------------------------------------------------------
chave_gemini = gem.obter_chave_api(st.secrets)
modelo_gemini = gem.MODELO_PADRAO
try:
    modelo_gemini = st.secrets.get("GEMINI_MODEL", modelo_gemini)
except Exception:
    pass

# ---------------------------------------------------------------------------
# Título
# ---------------------------------------------------------------------------
st.title("Astrologia Védica")
st.caption(
    "Projeto acadêmico. As posições são calculadas astronomicamente com o Swiss "
    "Ephemeris. A astrologia é uma tradição cultural/simbólica e não é "
    "comprovada cientificamente; as interpretações não substituem aconselhamento "
    "profissional."
)

# ---------------------------------------------------------------------------
# ETAPA 1 - dados de nascimento
# ---------------------------------------------------------------------------
st.header("1. Dados de nascimento")
with st.form("form_nascimento"):
    nome = st.text_input("Nome", placeholder="Ex.: Maria Souza")
    col1, col2 = st.columns(2)
    data_nasc = col1.date_input(
        "Data de nascimento",
        value=date(2000, 1, 1),
        min_value=date(1800, 1, 1),
        max_value=date.today(),
        format="DD/MM/YYYY",
    )
    hora_nasc = col2.time_input(
        "Horário de nascimento (o que marcava o relógio no local)",
        value=time(12, 0),
        step=60,
    )
    cidade = st.text_input(
        "Cidade de nascimento",
        placeholder="Ex.: Campinas, São Paulo, Brasil  (quanto mais completo, melhor)",
    )
    buscar = st.form_submit_button("🔎 Buscar local")

if buscar:
    if not nome.strip():
        st.error("Digite o nome.")
    elif not cidade.strip():
        st.error("Digite a cidade de nascimento.")
    else:
        try:
            with st.spinner("Procurando a cidade..."):
                candidatos = buscar_locais_em_cache(cidade)
        except ErroLocalizacao as erro:
            st.error(str(erro))
        else:
            st.session_state["entrada"] = {
                "nome": nome.strip(),
                "data": data_nasc,
                "hora": hora_nasc,
                "cidade": cidade.strip(),
            }
            st.session_state["candidatos"] = candidatos
            st.session_state["busca_id"] += 1
            st.session_state.pop("resultado", None)
            st.session_state.pop("interpretacao", None)
            st.session_state.pop("erro_ia", None)

# ---------------------------------------------------------------------------
# ETAPA 2 - confirmar local e fuso
# ---------------------------------------------------------------------------
if "entrada" in st.session_state:
    entrada = st.session_state["entrada"]
    candidatos = st.session_state["candidatos"]
    id_busca = st.session_state["busca_id"]

    st.header("2. Confirme sua cidade")

    local = None
    if candidatos:
        indice = st.radio(
            "Escolha o local correto:",
            options=list(range(len(candidatos))),
            format_func=lambda i: candidatos[i]["descricao"],
            key=f"radio_local_{id_busca}",
        )
        escolhido = candidatos[indice]
        local = {**escolhido, "origem": "Nominatim / OpenStreetMap"}
    else:
        st.warning(
            "Nenhum local encontrado. Tente escrever a cidade com estado e país "
            "(ex.: 'Recife, Pernambuco, Brasil') ou use a opção avançada abaixo."
        )

    nome_fuso_manual = ""
    offset_manual = None
    with st.expander("Avançado: informar coordenadas / fuso manualmente"):
        usar_manual = st.checkbox("Usar coordenadas informadas por mim", key=f"manual_{id_busca}")
        if usar_manual:
            lat_m = st.number_input("Latitude (Sul é negativo)", -90.0, 90.0, 0.0, format="%.6f",
                                    key=f"lat_{id_busca}")
            lon_m = st.number_input("Longitude (Oeste é negativo)", -180.0, 180.0, 0.0, format="%.6f",
                                    key=f"lon_{id_busca}")
            local = {
                "descricao": f"Coordenadas informadas manualmente ({lat_m:.4f}, {lon_m:.4f})",
                "latitude": lat_m,
                "longitude": lon_m,
                "origem": "manual",
            }
        nome_fuso_manual = st.text_input(
            "Fuso horário (opcional, nome IANA, ex.: America/Manaus)",
            key=f"fuso_{id_busca}",
            help="Deixe em branco para o programa descobrir sozinho.",
        ).strip()
        usar_offset = st.checkbox(
            "Usar um deslocamento UTC fixo (sobrepõe o fuso acima)", key=f"usaoff_{id_busca}"
        )
        if usar_offset:
            offset_manual = st.number_input(
                "Deslocamento em horas (ex.: -3 para UTC-03:00)", -12.0, 14.0, -3.0, 0.25,
                key=f"off_{id_busca}",
            )

    if local is None:
        st.stop()

    # --- descobrir o fuso da época ---------------------------------------
    try:
        if offset_manual is not None:
            nome_fuso = None
        elif nome_fuso_manual:
            nome_fuso = nome_fuso_manual
        else:
            nome_fuso = descobrir_fuso(local["latitude"], local["longitude"])

        ocorrencia = "primeira"
        momento = analisar_horario(entrada["data"], entrada["hora"], nome_fuso,
                                   offset_manual, ocorrencia)
        if momento["status"] == "ambiguo":
            escolha = st.radio(
                "Esse horário aconteceu duas vezes (fim do horário de verão). Qual vale?",
                ["Primeira vez (ainda em horário de verão)",
                 "Segunda vez (já em horário padrão)"],
                key=f"ocorrencia_{id_busca}",
            )
            ocorrencia = "segunda" if escolha.startswith("Segunda") else "primeira"
            momento = analisar_horario(entrada["data"], entrada["hora"], nome_fuso,
                                       offset_manual, ocorrencia)
    except ErroLocalizacao as erro:
        st.error(str(erro))
        st.stop()

    if momento["status"] == "inexistente":
        st.error(momento["avisos"][0])
        st.stop()

    with st.expander("Dados técnicos da localização"):
        st.info(
            f"**Local:** {local['descricao']}  \n"
            f"**Latitude / Longitude:** {local['latitude']:.4f} / {local['longitude']:.4f}  \n"
            f"**Fuso:** {momento['nome_fuso']} · {momento['offset_texto']} · "
            f"horário de verão: {'sim' if momento['horario_verao'] else 'não'}  \n"
            f"**Horário UTC usado no cálculo:** {momento['dt_utc'].strftime('%d/%m/%Y %H:%M:%S')}"
        )
    for aviso in momento["avisos"]:
        st.warning(aviso)

    consentimento = st.checkbox("Concordo com o envio dos dados astrológicos ao Gemini para gerar a interpretação. O provedor pode usar dados enviados no plano gratuito para melhorar seus serviços.")
    if st.button("✨ Descobrir meu mapa", type="primary", disabled=not consentimento):
        st.session_state.pop("resultado", None)
        st.session_state.pop("interpretacao", None)
        st.session_state.pop("erro_ia", None)
        try:
            with st.spinner("Calculando posições..."):
                st.session_state["resultado"] = gerar_json_mapa(
                    nome=entrada["nome"],
                    cidade_informada=entrada["cidade"],
                    local=local,
                    data_local=entrada["data"],
                    hora_local=entrada["hora"],
                    momento=momento,
                )
            st.session_state.pop("interpretacao", None)
        except ErroCalculo as erro:
            st.error(str(erro))

# ---------------------------------------------------------------------------
# ETAPA 3 - resultados
# ---------------------------------------------------------------------------
mapa = st.session_state.get("resultado")
if mapa:
    st.header("Seu universo védico")
    aba_ia, aba_tabelas = st.tabs(["Minha interpretação", "Mapa completo"])
    with aba_ia:
        if "interpretacao" not in st.session_state and "erro_ia" not in st.session_state:
            try:
                with st.spinner("Preparando sua interpretação personalizada..."):
                    st.session_state["interpretacao"] = gem.interpretar_mapa(mapa, chave_gemini, modelo_gemini)
            except gem.ErroGemini:
                st.session_state["erro_ia"] = True
        if st.session_state.get("interpretacao"):
            st.markdown(st.session_state["interpretacao"])
        else:
            st.warning("A interpretação está indisponível no momento. Seu mapa calculado está na outra aba.")
            if st.button("Tentar novamente", disabled=not consentimento):
                st.session_state.pop("erro_ia", None)
                st.rerun()

    with aba_tabelas:
        r = mapa["resumo"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Lagna (Ascendente)", r["lagna"])
        c2.metric("Rashi lunar", r["signo_lunar_rashi"])
        c3.metric("Nakshatra da Lua", f'{r["nakshatra_lunar"]} (pada {r["pada_lunar"]})')
        c4.metric("Signo solar", r["signo_solar"])
        asc = mapa["ascendente"]
        st.write(
            f'**Ascendente:** {asc["grau_no_signo_dms"]} de {asc["signo"]} · '
            f'Nakshatra {asc["nakshatra"]}, pada {asc["pada"]}'
        )
        st.subheader("Os nove Grahas")
        st.dataframe(tabela_grahas(mapa), hide_index=True)
        st.subheader("As doze casas (Whole Sign)")
        st.dataframe(tabela_casas(mapa), hide_index=True)
        st.caption(
            f'Ayanamsa Lahiri neste instante: {mapa["configuracao"]["valor_ayanamsa_lahiri_graus"]}° · '
            f'Efeméride: {mapa["metadados"]["efemeride_usada"]}'
        )
        for aviso in mapa["avisos"]:
            st.warning(aviso)

        with st.expander("Dados técnicos e JSON"):
            texto_json = json.dumps(mapa, ensure_ascii=False, indent=2)
            st.download_button(
                "⬇️ Baixar JSON",
                data=texto_json,
                file_name=f"mapa_vedico_{nome_de_arquivo(mapa['pessoa']['nome'])}.json",
                mime="application/json",
            )
            st.json(mapa, expanded=1)

