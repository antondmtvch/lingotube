# lingotube

![version](https://img.shields.io/badge/version-0.1.0-blue)
![python](https://img.shields.io/badge/python-%E2%89%A53.14-3776AB?logo=python&logoColor=white)
![coverage cli](https://img.shields.io/badge/coverage_cli-96%25-brightgreen)
![coverage extension](https://img.shields.io/badge/coverage_extension-99%25-brightgreen)

[English](../../README.md) · [Русский](README.ru.md) · [简体中文](README.zh-Hans.md) · [繁體中文](README.zh-Hant.md) · [हिन्दी](README.hi.md) · [Español](README.es.md) · [Français](README.fr.md) · [العربية](README.ar.md) · [বাংলা](README.bn.md) · **Português** · [ไทย](README.th.md) · [日本語](README.ja.md) · [Tiếng Việt](README.vi.md) · [Deutsch](README.de.md)

O lingotube obtém as legendas, a transcrição e o resumo de um vídeo do YouTube. O projeto tem três partes: uma ferramenta de linha de comando, um skill para agentes de IA e uma extensão de navegador (em desenvolvimento) que mostra legendas traduzidas sobre o player.
O texto vem do chat integrado do YouTube («Perguntar», Gemini) na página do vídeo.
Todas as solicitações são feitas em nome da sua conta do YouTube.

> [!WARNING]
> A ferramenta usa uma solicitação do chat do YouTube **interna e não documentada**. O YouTube pode
> alterá-la sem aviso, e a ferramenta deixará de funcionar até ser atualizada. Os Termos de Serviço
> do YouTube não permitem acesso automatizado: você usa a ferramenta por sua conta e risco.
> As solicitações são enviadas uma a uma, com uma pausa entre elas, mas não há garantia de que a sua
> conta não será restringida.

> [!NOTE]
> As perguntas e respostas ficam no histórico de chat da sua conta. O chat não está disponível
> na Rússia nem na maior parte da UE, nem em alguns vídeos.

**Sumário**

- [O que está incluído](#o-que-está-incluído)
- [Ferramenta de linha de comando (CLI)](#ferramenta-de-linha-de-comando-cli)
  - [Recursos](#recursos)
  - [Instalação](#instalação)
  - [Início rápido](#início-rápido)
  - [Comandos](#comandos)
  - [Cookies e login](#cookies-e-login)
  - [Modos de tradução](#modos-de-tradução)
  - [Códigos de saída](#códigos-de-saída)
- [Skill para agentes de IA](#skill-para-agentes-de-ia)
- [Extensão de navegador](#extensão-de-navegador)
- [Limitações](#limitações)
- [Desenvolvimento](#desenvolvimento)

## O que está incluído

| Componente | O que faz |
|---|---|
| [Ferramenta de linha de comando (CLI)](#ferramenta-de-linha-de-comando-cli) | O comando `lingotube`: obtém as legendas, a transcrição e o resumo de um vídeo como arquivos ou JSON. |
| [Skill para agentes de IA](#skill-para-agentes-de-ia) | Permite que um agente de IA (Claude Code, Codex, Cursor e outros) resuma um vídeo, gere uma transcrição ou legendas e encontre um momento pela descrição. Ele executa a ferramenta de linha de comando. |
| [Extensão de navegador](#extensão-de-navegador) | Legendas traduzidas sobre o player do YouTube, em qualquer idioma. Em desenvolvimento. |

## Ferramenta de linha de comando (CLI)

Tudo nesta seção trata do comando `lingotube`. O skill e a extensão têm suas próprias seções mais abaixo.

### Recursos

- **Legendas** em qualquer idioma, nos formatos `srt`, `vtt` e `json`.
- **Transcrição** no idioma original com marcações de tempo.
- **Resumo** do vídeo.
- **Três modos de tradução**: o chat integrado do YouTube, o seu próprio modelo com uma API compatível com OpenAI,
  ou um agente de IA que traduz a transcrição por conta própria.
- **Cache e retomada**: vídeos longos são processados em partes e, após uma falha, o trabalho continua de onde parou.
- **Saída legível por máquina** com `--json` para scripts e agentes de IA.

### Instalação

Você precisa do [uv](https://docs.astral.sh/uv/). O uv baixa por conta própria a versão certa do Python.

```sh
uv tool install git+https://github.com/antondmtvch/lingotube
```

Ou a partir de uma cópia local do repositório:

```sh
uv tool install .
```

Atualizar e desinstalar:

```sh
uv tool upgrade lingotube
uv tool uninstall lingotube
```

### Início rápido

1. Entre no YouTube. No Chrome ou no Edge, o mais simples é:

   ```sh
   lingotube login
   ```

   Abre-se uma janela do navegador com um perfil separado do lingotube. Entre na sua conta e **feche a
   janela do navegador**: o comando espera você fechá-la. No Firefox, basta entrar no YouTube como de costume.

2. Verifique se tudo está pronto:

   ```sh
   lingotube doctor
   ```

   O `doctor` verifica as fontes de cookies, o login na conta e a disponibilidade do chat em um vídeo de teste.
   Ele apenas abre o chat e não escreve nada nele.

3. Obtenha as legendas:

   ```sh
   lingotube subs https://www.youtube.com/watch?v=XXXXXXXXXXX --lang pt
   ```

### Comandos

| Comando | O que faz |
|---|---|
| `lingotube subs <link> --lang pt` | Cria um arquivo de legendas no idioma escolhido. |
| `lingotube summary <link> --lang pt` | Mostra um resumo no idioma escolhido. |
| `lingotube transcript <link>` | Gera uma transcrição no idioma original com marcações de tempo (JSON por padrão). |
| `lingotube build <link> --lang pt --from <arquivo>` | Recebe uma tradução pronta, confere com o original e monta as legendas. |
| `lingotube login [--browser chrome\|edge]` | Abre uma janela de login no YouTube e salva os cookies. |
| `lingotube logout` | Remove o perfil de login e os cookies salvos. |
| `lingotube doctor` | Verifica se tudo está pronto: cookies, login na conta e chat em um vídeo de teste. |

`<link>` é qualquer link de vídeo do YouTube ou um ID de vídeo.

Opções principais:

- `--lang <código>` — idioma do resultado (`ru`, `en`, `es` etc.). Sem ela, o idioma vem das configurações.
- `--format srt|vtt|json` — formato das legendas, `srt` por padrão.
- `-o <caminho>` — onde gravar o resultado. Com `-o -`, o resultado vai para a saída padrão.
- `--offset <segundos>` — desloca todas as legendas; números decimais e negativos são aceitos.
- `--cookies-file <caminho>` / `--browser <nome>` — fonte dos cookies.
- `--no-cache` — não usar o cache.
- `--json` — um único documento JSON `{"ok", "result", "warnings", "error"}`.

Um ID que começa com hífen deve ser passado depois de `--`:

```sh
lingotube subs --lang pt -- -n5MqamatXE
```

### Cookies e login

A ferramenta usa a primeira fonte adequada nesta ordem:

1. Um arquivo `cookies.txt`: a opção `--cookies-file`, a variável `LINGOTUBE_COOKIES_FILE` ou o caminho das configurações.
2. Um navegador escolhido explicitamente: a opção `--browser` ou `browser` nas configurações.
3. O perfil de login do lingotube, se foi criado por `lingotube login`.
4. Caso contrário, Firefox, Chrome, Edge e Brave são testados em sequência.

No Windows, o Chrome e o Edge protegem seus cookies, e eles normalmente não podem ser lidos diretamente.
Para eles, use `lingotube login`. Exportar um arquivo continua sendo uma alternativa.

> [!CAUTION]
> O arquivo `cookies.txt` dá acesso à sua conta. Guarde-o como uma senha e não o coloque
> em repositórios nem em pastas compartilhadas. Cookies, tokens e cabeçalhos de autorização
> nunca aparecem na saída, nas mensagens de erro nem no `--json`: `***` é exibido no lugar.

Se os cookies deixarem de funcionar (código de saída `4`), execute `lingotube login` de novo ou exporte um arquivo novo.

### Modos de tradução

| Modo | Quando está ativo | Quem traduz |
|---|---|---|
| **Chat** (padrão) | nada está configurado | o chat do YouTube devolve o texto já no idioma desejado |
| **Modelo próprio** | a seção `[translator]` está definida nas configurações | o seu modelo com uma API compatível com OpenAI |
| **Agente** | `transcript` → tradução → `build` | um agente de IA ou você, manualmente; o lingotube apenas confere a tradução e monta as legendas |

As configurações ficam em `settings.toml`:

- Windows: `%LOCALAPPDATA%\lingotube\settings.toml`
- macOS: `~/Library/Application Support/lingotube/settings.toml`
- Linux: `~/.config/lingotube/settings.toml`

Exemplo do modo «modelo próprio»:

```toml
lang = "pt"

[translator]
base_url = "https://api.openai.com/v1"   # ou um modelo local, p. ex. http://127.0.0.1:11434/v1
model = "gpt-4o-mini"
api_key_env = "LINGOTUBE_API_KEY"        # nome da variável de ambiente com a chave
batch_size = 40
```

A chave nunca é gravada no arquivo de configurações: a ferramenta a lê apenas da variável de ambiente.

Modo «agente»:

```sh
lingotube transcript <link> -o orig.json          # o original em JSON
# traduza o campo text de cada linha sem alterar id nem tempo e salve como pt.json
lingotube build <link> --lang pt --from pt.json   # verificação e montagem das legendas
```

> [!TIP]
> Para manter a tradução literal, use o modo «modelo próprio» ou «agente»: eles obtêm primeiro
> o original, e a tradução é conferida pelos números das linhas. O chat pode parafrasear ou juntar frases.

### Códigos de saída

| Código | Significado |
|---|---|
| `0` | Sucesso. |
| `1` | Outro erro. |
| `2` | Opções de comando inválidas. |
| `3` | O chat está indisponível para este vídeo ou conta. |
| `4` | Problema de login: cookies não encontrados ou expirados, ou a chave do modelo não foi definida. |
| `5` | Resultado incompleto: o arquivo foi gravado, mas a transcrição não chega ao fim do vídeo. |
| `6` | Falha de rede após esgotar as tentativas. |
| `7` | Os dados não passaram na validação. |
| `130` | Interrompido pelo usuário (Ctrl+C). |

## Skill para agentes de IA

O skill executa a [ferramenta de linha de comando](#ferramenta-de-linha-de-comando-cli) pelo agente, então instale primeiro a ferramenta e depois o skill.


O repositório tem um skill no formato aberto Agent Skills. Com ele, um agente de IA (Claude Code, Codex,
Cursor, Gemini CLI e outros) resume vídeos, gera transcrições e legendas, encontra
um momento pela descrição e ajuda com a instalação e o login.

```sh
npx skills add antondmtvch/lingotube
```

Sem Node.js, copie a pasta `skills/lingotube/` para a pasta de skills do seu agente
(`~/.claude/skills/` para o Claude Code ou `~/.agents/skills/` para a maioria dos outros).

## Extensão de navegador

Uma extensão Manifest V3 para Chrome, Edge e Firefox que mostra legendas traduzidas sobre o player do YouTube. Ela está em desenvolvimento.

- Um botão no player ativa as legendas; o painel com o texto pode ser arrastado.
- Você escolhe um entre 30 idiomas ou digita o seu.
- O tempo e o texto original vêm das próprias legendas do YouTube; o chat apenas as traduz.
- Funciona no navegador em que você já está logado no YouTube, então não é preciso configurar cookies.

Ela ainda não está em nenhuma loja. Baixe os arquivos para o seu navegador na [página de versões](https://github.com/antondmtvch/lingotube/releases):

- Chrome: baixe `lingotube-<versão>-chromium.zip` e descompacte em uma pasta que você vá manter. Abra `chrome://extensions`, ative o «Modo do desenvolvedor», clique em «Carregar sem compactação» e escolha essa pasta. O Chrome avisa na inicialização sobre extensões em modo de desenvolvedor. Para atualizar, substitua os arquivos da pasta e clique no botão de recarregar no cartão da extensão.
- Edge: use o mesmo arquivo. Abra `edge://extensions`, ative o «Modo do desenvolvedor», clique em «Carregar descompactada» e escolha a pasta.
- Firefox 128 ou mais recente: baixe `lingotube-<versão>-firefox.xpi`, arraste o arquivo para a janela do Firefox (ou abra `about:addons`, clique no ícone de engrenagem e escolha «Instalar extensão a partir de arquivo…») e confirme a instalação.

Brave, Opera e Vivaldi não foram testados.

## Limitações

Estas limitações valem para os três componentes, porque todos dependem do chat do YouTube.


- O chat funciona apenas para usuários logados com mais de 13 anos, não está disponível em todos os países
  e não existe em todos os vídeos.
- Contas de marca não são compatíveis: usa-se a conta principal do navegador.
- Uma hora de vídeo leva vários minutos: as solicitações vão uma a uma.
- O tempo das linhas é definido pelo chat. Em vídeos longos, algumas linhas podem se desviar alguns
  segundos; um deslocamento constante é corrigido com a opção `--offset`.
- O texto de vídeos longos não é garantidamente literal: o chat às vezes responde com um texto
  de sentido próximo, e a ferramenta não percebe isso. Para usos importantes, confira o resultado com a gravação.
- Não há suporte a proxy.

## Desenvolvimento

As dependências e o ambiente são gerenciados com o uv:

```sh
uv sync
uv run pytest
uv run ruff check
```

Cobertura de testes (os valores dos selos acima foram medidos com estes comandos e são atualizados manualmente):

```sh
uv run --with pytest-cov pytest --cov=lingotube
cd extension && node --test --experimental-test-coverage --test-coverage-exclude='tests/**' tests/
```

Estrutura do projeto:

- `src/lingotube/` — o núcleo: CLI, autorização, chat, tradução, cache e gravação de resultados.
- `skills/lingotube/` — o skill para agentes de IA.
- `extension/` — a extensão de navegador.
- `tests/` — testes em Python, `probe/` — sondagens manuais de solicitações ao YouTube.
- `docs/readme/` — traduções deste README.
