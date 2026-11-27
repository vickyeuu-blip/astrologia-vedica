"""
testar_calculos.py
==================
Verificações automáticas para você confirmar que a instalação está correta
ANTES de abrir o site. Rode no terminal:

    python testar_calculos.py            (testes offline)
    python testar_calculos.py --rede     (inclui a busca de cidade na internet)

Os valores de referência são fatos astronômicos conhecidos do instante
J2000 (01/01/2000, 12:00 UT):
  * Ayanamsa Lahiri ........ ~23,85°
  * Longitude TROPICAL do Sol ~280,37°  -> sideral ~256,52°
  * Nodo lunar médio (tropical) ~125,04° -> sideral ~101,19°
Se algum teste falhar, NÃO use os resultados do site e confira a instalação.
"""

import sys
from datetime import date, datetime, time, timezone

falhas = []


def verificar(descricao: str, condicao: bool, detalhe: str = ""):
    if condicao:
        print(f"  [OK]    {descricao}")
    else:
        print(f"  [FALHA] {descricao}  {detalhe}")
        falhas.append(descricao)


def perto(a: float, b: float, tolerancia: float) -> bool:
    diferenca = abs((a - b + 180) % 360 - 180)  # diferença angular circular
    return diferenca <= tolerancia


print("\n1) Regras de signo / nakshatra / pada")
from astrologia import calcular_mapa, descrever_longitude  # noqa: E402

d = descrever_longitude(0.0)
verificar("0° = Mesha, Ashwini, pada 1", (d["signo"], d["nakshatra"], d["pada"]) == ("Mesha", "Ashwini", 1))
d = descrever_longitude(3.4)
verificar("3°24' = Ashwini pada 2", (d["nakshatra"], d["pada"]) == ("Ashwini", 2))
d = descrever_longitude(13.34)
verificar("13°20'+ = Bharani pada 1", (d["nakshatra"], d["pada"]) == ("Bharani", 1))
d = descrever_longitude(359.99)
verificar("359°59' = Meena, Revati, pada 4", (d["signo"], d["nakshatra"], d["pada"]) == ("Meena", "Revati", 4))
d = descrever_longitude(30.0)
verificar("30° = Vrishabha (início do 2º signo)", d["signo"] == "Vrishabha")
d = descrever_longitude(40.0)
verificar("40° = início de Rohini (4º nakshatra, 27 no total)", d["nakshatra"] == "Rohini" and d["pada"] == 1)

print("\n2) Cálculo astronômico real (J2000, São Paulo)")
instante = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
mapa = calcular_mapa(instante, -23.55, -46.63)
sol = next(g for g in mapa["grahas"] if g["graha"] == "Surya")
rahu = next(g for g in mapa["grahas"] if g["graha"] == "Rahu")
ketu = next(g for g in mapa["grahas"] if g["graha"] == "Ketu")

verificar("Ayanamsa Lahiri ~23,85°", abs(mapa["ayanamsa_lahiri_graus"] - 23.85) < 0.03,
          f'(obtido {mapa["ayanamsa_lahiri_graus"]})')
verificar("Sol sideral ~256,52°", perto(sol["longitude_sideral"], 256.52, 0.1),
          f'(obtido {sol["longitude_sideral"]})')
verificar("Rahu (nodo médio) sideral ~101,19°", perto(rahu["longitude_sideral"], 101.19, 0.1),
          f'(obtido {rahu["longitude_sideral"]})')
verificar("Ketu = Rahu + 180°", perto(ketu["longitude_sideral"], rahu["longitude_sideral"] + 180, 0.001))
verificar("Existem 9 grahas e 12 casas", len(mapa["grahas"]) == 9 and len(mapa["casas"]) == 12)

asc = mapa["ascendente"]
verificar("Casa 1 = signo do Ascendente (Whole Sign)", mapa["casas"][0]["numero_do_signo"] == asc["numero_do_signo"])
coerente = all(
    g["casa"] == (g["numero_do_signo"] - asc["numero_do_signo"]) % 12 + 1 for g in mapa["grahas"]
)
verificar("Casa de cada graha coerente com o Ascendente", coerente)
print(f'  Ascendente neste teste: {asc["grau_no_signo_dms"]} de {asc["signo"]}; '
      f'efeméride: {mapa["efemeride_usada"]}')

print("\n3) Fuso horário histórico (banco IANA)")
from geolocalizacao import analisar_horario  # noqa: E402

m = analisar_horario(date(2000, 1, 15), time(12, 0), "America/Sao_Paulo")
verificar("São Paulo, jan/2000: UTC-02:00 com horário de verão", m["offset_texto"] == "UTC-02:00" and m["horario_verao"],
          f'(obtido {m["offset_texto"]})')
m = analisar_horario(date(2019, 7, 1), time(12, 0), "America/Sao_Paulo")
verificar("São Paulo, jul/2019: UTC-03:00 sem horário de verão", m["offset_texto"] == "UTC-03:00" and not m["horario_verao"])
m = analisar_horario(date(2018, 11, 4), time(0, 30), "America/Sao_Paulo")
verificar("04/11/2018 00:30 em São Paulo não existiu", m["status"] == "inexistente")
m = analisar_horario(date(2018, 2, 17), time(23, 30), "America/Sao_Paulo")
verificar("17/02/2018 23:30 em São Paulo é ambíguo", m["status"] == "ambiguo")
m = analisar_horario(date(2000, 1, 1), time(9, 0), None, offset_manual_horas=-3)
verificar("Deslocamento manual -3h: 09:00 -> 12:00 UTC", m["dt_utc"].hour == 12)

if "--rede" in sys.argv:
    print("\n4) Busca de cidade na internet (Nominatim)")
    from geolocalizacao import buscar_locais, descobrir_fuso  # noqa: E402

    achados = buscar_locais("São Paulo, Brasil")
    verificar("Encontrou São Paulo perto de (-23,55; -46,63)",
              bool(achados) and abs(achados[0]["latitude"] + 23.55) < 0.5
              and abs(achados[0]["longitude"] + 46.63) < 0.5)
    if achados:
        verificar("Fuso de São Paulo = America/Sao_Paulo",
                  descobrir_fuso(achados[0]["latitude"], achados[0]["longitude"]) == "America/Sao_Paulo")

print()
if falhas:
    print(f"RESULTADO: {len(falhas)} teste(s) falharam.")
    sys.exit(1)
print("RESULTADO: todos os testes passaram. Pode abrir o site.")
