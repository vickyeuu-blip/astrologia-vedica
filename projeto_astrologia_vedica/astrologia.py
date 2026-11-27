"""
astrologia.py
=============
Todos os cálculos astronômicos do projeto, feitos com a biblioteca PySwissEph
(o Swiss Ephemeris, usado por astrônomos e astrólogos do mundo todo).

NENHUMA posição de planeta é "inventada" aqui: cada longitude vem de
swe.calc_ut(), e o Ascendente vem de swe.houses_ex().

Configuração fixa deste projeto:
  * Zodíaco SIDERAL
  * Ayanamsa LAHIRI
  * Nodo lunar MÉDIO (Mean Node) -> Rahu; Ketu = Rahu + 180°
  * Casas WHOLE SIGN (o signo do Ascendente inteiro é a casa 1, e assim por diante)
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path

import swisseph as swe

from constantes import (
    APP_VERSAO,
    CONFIGURACAO_TEXTO,
    NAKSHATRAS,
    NOMES_GRAHAS,
    REGENTES_NAKSHATRAS,
    SIGNOS,
)

# Pasta onde (opcionalmente) ficam os arquivos .se1 do Swiss Ephemeris.
PASTA_EPHE = Path(__file__).resolve().parent / "ephe"

# A biblioteca Swiss Ephemeris guarda configurações "globais". Para evitar que
# duas pessoas usando o site ao mesmo tempo se atrapalhem, usamos uma trava.
_TRAVA = threading.Lock()


class ErroCalculo(Exception):
    """Erro com mensagem amigável para mostrar na tela."""


# ---------------------------------------------------------------------------
# Ordem tradicional dos Grahas e seus identificadores no Swiss Ephemeris.
# Ketu não existe como corpo no Swiss Ephemeris: ele é sempre o ponto
# oposto (180°) a Rahu.
# ---------------------------------------------------------------------------
GRAHAS_SWE = [
    ("Surya", swe.SUN),
    ("Chandra", swe.MOON),
    ("Mangala", swe.MARS),
    ("Budha", swe.MERCURY),
    ("Guru", swe.JUPITER),
    ("Shukra", swe.VENUS),
    ("Shani", swe.SATURN),
    ("Rahu", swe.MEAN_NODE),  # nodo lunar MÉDIO
]


# ---------------------------------------------------------------------------
# Funções auxiliares (matemática simples, sem astronomia)
# ---------------------------------------------------------------------------
def formatar_dms(graus: float) -> str:
    """Converte 12.5833 em  12°35'00\"  (truncando, nunca arredondando para 60")."""
    total_segundos = int(graus * 3600)
    g, resto = divmod(total_segundos, 3600)
    m, s = divmod(resto, 60)
    return f"{g}°{m:02d}'{s:02d}\""


