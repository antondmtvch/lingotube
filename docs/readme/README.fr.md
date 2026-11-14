# lingotube

![version](https://img.shields.io/badge/version-0.1.0-blue)
![extension release](https://img.shields.io/github/v/release/antondmtvch/lingotube?filter=extension-v*&label=extension)
![python](https://img.shields.io/badge/python-%E2%89%A53.14-3776AB?logo=python&logoColor=white)
![coverage cli](https://img.shields.io/badge/coverage_cli-96%25-brightgreen)
![coverage extension](https://img.shields.io/badge/coverage_extension-99%25-brightgreen)

[English](/README.md) · [Русский](/docs/readme/README.ru.md) · [简体中文](/docs/readme/README.zh-Hans.md) · [繁體中文](/docs/readme/README.zh-Hant.md) · [हिन्दी](/docs/readme/README.hi.md) · [Español](/docs/readme/README.es.md) · **Français** · [العربية](/docs/readme/README.ar.md) · [বাংলা](/docs/readme/README.bn.md) · [Português](/docs/readme/README.pt.md) · [ไทย](/docs/readme/README.th.md) · [日本語](/docs/readme/README.ja.md) · [Tiếng Việt](/docs/readme/README.vi.md) · [Deutsch](/docs/readme/README.de.md)

lingotube récupère les sous-titres, la transcription et le résumé d'une vidéo YouTube. Le projet se compose de trois parties : un outil en ligne de commande, un skill pour agents IA et une extension de navigateur (en développement) qui affiche des sous-titres traduits sur le lecteur.
Le texte provient du chat intégré de YouTube (« Poser une question », Gemini) sur la page de la vidéo.
Toutes les requêtes sont faites au nom de votre compte YouTube.

> [!WARNING]
> L'outil utilise une requête du chat YouTube **interne et non documentée**. YouTube peut la modifier
> sans préavis, et l'outil cessera alors de fonctionner jusqu'à sa mise à jour. Les Conditions
> d'utilisation de YouTube n'autorisent pas l'accès automatisé : vous utilisez l'outil à vos risques.
> Les requêtes sont envoyées une par une, avec une pause entre elles, mais rien ne garantit que votre
> compte ne sera pas restreint.

> [!NOTE]
> Les questions et les réponses restent dans l'historique du chat de votre compte. Le chat n'est pas
> disponible en Russie ni dans la plupart des pays de l'UE, ni sous certaines vidéos.

**Sommaire**

- [Contenu du projet](#contenu-du-projet)
- [Outil en ligne de commande (CLI)](#outil-en-ligne-de-commande-cli)
  - [Fonctionnalités](#fonctionnalités)
  - [Installation](#installation)
  - [Démarrage rapide](#démarrage-rapide)
  - [Commandes](#commandes)
  - [Cookies et connexion](#cookies-et-connexion)
  - [Modes de traduction](#modes-de-traduction)
  - [Codes de sortie](#codes-de-sortie)
- [Skill pour agents IA](#skill-pour-agents-ia)
- [Extension de navigateur](#extension-de-navigateur)
- [Limites](#limites)
- [Développement](#développement)

## Contenu du projet

| Composant | Rôle |
|---|---|
| [Outil en ligne de commande (CLI)](#outil-en-ligne-de-commande-cli) | La commande `lingotube` : récupère les sous-titres, la transcription et le résumé d'une vidéo sous forme de fichiers ou de JSON. |
| [Skill pour agents IA](#skill-pour-agents-ia) | Permet à un agent IA (Claude Code, Codex, Cursor et d'autres) de résumer une vidéo, de produire une transcription ou des sous-titres et de retrouver un moment à partir d'une description. Il lance l'outil en ligne de commande. |
| [Extension de navigateur](#extension-de-navigateur) | Sous-titres traduits sur le lecteur YouTube, dans n'importe quelle langue. En développement. |

## Outil en ligne de commande (CLI)

Tout ce qui figure dans cette section concerne la commande `lingotube`. Le skill et l'extension ont leurs propres sections plus bas.

### Fonctionnalités

- **Sous-titres** dans toutes les langues, aux formats `srt`, `vtt` et `json`.
- **Transcription** dans la langue d'origine, avec les repères temporels.
- **Résumé** de la vidéo.
- **Trois modes de traduction** : le chat intégré de YouTube, votre propre modèle avec une API compatible OpenAI,
  ou un agent IA qui traduit lui-même la transcription.
- **Cache et reprise** : les longues vidéos sont traitées par parties, et après un échec le travail reprend là où il s'est arrêté.
- **Sortie lisible par machine** avec `--json` pour les scripts et les agents IA.

### Installation

Il vous faut [uv](https://docs.astral.sh/uv/). uv télécharge lui-même la bonne version de Python.

```sh
uv tool install git+https://github.com/antondmtvch/lingotube
```

Ou depuis une copie locale du dépôt :

```sh
uv tool install .
```

Mise à jour et désinstallation :

```sh
uv tool upgrade lingotube
uv tool uninstall lingotube
```

### Démarrage rapide

1. Connectez-vous à YouTube. Dans Chrome ou Edge, le plus simple est :

   ```sh
   lingotube login
   ```

   Une fenêtre de navigateur s'ouvre avec un profil lingotube distinct. Connectez-vous à votre compte et **fermez la
   fenêtre du navigateur** : la commande attend que vous la fermiez. Dans Firefox, il suffit de se connecter à YouTube comme d'habitude.

2. Vérifiez que tout est prêt :

   ```sh
   lingotube doctor
   ```

   `doctor` vérifie les sources de cookies, la connexion au compte et la disponibilité du chat sur une vidéo de test.
   Il ne fait qu'ouvrir le chat et n'y écrit rien.

3. Récupérez les sous-titres :

   ```sh
   lingotube subs https://www.youtube.com/watch?v=XXXXXXXXXXX --lang fr
   ```

### Commandes

| Commande | Ce qu'elle fait |
|---|---|
| `lingotube subs <lien> --lang fr` | Crée un fichier de sous-titres dans la langue choisie. |
| `lingotube summary <lien> --lang fr` | Affiche un résumé dans la langue choisie. |
| `lingotube transcript <lien>` | Produit une transcription dans la langue d'origine avec repères temporels (JSON par défaut). |
| `lingotube build <lien> --lang fr --from <fichier>` | Prend une traduction toute faite, la compare à l'original et construit les sous-titres. |
| `lingotube login [--browser chrome\|edge]` | Ouvre une fenêtre de connexion à YouTube et enregistre les cookies. |
| `lingotube logout` | Supprime le profil de connexion et les cookies enregistrés. |
| `lingotube doctor` | Vérifie que tout est prêt : cookies, connexion au compte et chat sur une vidéo de test. |

`<lien>` est n'importe quel lien vers une vidéo YouTube ou un identifiant de vidéo.

Options principales :

- `--lang <code>` — langue du résultat (`ru`, `en`, `es`, etc.). Sans cette option, la langue vient des paramètres.
- `--format srt|vtt|json` — format des sous-titres, `srt` par défaut.
- `-o <chemin>` — où écrire le résultat. Avec `-o -`, le résultat va sur la sortie standard.
- `--offset <secondes>` — décale tous les sous-titres ; les nombres décimaux et négatifs sont acceptés.
- `--cookies-file <chemin>` / `--browser <nom>` — source des cookies.
- `--no-cache` — n'utilise pas le cache.
- `--json` — un seul document JSON `{"ok", "result", "warnings", "error"}`.

Un identifiant qui commence par un tiret se passe après `--` :

```sh
lingotube subs --lang fr -- -n5MqamatXE
```

### Cookies et connexion

L'outil prend la première source qui convient, dans cet ordre :

1. Un fichier `cookies.txt` : l'option `--cookies-file`, la variable `LINGOTUBE_COOKIES_FILE` ou le chemin des paramètres.
2. Un navigateur choisi explicitement : l'option `--browser` ou `browser` dans les paramètres.
3. Le profil de connexion lingotube, s'il a été créé par `lingotube login`.
4. Sinon, Firefox, Chrome, Edge et Brave sont essayés tour à tour.

Sous Windows, Chrome et Edge protègent leurs cookies, qui ne peuvent généralement pas être lus directement.
Pour eux, utilisez `lingotube login`. L'export d'un fichier reste une solution de secours.

> [!CAUTION]
> Le fichier `cookies.txt` donne accès à votre compte. Conservez-le comme un mot de passe et ne le placez
> ni dans des dépôts ni dans des dossiers partagés. Les cookies, jetons et en-têtes d'autorisation
> n'apparaissent jamais dans la sortie, les messages d'erreur ni `--json` : `***` est affiché à la place.

Si les cookies cessent de fonctionner (code de sortie `4`), relancez `lingotube login` ou exportez un nouveau fichier.

### Modes de traduction

| Mode | Quand il est actif | Qui traduit |
|---|---|---|
| **Chat** (par défaut) | rien n'est configuré | le chat YouTube renvoie directement le texte dans la langue voulue |
| **Modèle perso** | la section `[translator]` est définie dans les paramètres | votre modèle avec une API compatible OpenAI |
| **Agent** | `transcript` → traduction → `build` | un agent IA ou vous à la main ; lingotube se contente de vérifier la traduction et de construire les sous-titres |

Les paramètres se trouvent dans `settings.toml` :

- Windows : `%LOCALAPPDATA%\lingotube\settings.toml`
- macOS : `~/Library/Application Support/lingotube/settings.toml`
- Linux : `~/.config/lingotube/settings.toml`

Exemple du mode « modèle perso » :

```toml
lang = "fr"

[translator]
base_url = "https://api.openai.com/v1"   # ou un modèle local, p. ex. http://127.0.0.1:11434/v1
model = "gpt-4o-mini"
api_key_env = "LINGOTUBE_API_KEY"        # nom de la variable d'environnement contenant la clé
batch_size = 40
```

La clé n'est jamais écrite dans le fichier de paramètres : l'outil la lit uniquement depuis la variable d'environnement.

Mode « agent » :

```sh
lingotube transcript <lien> -o orig.json          # l'original en JSON
# traduisez le champ text de chaque ligne sans toucher à id ni au temps, puis enregistrez-le en fr.json
lingotube build <lien> --lang fr --from fr.json   # vérification et construction des sous-titres
```

> [!TIP]
> Pour garder une traduction littérale, utilisez le mode « modèle perso » ou « agent » : ils obtiennent d'abord
> l'original, et la traduction est vérifiée par numéros de ligne. Le chat peut paraphraser ou fusionner des phrases.

### Codes de sortie

| Code | Signification |
|---|---|
| `0` | Succès. |
| `1` | Autre erreur. |
| `2` | Options de commande invalides. |
| `3` | Le chat est indisponible pour cette vidéo ou ce compte. |
| `4` | Problème de connexion : cookies introuvables ou expirés, ou clé du modèle absente. |
| `5` | Résultat incomplet : le fichier est écrit, mais la transcription n'atteint pas la fin de la vidéo. |
| `6` | Échec réseau après épuisement des nouvelles tentatives. |
| `7` | Les données n'ont pas passé la validation. |
| `130` | Interrompu par l'utilisateur (Ctrl+C). |

## Skill pour agents IA

Le skill lance l'[outil en ligne de commande](#outil-en-ligne-de-commande-cli) pour l'agent : installez donc d'abord l'outil, puis le skill.


Le dépôt contient un skill au format ouvert Agent Skills. Avec lui, un agent IA (Claude Code, Codex,
Cursor, Gemini CLI et d'autres) résume des vidéos, produit des transcriptions et des sous-titres, retrouve
un moment à partir d'une description et aide à l'installation et à la connexion.

```sh
npx skills add antondmtvch/lingotube
```

Sans Node.js, copiez le dossier `skills/lingotube/` dans le dossier skills de votre agent
(`~/.claude/skills/` pour Claude Code ou `~/.agents/skills/` pour la plupart des autres).

## Extension de navigateur

Une extension Manifest V3 pour Chrome, Edge et Firefox qui affiche des sous-titres traduits sur le lecteur YouTube. Elle est en développement.

- Un bouton du lecteur active les sous-titres ; le panneau contenant le texte peut être déplacé.
- Vous choisissez parmi 30 langues ou tapez la vôtre.
- Le minutage et le texte d'origine viennent des sous-titres propres de YouTube ; le chat ne fait que les traduire.
- Elle fonctionne dans le navigateur où vous êtes déjà connecté à YouTube : aucune configuration des cookies n'est nécessaire.

Elle n'est pas encore dans une boutique. Téléchargez les fichiers pour votre navigateur depuis la [page des versions](https://github.com/antondmtvch/lingotube/releases) :

- Chrome : téléchargez `lingotube-<version>-chromium.zip` et décompressez-le dans un dossier que vous conserverez. Ouvrez `chrome://extensions`, activez le « Mode développeur », cliquez sur « Charger l'extension non empaquetée » et choisissez ce dossier. Au démarrage, Chrome vous rappelle les extensions en mode développeur. Pour mettre à jour, remplacez les fichiers du dossier et cliquez sur le bouton de rechargement de la carte de l'extension.
- Edge : utilisez la même archive. Ouvrez `edge://extensions`, activez le « Mode développeur », cliquez sur « Charger l'extension décompressée » et choisissez le dossier.
- Firefox 140 ou plus récent : téléchargez `lingotube-<version>-firefox.xpi`, glissez le fichier dans la fenêtre de Firefox (ou ouvrez `about:addons`, cliquez sur l'icône en forme de roue dentée et choisissez « Installer un module depuis un fichier… ») et confirmez l'installation.

Brave, Opera et Vivaldi n'ont pas été testés.

## Limites

Ces limites s'appliquent aux trois composants, car tous reposent sur le chat de YouTube.


- Le chat ne fonctionne que pour les utilisateurs connectés de plus de 13 ans, n'existe pas dans tous les pays
  et n'est pas présent sous toutes les vidéos.
- Les comptes de marque ne sont pas pris en charge : c'est le compte principal du navigateur qui est utilisé.
- Une heure de vidéo prend plusieurs minutes : les requêtes se font une par une.
- Le minutage des lignes est fixé par le chat. Sur les longues vidéos, certaines lignes peuvent dériver de quelques
  secondes ; un décalage constant se corrige avec l'option `--offset`.
- Le texte des longues vidéos n'est pas garanti mot pour mot : le chat répond parfois par un texte
  de sens proche, et l'outil ne le détecte pas. Pour les usages importants, vérifiez le résultat avec l'enregistrement.
- Le proxy n'est pas pris en charge.

## Développement

Les dépendances et l'environnement sont gérés avec uv :

```sh
uv sync
uv run pytest
uv run ruff check
```

Couverture des tests (les valeurs des badges ci-dessus ont été mesurées avec ces commandes et sont mises à jour à la main) :

```sh
uv run --with pytest-cov pytest --cov=lingotube
cd extension && node --test --experimental-test-coverage --test-coverage-exclude='tests/**' tests/
```

Structure du projet :

- `src/lingotube/` — le cœur : CLI, autorisation, chat, traduction, cache et écriture des résultats.
- `skills/lingotube/` — le skill pour agents IA.
- `extension/` — l'extension de navigateur.
- `tests/` — tests Python.
- `docs/readme/` — traductions de ce README.
