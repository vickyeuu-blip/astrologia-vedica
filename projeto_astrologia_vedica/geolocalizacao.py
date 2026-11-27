"""
geolocalizacao.py
=================
Descobre latitude/longitude de uma cidade e o fuso horário VÁLIDO NA DATA
do nascimento (incluindo horário de verão da época).

Ferramentas gratuitas usadas:
  * geopy + Nominatim (dados do OpenStreetMap) -> cidade -> latitude/longitude
  * timezonefinder                              -> latitude/longitude -> nome do fuso
  * zoneinfo (já vem no Python) + tzdata        -> regras históricas de cada fuso

Sobre o "fuso histórico":
  O banco de dados IANA tz (usado pelo zoneinfo) guarda as mudanças de fuso e
  de horário de verão de cada região ao longo do tempo. É muito bom para
  datas recentes, mas ANTES DE 1970 ele pode ser impreciso em algumas regiões.
  Por isso o programa mostra o fuso encontrado e permite correção manual.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from constantes import USER_AGENT


class ErroLocalizacao(Exception):
    """Erro com mensagem amigável para mostrar na tela."""


# ---------------------------------------------------------------------------
# 1) Cidade -> latitude e longitude
# ---------------------------------------------------------------------------
def buscar_locais(consulta: str, limite: int = 5) -> list[dict]:
    """
    Procura a cidade no OpenStreetMap (Nominatim) e devolve até `limite`
    candidatos, para o usuário escolher o correto.
    """
    from geopy.exc import GeocoderServiceError, GeocoderTimedOut, GeocoderUnavailable
    from geopy.geocoders import Nominatim

    consulta = consulta.strip()
    if not consulta:
        raise ErroLocalizacao("Digite o nome da cidade.")

    geolocalizador = Nominatim(user_agent=USER_AGENT, timeout=10)
    try:
        resultados = geolocalizador.geocode(
            consulta, exactly_one=False, limit=limite, language="pt"
        )
    except (GeocoderTimedOut, GeocoderUnavailable):
        raise ErroLocalizacao(
            "O serviço de busca de cidades não respondeu. Verifique a internet "
            "e tente de novo em alguns segundos."
        )
    except GeocoderServiceError as erro:
        raise ErroLocalizacao(f"O serviço de busca recusou o pedido: {erro}")

    if not resultados:
        return []
    return [
        {
            "descricao": r.address,
            "latitude": float(r.latitude),
            "longitude": float(r.longitude),
        }
        for r in resultados
    ]


# ---------------------------------------------------------------------------
# 2) Latitude/longitude -> nome do fuso (ex.: "America/Sao_Paulo")
# ---------------------------------------------------------------------------
_buscador_de_fuso = None


def descobrir_fuso(latitude: float, longitude: float) -> str:
    global _buscador_de_fuso
    if _buscador_de_fuso is None:
        from timezonefinder import TimezoneFinder

        _buscador_de_fuso = TimezoneFinder()
    nome = _buscador_de_fuso.timezone_at(lat=latitude, lng=longitude)
    if not nome:
        raise ErroLocalizacao(
            "Não consegui identificar o fuso horário para estas coordenadas. "
            "Use a opção avançada para informar o fuso manualmente."
        )
    return nome


# ---------------------------------------------------------------------------
# 3) Horário local + fuso da época -> horário UTC
# ---------------------------------------------------------------------------
def formatar_offset(delta: timedelta) -> str:
    total = int(delta.total_seconds())
    sinal = "+" if total >= 0 else "-"
    total = abs(total)
    horas, resto = divmod(total, 3600)
    minutos, segundos = divmod(resto, 60)
    texto = f"UTC{sinal}{horas:02d}:{minutos:02d}"
    if segundos:
        texto += f":{segundos:02d}"
    return texto


def analisar_horario(
    data: date,
    hora: time,
    nome_fuso: str | None = None,
    offset_manual_horas: float | None = None,
    ocorrencia: str = "primeira",
) -> dict:
    """
    Converte o horário local de nascimento em UTC, usando as regras do fuso
    que valiam NAQUELA data.

    Retorna um dicionário com:
      status        : "ok", "ambiguo" ou "inexistente"
      dt_utc        : datetime em UTC (None se o horário não existiu)
      nome_fuso, offset_texto, horario_verao, avisos

    Casos especiais de horário de verão:
      * "ambiguo"    : quando o relógio é atrasado, o mesmo horário ocorre duas
                       vezes. `ocorrencia` = "primeira" (ainda em horário de
                       verão) ou "segunda" (já em horário padrão).
      * "inexistente": quando o relógio é adiantado, certos horários nunca
                       existiram naquele dia.
    """
    ingenuo = datetime.combine(data, hora)  # sem fuso ainda
    avisos: list[str] = []

    # --- Caso 1: deslocamento UTC informado manualmente -------------------
    if offset_manual_horas is not None:
        delta = timedelta(hours=offset_manual_horas)
        local_com_fuso = ingenuo.replace(tzinfo=timezone(delta))
        return {
            "status": "ok",
            "dt_utc": local_com_fuso.astimezone(timezone.utc),
            "nome_fuso": "manual",
            "offset_texto": formatar_offset(delta),
            "horario_verao": False,
            "avisos": ["Deslocamento UTC informado manualmente pelo usuário."],
        }

    # --- Caso 2: fuso pelo nome (banco IANA) ------------------------------
    if not nome_fuso:
        raise ErroLocalizacao("Fuso horário não informado.")
    try:
        zona = ZoneInfo(nome_fuso)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        raise ErroLocalizacao(
            f'Fuso horário "{nome_fuso}" não encontrado. Exemplo válido: '
            "America/Sao_Paulo. (No Windows, confirme que o pacote 'tzdata' "
            "está instalado.)"
        )

    primeira = ingenuo.replace(tzinfo=zona, fold=0)
    segunda = ingenuo.replace(tzinfo=zona, fold=1)

    status = "ok"
    if primeira.utcoffset() != segunda.utcoffset():
        # Há uma mudança de relógio nesse horário. Vamos descobrir qual:
        # ida e volta (local -> UTC -> local). Se o horário não "volta" igual,
        # ele nunca existiu (relógio adiantado).
        volta = primeira.astimezone(timezone.utc).astimezone(zona).replace(tzinfo=None)
        status = "inexistente" if volta != ingenuo else "ambiguo"

    if status == "inexistente":
        return {
            "status": status,
            "dt_utc": None,
            "nome_fuso": nome_fuso,
            "offset_texto": "",
            "horario_verao": False,
            "avisos": [
                "Este horário local não existiu nesta data (o relógio foi "
                "adiantado pelo horário de verão). Confira o horário."
            ],
        }

    escolhido = segunda if (status == "ambiguo" and ocorrencia == "segunda") else primeira
    if status == "ambiguo":
        avisos.append(
            "Este horário ocorreu duas vezes (fim do horário de verão). Foi "
            f"usada a {'segunda' if ocorrencia == 'segunda' else 'primeira'} ocorrência."
        )

    if data.year < 1970:
        avisos.append(
            "Data anterior a 1970: o banco de fusos IANA pode ser impreciso "
            "para algumas regiões. Confira o fuso/horário de verão da época."
        )

    offset = escolhido.utcoffset()
    return {
        "status": status,
        "dt_utc": escolhido.astimezone(timezone.utc),
        "nome_fuso": nome_fuso,
        "offset_texto": formatar_offset(offset),
        "horario_verao": bool(escolhido.dst()),
        "avisos": avisos,
    }
