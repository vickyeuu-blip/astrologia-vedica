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

def _texto_pdf(texto: object) -> str:
    """Ajusta caracteres especiais para evitar erro de acentuação na fonte padrão do PDF."""
    s = str(texto)
    for orig, sub in {
        "—": "-",
        "–": "-",
        "•": "-",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "…": "...",
    }.items():
        s = s.replace(orig, sub)
    return s.encode("latin-1", "replace").decode("latin-1")


def gerar_pdf_mapa(mapa: dict, interpretacao: str | None = None) -> bytes:
    from fpdf import FPDF
    from fpdf.fonts import FontFace

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Título
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(64, 56, 47)
    pdf.multi_cell(0, 10, _texto_pdf(f"Mapa Védico (Jyotish) - {mapa['pessoa']['nome']}"))
    pdf.ln(3)

    # Resumo e Ascendente
    r = mapa["resumo"]
    asc = mapa["ascendente"]
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, _texto_pdf("Resumo"), new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 10)
    resumo_linhas = [
        f"Lagna (Ascendente): {r['lagna']}",
        f"Rashi lunar: {r['signo_lunar_rashi']}",
        f"Nakshatra da Lua: {r['nakshatra_lunar']} (pada {r['pada_lunar']})",
        f"Signo solar: {r['signo_solar']}",
        (
            f"Ascendente: {asc['grau_no_signo_dms']} de {asc['signo']} "
            f"(Nakshatra {asc['nakshatra']}, pada {asc['pada']})"
        ),
    ]
    for linha in resumo_linhas:
        pdf.multi_cell(0, 6, _texto_pdf(linha))
    pdf.ln(4)

    headings_style = FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=(64, 60, 80))
    pdf.set_draw_color(216, 203, 180)

    # Tabela dos Grahas
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, _texto_pdf("Os nove Grahas"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 7.5)
    df_grahas = tabela_grahas(mapa)
    with pdf.table(
        col_widths=(16, 15, 32, 21, 10, 22, 10, 24, 17, 23),
        headings_style=headings_style,
        line_height=5,
    ) as table:
        row = table.row()
        for col in df_grahas.columns:
            row.cell(_texto_pdf(col))
        for _, linha_df in df_grahas.iterrows():
            row = table.row()
            for valor in linha_df:
                row.cell(_texto_pdf(valor))
    pdf.ln(5)

    # Tabela das Casas
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, _texto_pdf("As doze casas (Whole Sign)"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8.5)
    df_casas = tabela_casas(mapa)
    with pdf.table(
        col_widths=(15, 45, 30, 35, 65),
        headings_style=headings_style,
        line_height=5.5,
    ) as table:
        row = table.row()
        for col in df_casas.columns:
            row.cell(_texto_pdf(col))
        for _, linha_df in df_casas.iterrows():
            row = table.row()
            for valor in linha_df:
                row.cell(_texto_pdf(valor))

    # Interpretação (se já tiver sido gerada)
    if interpretacao:
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 9, _texto_pdf("Interpretação"), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        for linha in interpretacao.splitlines():
            limpa = linha.strip()
            if not limpa:
                pdf.ln(3)
            elif limpa.startswith("#"):
                pdf.ln(2)
                pdf.set_font("Helvetica", "B", 11)
                pdf.multi_cell(0, 6, _texto_pdf(limpa.lstrip("# ")))
            else:
                pdf.set_font("Helvetica", "", 10)
                pdf.multi_cell(0, 5.5, _texto_pdf(limpa.replace("**", "")))

    return bytes(pdf.output())


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
st.markdown('\n<style>\n@import url(\'https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600;700&family=DM+Sans:wght@400;500;600;700&display=swap\');\n:root {color-scheme:light;}\n.stApp, [data-testid="stHeader"] {background:#F5F0E7;color:#40382F;}\n.stApp {background-image:radial-gradient(ellipse at top,#FFFCF6 0%,#F5F0E7 65%);}\n.stApp p,.stApp label,.stApp input,.stApp button,.stApp [data-testid="stMarkdownContainer"] {font-family:\'DM Sans\',sans-serif;}\n.stApp h1,.stApp h2,.stApp h3 {font-family:\'Cormorant Garamond\',Georgia,serif;color:#40382F;font-weight:600;}\n.stApp h2 {font-size:2.1rem;}\n.block-container {max-width:850px;padding-top:3rem;padding-bottom:4rem;}\n[data-testid="stForm"] {background:#FFFCF6;border:1px solid #E5DAC6;border-radius:22px;padding:1.7rem;box-shadow:0 10px 35px #40382F0a;}\n[data-testid="stTextInput"] input,[data-testid="stDateInput"] input,[data-testid="stTimeInput"] input {background:#FFFCF6;color:#40382F;}\n[data-baseweb="input"] {border-radius:10px;background:#FFFCF6;border-color:#D8CBB4;}\n.stButton button,.stFormSubmitButton button,.stDownloadButton button {border-radius:10px;border:1px solid #403C50;background:#403C50;color:white;min-height:44px;}\n.stButton button p,.stFormSubmitButton button p,.stDownloadButton button p {color:white;}\n.stButton button:hover,.stFormSubmitButton button:hover {background:#57516A;color:white;border-color:#57516A;}\n.stButton button:disabled {opacity:.45;}\n[data-testid="stExpander"] {background:#FFFCF6;border-radius:12px;}\n[data-baseweb="tab-list"] {gap:12px;background:transparent;}\n[data-baseweb="tab"] {color:#40382F;padding:12px 8px;white-space:normal;}\n[data-baseweb="tab"][aria-selected="true"] {color:#95733F;}\n[data-baseweb="tab-highlight"] {background:#B69A69;}\n[data-testid="stMetric"] {background:#FFFCF6;border:1px solid #E5DAC6;border-radius:14px;padding:12px;}\n[data-testid="stMetricValue"] {font-size:1.1rem;white-space:normal;overflow-wrap:anywhere;}\n.vedic-hero {text-align:center;padding:12px 0 30px;color:#40382F;}\n.vedic-hero .brand {font:600 12px \'DM Sans\',sans-serif;letter-spacing:.25em;color:#95733F;margin:12px 0;}\n.vedic-hero h1 {font-size:clamp(2.5rem,6vw,3.7rem);line-height:1.05;margin:12px 0;}\n.vedic-hero p {color:#756B5D;font-size:1rem;max-width:480px;margin:12px auto;}\n.vedic-hero > svg {width:145px;height:145px;}\n@media(max-width:600px){.block-container{padding:2rem 1rem;}[data-testid="stForm"]{padding:1rem;}}\n</style>\n', unsafe_allow_html=True)
st.markdown('<div class="vedic-hero"><svg viewBox="0 0 180 180" xmlns="http://www.w3.org/2000/svg" fill="none" stroke="#B69A69"><circle cx="90" cy="90" r="83"/><circle cx="90" cy="90" r="65"/><circle cx="90" cy="90" r="44"/><path d="M90 7V46 M90 134V173 M7 90H46 M134 90H173 M31 31L59 59 M121 121L149 149 M31 149L59 121 M121 59L149 31"/><circle cx="90" cy="90" r="19" fill="#B69A69"/><path d="M90 61V68 M90 112V119 M61 90H68 M112 90H119 M69 69L74 74 M106 106L111 111 M69 111L74 106 M106 74L111 69" stroke-width="2"/></svg><div class="brand">ASTROLOGIA VÉDICA</div><h1>Descubra o universo<br>que existe em você.</h1><p>Uma jornada de autoconhecimento através da sabedoria do Jyotish.</p></div>', unsafe_allow_html=True)
st.markdown("""
<p style="
    text-align: center;
    color: #51483E;
    font-size: 16px;
    line-height: 1.7;
    max-width: 600px;
    margin: 0 auto 30px auto;
">
    Originária da Índia, a astrologia védica, também conhecida
    como Jyotish, é uma tradição milenar que interpreta a posição
    dos astros no momento do nascimento, oferecendo uma perspectiva
    simbólica sobre sua personalidade, seus talentos e os desafios da vida.
</p>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# ETAPA 1 - dados de nascimento
# ---------------------------------------------------------------------------
st.header("Seu mapa de nascimento")
with st.form("form_nascimento"):
    nome = st.text_input("Nome", placeholder="Como podemos chamar você?")
    col1, col2 = st.columns(2)
    data_nasc = col1.date_input(
        "Data de nascimento",
        value=date(2000, 1, 1),
        min_value=date(1800, 1, 1),
        max_value=date.today(),
        format="DD/MM/YYYY",
    )
    hora_nasc = col2.time_input(
        "Horário de nascimento",
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

    st.header("Confirme sua cidade")

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
        if consentimento and "interpretacao" not in st.session_state and "erro_ia" not in st.session_state:
            try:
                with st.spinner("Preparando sua interpretação personalizada..."):
                    st.session_state["interpretacao"] = gem.interpretar_mapa(mapa, chave_gemini, modelo_gemini)
            except gem.ErroGemini as erro:
                import re
                mensagem = str(erro)
                if chave_gemini:
                    mensagem = mensagem.replace(chave_gemini, "[oculta]")
                mensagem = re.sub(r"AIza[\w-]+", "[oculta]", mensagem)
                st.session_state["erro_ia"] = mensagem
        if st.session_state.get("interpretacao"):
            st.markdown(st.session_state["interpretacao"])
        else:
            st.warning("A interpretação está indisponível no momento. Seu mapa calculado está na outra aba.")
            if st.session_state.get("erro_ia"):
                st.error(st.session_state["erro_ia"])
            if st.button("Tentar novamente", disabled=not consentimento):
                st.session_state.pop("erro_ia", None)
                st.rerun()

    with aba_tabelas:
        r = mapa["resumo"]
        c1, c2 = st.columns(2)
        c3, c4 = st.columns(2)
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







        st.download_button(
            "⬇️ Baixar mapa em PDF",
            data=gerar_pdf_mapa(mapa, st.session_state.get("interpretacao")),
            file_name=f"mapa_vedico_{nome_de_arquivo(mapa['pessoa']['nome'])}.pdf",
            mime="application/pdf",
        )
        st.caption(
            f'Ayanamsa Lahiri neste instante: {mapa["configuracao"]["valor_ayanamsa_lahiri_graus"]}° · '
            f'Efeméride: {mapa["metadados"]["efemeride_usada"]}'
        )

        with st.expander("Dados técnicos e JSON"):
            texto_json = json.dumps(mapa, ensure_ascii=False, indent=2)
            st.download_button(
                "⬇️ Baixar JSON",
                data=texto_json,
                file_name=f"mapa_vedico_{nome_de_arquivo(mapa['pessoa']['nome'])}.json",
                mime="application/json",
            )
            st.json(mapa, expanded=1)