def descrever_longitude(longitude: float) -> dict:
    """
    A partir de uma longitude sideral (0 a 360), descobre:
    signo, grau dentro do signo, nakshatra, pada e signo do Navamsa.

    Regras:
      * cada signo tem 30°
      * cada nakshatra tem 360/27 = 13°20'
      * cada pada tem 3°20' (são 4 padas por nakshatra, 108 no total)
    Usamos "longitude * 108 / 360" para achar o pada global (0 a 107) com
    mais segurança contra erros de arredondamento.
    """
    lon = longitude % 360.0

    indice_signo = int(lon // 30)
    grau_no_signo = lon - indice_signo * 30

    pada_global = int(lon * 108 / 360)
    pada_global = min(pada_global, 107)
    indice_nakshatra = pada_global // 4
    pada = pada_global % 4 + 1

    # Navamsa: cada pada corresponde a um signo, em sequência a partir de Áries.
    indice_navamsa = pada_global % 12

    signo = SIGNOS[indice_signo]
    navamsa = SIGNOS[indice_navamsa]
    return {
        "longitude_sideral": round(lon, 6),
        "signo": signo[0],
        "signo_pt": signo[1],
        "numero_do_signo": indice_signo + 1,
        "regente_do_signo": signo[2],
        "grau_no_signo": round(grau_no_signo, 6),
        "grau_no_signo_dms": formatar_dms(grau_no_signo),
        "nakshatra": NAKSHATRAS[indice_nakshatra],
        "numero_do_nakshatra": indice_nakshatra + 1,
        "regente_do_nakshatra": REGENTES_NAKSHATRAS[indice_nakshatra],
        "pada": pada,
        "signo_navamsa": navamsa[0],
    }


def _escolher_efemerides() -> int:
    """
    Decide qual "fonte de dados" do Swiss Ephemeris usar.

    * Se existirem arquivos .se1 na pasta ephe/, usa-os (máxima precisão).
    * Se não existirem, usa a efeméride Moshier, que já vem DENTRO da
      biblioteca (não precisa baixar nada). Precisão de cerca de 1 segundo
      de arco para os planetas, mais que suficiente para astrologia.
    """
    tem_arquivos = PASTA_EPHE.is_dir() and any(PASTA_EPHE.glob("*.se1"))
    if tem_arquivos:
        swe.set_ephe_path(str(PASTA_EPHE))
        return swe.FLG_SWIEPH
    return swe.FLG_MOSEPH


def _nome_efemeride(flag_retornada: int) -> str:
    if flag_retornada & swe.FLG_MOSEPH:
        return "Moshier (embutida na biblioteca)"
    if flag_retornada & swe.FLG_SWIEPH:
        return "Swiss Ephemeris (arquivos .se1)"
    return "outra"


# ---------------------------------------------------------------------------
# Cálculo principal
# ---------------------------------------------------------------------------
def calcular_mapa(dt_utc: datetime, latitude: float, longitude: float) -> dict:
    """
    Calcula Grahas, Ascendente e Casas para um instante (em UTC) e um lugar.

    dt_utc    : datetime com fuso UTC (aware)
    latitude  : graus, Norte positivo, Sul negativo
    longitude : graus, Leste positivo, Oeste negativo (ex.: São Paulo = -46.63)
    """
    if dt_utc.tzinfo is None:
        raise ErroCalculo("O horário precisa estar em UTC (com fuso definido).")
    dt_utc = dt_utc.astimezone(timezone.utc)

    with _TRAVA:
        # 1) Configurações: zodíaco sideral com ayanamsa Lahiri
        swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
        flag_base = _escolher_efemerides()
        flags = flag_base | swe.FLG_SIDEREAL | swe.FLG_SPEED

        # 2) Dia Juliano (a "hora" que os astrônomos usam), a partir do UTC
        segundos = dt_utc.second + dt_utc.microsecond / 1e6
        _jd_et, jd_ut = swe.utc_to_jd(
            dt_utc.year, dt_utc.month, dt_utc.day,
            dt_utc.hour, dt_utc.minute, segundos,
            swe.GREG_CAL,
        )

        ayanamsa = swe.get_ayanamsa_ut(jd_ut)

        # 3) Grahas
        grahas = []
        flag_usada = flag_base
        rahu_lon = rahu_vel = None
        for nome, corpo in GRAHAS_SWE:
            try:
                resultado, flag_ret = swe.calc_ut(jd_ut, corpo, flags)
            except Exception as erro:  # erro vindo da biblioteca C
                raise ErroCalculo(f"Falha ao calcular {nome}: {erro}") from erro
            flag_usada = flag_ret
            lon, lat_ecl, _dist, vel_lon = (
                resultado[0], resultado[1], resultado[2], resultado[3]
            )
            if nome == "Rahu":
                rahu_lon, rahu_vel = lon, vel_lon
            grahas.append((nome, lon, lat_ecl, vel_lon))

        # Ketu = Rahu + 180° (sempre)
        grahas.append(("Ketu", (rahu_lon + 180.0) % 360.0, 0.0, rahu_vel))

        # 4) Ascendente (Lagna) em zodíaco sideral
        try:
            _cuspides, ascmc = swe.houses_ex(
                jd_ut, latitude, longitude, b"W", swe.FLG_SIDEREAL
            )
        except Exception as erro:
            raise ErroCalculo(
                "Não foi possível calcular o Ascendente para esta latitude "
                f"(locais muito próximos dos polos podem falhar). Detalhe: {erro}"
            ) from erro
        asc_lon = ascmc[0] % 360.0

    # --- A partir daqui são só contas simples (fora da trava) ---------------
    indice_signo_asc = int(asc_lon // 30)

    def casa_do_signo(indice_signo: int) -> int:
        """Whole Sign: casa 1 = signo do ascendente; depois segue em ordem."""
        return (indice_signo - indice_signo_asc) % 12 + 1

    lista_grahas = []
    for nome, lon, lat_ecl, vel in grahas:
        info = descrever_longitude(lon)
        eh_no_lunar = nome in ("Rahu", "Ketu")
        lista_grahas.append({
            "graha": nome,
            "nome_pt": NOMES_GRAHAS[nome],
            **info,
            "casa": casa_do_signo(info["numero_do_signo"] - 1),
            "retrogrado": True if eh_no_lunar else bool(vel < 0),
            "velocidade_graus_por_dia": round(vel, 6),
            "observacao": (
                "Nodo médio: movimento médio, sempre retrógrado."
                if eh_no_lunar else ""
            ),
        })

    # Posição (casa) de cada graha, para saber onde está o regente de cada casa
    casa_de = {g["graha"]: g["casa"] for g in lista_grahas}

    asc_info = descrever_longitude(asc_lon)
    ascendente = {
        "nome": "Lagna (Ascendente)",
        **asc_info,
        "casa": 1,
    }

    casas = []
    for n in range(1, 13):
        indice_signo = (indice_signo_asc + n - 1) % 12
        signo = SIGNOS[indice_signo]
        regente = signo[2]
        casas.append({
            "casa": n,
            "signo": signo[0],
            "signo_pt": signo[1],
            "numero_do_signo": indice_signo + 1,
            "inicio_longitude_sideral": indice_signo * 30,
            "regente_do_signo": regente,
            "regente_esta_na_casa": casa_de[regente],
            "grahas_na_casa": [
                g["graha"] for g in lista_grahas if g["casa"] == n
            ],
        })

    lua = next(g for g in lista_grahas if g["graha"] == "Chandra")
    sol = next(g for g in lista_grahas if g["graha"] == "Surya")
    resumo = {
        "lagna": f'{ascendente["signo"]} ({ascendente["signo_pt"]})',
        "signo_lunar_rashi": f'{lua["signo"]} ({lua["signo_pt"]})',
        "nakshatra_lunar": lua["nakshatra"],
        "pada_lunar": lua["pada"],
        "signo_solar": f'{sol["signo"]} ({sol["signo_pt"]})',
    }

    return {
        "jd_ut": round(jd_ut, 8),
        "ayanamsa_lahiri_graus": round(ayanamsa, 6),
        "efemeride_usada": _nome_efemeride(flag_usada),
        "resumo": resumo,
        "ascendente": ascendente,
        "grahas": lista_grahas,
        "casas": casas,
    }


# ---------------------------------------------------------------------------
# Montagem do JSON final
# ---------------------------------------------------------------------------
def gerar_json_mapa(
    nome: str,
    cidade_informada: str,
    local: dict,
    data_local,
    hora_local,
    momento: dict,
) -> dict:
    """
    Junta tudo em um único dicionário (que vira o JSON).

    local   : {"descricao", "latitude", "longitude", "origem"}
    momento : resultado de geolocalizacao.analisar_horario()
    """
    calculo = calcular_mapa(
        momento["dt_utc"], local["latitude"], local["longitude"]
    )

    avisos = list(momento.get("avisos", []))
    if not calculo["efemeride_usada"].startswith("Swiss"):
        avisos.append(
            "Foi usada a efeméride Moshier embutida (precisão ~1 segundo de arco "
            "para os planetas). Para precisão máxima, coloque os arquivos .se1 "
            "na pasta ephe/."
        )

    try:
        versao_swe = swe.version
    except AttributeError:
        versao_swe = "desconhecida"

    return {
        "metadados": {
            "aplicativo": "Astrologia Védica - trabalho universitário",
            "versao_aplicativo": APP_VERSAO,
            "gerado_em_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "biblioteca_astronomica": f"PySwissEph / Swiss Ephemeris {versao_swe}",
            "efemeride_usada": calculo["efemeride_usada"],
        },
        "configuracao": {
            **CONFIGURACAO_TEXTO,
            "valor_ayanamsa_lahiri_graus": calculo["ayanamsa_lahiri_graus"],
        },
        "pessoa": {"nome": nome},
        "nascimento": {
            "data_local": data_local.isoformat(),
            "hora_local": hora_local.strftime("%H:%M:%S"),
            "cidade_informada": cidade_informada,
            "local_encontrado": local["descricao"],
            "origem_das_coordenadas": local.get("origem", ""),
            "latitude": round(local["latitude"], 6),
            "longitude": round(local["longitude"], 6),
            "fuso_horario": momento["nome_fuso"],
            "deslocamento_utc": momento["offset_texto"],
            "horario_de_verao": momento["horario_verao"],
            "data_hora_utc": momento["dt_utc"].strftime("%Y-%m-%dT%H:%M:%SZ"),
            "dia_juliano_ut": calculo["jd_ut"],
        },
        "resumo": calculo["resumo"],
        "ascendente": calculo["ascendente"],
        "grahas": calculo["grahas"],
        "casas": calculo["casas"],
        "avisos": avisos,
    }
