# Astrologia Védica com Python, Streamlit e PySwissEph

Site que recebe nome, data, horário e cidade de nascimento e calcula, com o
Swiss Ephemeris: os 9 Grahas, o Ascendente (Lagna), as 12 casas (Whole Sign),
os Nakshatras e os Padas. Zodíaco sideral, ayanamsa Lahiri, nodo lunar médio.
O resultado é organizado em JSON (visualização + download) e pode ser enviado
ao Gemini para interpretação.

## Estrutura de arquivos

```
projeto_astrologia_vedica/
├── app.py                    <- o site (interface Streamlit)
├── astrologia.py             <- cálculos com PySwissEph
├── geolocalizacao.py         <- cidade -> coordenadas -> fuso horário da época
├── gemini_interpretador.py   <- integração com a API do Gemini
├── constantes.py             <- signos, nakshatras, regentes
├── testar_calculos.py        <- verificação da instalação
├── requirements.txt          <- lista de bibliotecas
├── .gitignore
├── .streamlit/
│   └── secrets.toml.example  <- modelo para guardar a chave do Gemini
└── ephe/
    └── LEIA-ME.txt           <- pasta opcional para arquivos .se1
```

## Instalação (Windows, Prompt de Comando)

1. Instale o **Python 3.11** (python.org; no Windows use o instalador 3.11.9) e
   marque **"Add python.exe to PATH"**.
2. Abra o Prompt de Comando **dentro da pasta do projeto**
   (na barra de endereços do Explorador de Arquivos digite `cmd` e Enter).
3. Crie o ambiente virtual: `py -3.11 -m venv .venv`
4. Ative-o: `.venv\Scripts\activate.bat`  (deve aparecer `(.venv)` na linha)
5. Instale as bibliotecas: `pip install -r requirements.txt`
6. Verifique: `python testar_calculos.py`
7. Abra o site: `streamlit run app.py`

Mac/Linux: `python3.11 -m venv .venv`, `source .venv/bin/activate`, e os demais
comandos iguais.

## Chave do Gemini (opcional)

1. Gere uma chave gratuita em https://aistudio.google.com/apikey
2. Copie `.streamlit/secrets.toml.example` para `.streamlit/secrets.toml`
3. Troque `COLE_SUA_CHAVE_AQUI` pela sua chave.

Alternativa: colar a chave no campo da barra lateral do site.

## Solução de problemas

| Sintoma | Causa provável / solução |
|---|---|
| `error: Microsoft Visual C++ 14.0 ... is required` ao instalar | Python diferente do 3.11. Apague a pasta `.venv` e refaça os passos 3 a 5 com Python 3.11. |
| `'streamlit' não é reconhecido` | O ambiente virtual não está ativo (passo 4). |
| `ZoneInfoNotFoundError` | Rode `pip install tzdata`. |
| Busca de cidade não responde | Sem internet, ou o Nominatim limitou o uso. Espere e tente de novo. |
| Gemini erro 404 | Nome do modelo desatualizado: use "Listar modelos disponíveis" e troque na barra lateral. |
| Gemini erro 429 | Limite gratuito atingido: aguarde. |

## Licenças e uso responsável

| Componente | Licença |
|---|---|
| Swiss Ephemeris / PySwissEph | **AGPL-3.0** (ou licença comercial da Astrodienst) |
| Streamlit, google-genai, tzdata | Apache-2.0 |
| geopy, timezonefinder | MIT |
| pandas | BSD-3-Clause |
| Dados de cidades (Nominatim) | © colaboradores do OpenStreetMap, licença ODbL |

* **AGPL:** para um trabalho acadêmico local não há problema. Se você
  publicar o site na internet, precisa oferecer o código-fonte a quem o usar e
  manter a mesma licença. Para uso comercial fechado, compre a licença da
  Astrodienst.
* **Nominatim:** uso leve apenas (máx. 1 consulta/segundo). Edite
  `USER_AGENT` em `constantes.py` com o nome do seu projeto e seu e-mail.
* **Gemini (plano gratuito):** confira os termos atuais sobre uso dos dados
  enviados. O site não envia o nome nem o endereço completo.
* A astrologia não possui comprovação científica; apresente o trabalho como
  aplicação técnica (cálculo astronômico + IA), não como previsão.
