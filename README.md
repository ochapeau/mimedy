# 🗂️ mimedy

[![CI](https://github.com/ochapeau/mimedy/actions/workflows/ci.yml/badge.svg)](https://github.com/ochapeau/mimedy/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/ochapeau/mimedy/graph/badge.svg)](https://codecov.io/gh/ochapeau/mimedy)
[![PyPI](https://img.shields.io/pypi/v/mimedy)](https://pypi.org/project/mimedy/)
[![Python](https://img.shields.io/pypi/pyversions/mimedy)](https://pypi.org/project/mimedy/)

**Tidies up a messy folder by each file's real type, not by its extension.**\
**Range un dossier en désordre selon le vrai type de chaque fichier, pas selon son extension.**

*mimedy = **MIME** + **tidy**: each file's MIME type decides where it belongs.*\
*mimedy = **MIME** + **tidy** (ranger) : le type MIME de chaque fichier décide de sa place.*

[English](#english) · [Français](#français)

---

<a id="english"></a>

## 🇬🇧 English

**Contents:** [Why](#why) · [Features](#features) · [Installation](#installation) · [Usage](#usage) · [Configuration](#configuration) · [Ignored files](#ignored-files) · [How is a file classified](#how-is-a-file-classified) · [Project structure](#project-structure) · [Development](#development) · [Roadmap](#roadmap) · [License](#license)

### Why?

A `Downloads` folder always ends up looking the same: PDFs, screenshots, archives, a `.json` exported at some point, a file with no extension that nobody remembers…

Most organizing tools trust file extensions. But an extension can lie, be missing, or simply be wrong. **mimedy** uses [Magika](https://github.com/google/magika), Google's deep learning model that identifies a file **from its content**, to decide where it belongs.

```text
$ mimedy ~/Downloads
[INFO] Loaded config from /Users/me/.config/mimedy/config.yaml
[INFO] Organizing /Users/me/Downloads
[INFO] 'export.csv' → Data/
[INFO] 'holidays.jpg' → Photos/
[INFO] 'invoice' → PDF/
[INFO] 'report.pdf' → PDF/report (1).pdf
[INFO] 'script.py' → Python/
[WARNING] Skipped 'locked.txt': Magika could not read the file (permission_error)
[INFO] 5 files to move into 4 folders, 1 skipped, 0 ignored
Move 5 files? [y/N]: y
[INFO] Done: 5 moved, 0 failed
```

### Features

- 🧠 **Content-based detection**: Magika recognizes over 200 file types, even when renamed or missing an extension.
- 🔒 **100% local**: the AI model ships with the tool and runs on your machine. No network connection, no file or data is ever sent anywhere.
- 🪜 **Cascading rules**: hidden files, large files, extensions, MIME types, then the Magika group as a fallback.
- 📋 **Plan, then confirm**: every move is shown before it happens, and nothing moves without your approval. `--dry-run` stops at the plan.
- 🧯 **Robust**: an unreadable or locked file is reported and skipped, without stopping the run.
- 🙈 **System files ignored**: `.DS_Store`, `Thumbs.db`… stay where they are, and you can add your own patterns (`*.part`).
- 🛡️ **Never overwrites**: if `photo.jpg` already exists, the new file becomes `photo (1).jpg`.
- 🐛 **`--verbose` mode**: shows which rule decided each file's destination.
- ⚙️ **Simple YAML configuration**, entirely optional.

### Installation

mimedy is published on [PyPI](https://pypi.org/project/mimedy/) and requires Python 3.10+. The easiest way is to install it as an isolated tool with [uv](https://docs.astral.sh/uv/) or [pipx](https://pipx.pypa.io/):

```bash
uv tool install mimedy     # or: pipx install mimedy
```

> ⚠️ mimedy is tested on macOS and Linux. Windows should work, but is not tested yet: feedback is welcome.

To try it without installing anything:

```bash
uvx mimedy ~/Downloads --dry-run
```

### Usage

> 💡 mimedy always shows the full plan and asks for confirmation before moving anything.

```bash
# Show the plan, then confirm
mimedy ~/Downloads

# Only show the plan
mimedy ~/Downloads --dry-run

# No confirmation, e.g. in a script
mimedy ~/Downloads --yes --config my-config.yaml

# Understand why a file goes where it goes
mimedy ~/Downloads --dry-run --verbose
```

| Option | Description |
| :--- | :--- |
| `DIRECTORY` | Folder to organize *(required)*. |
| `--config`, `-c PATH` | YAML configuration file *(default: see [Configuration](#configuration))*. |
| `--dry-run`, `-n` | Show planned moves without performing them. |
| `--yes`, `-y` | Move without asking for confirmation. |
| `--verbose`, `-v` | Show which rule applied to each file, and the ignored files. |
| `--lowercase`, `-l` | Keep folders named after Magika groups lowercase (`video/` instead of `Video/`). |
| `--version`, `-V` | Show the version. |
| `--help`, `-h` | Show the help. |
| `--init-config` | Create a commented example config at the default location (never overwrites an existing one). |
| `--install-completion` | Enable Tab completion of the options in your shell, detected automatically: bash, zsh, fish or PowerShell (once is enough). |
| `--show-completion` | Print the completion script, to install it yourself (e.g. when your shell config is not in the usual location). |

Only files directly inside the folder are processed. Existing subfolders are left untouched, so the tool can safely be run again. Subfolders are the only entries skipped without being listed: everything else that stays in place shows up as [ignored](#ignored-files) or skipped.

| Exit code | Meaning |
| :-: | :--- |
| `0` | Everything went fine, or there was nothing to organize. |
| `1` | At least one file could not be processed, or the confirmation was declined. |
| `2` | Invalid arguments or configuration. |

### Configuration

Without `--config`, mimedy reads your personal configuration file, if it exists:

| System | Location |
|---|---|
| Linux, macOS | `~/.config/mimedy/config.yaml` (or `$XDG_CONFIG_HOME/mimedy/config.yaml`) |
| Windows | `%APPDATA%\mimedy\config.yaml` |

If it doesn't exist, the defaults are used. A file passed with `--config`, however, must exist. `mimedy --help` shows the exact location on your machine.

To get started, create a commented example config, then adapt it:

```bash
mimedy --init-config
# Created config file: /Users/me/.config/mimedy/config.yaml
```

```yaml
ignore_system_files: true   # leave .DS_Store, Thumbs.db… in place
ignore:                     # extra patterns, case-insensitive
  - "*.part"
  - "*.crdownload"

hidden: "Hidden"            # files starting with '.'

large_files:
  threshold_mb: 500         # default 100, in decimal MB like Finder or Explorer
  target_dir: "Large"

extensions:                 # exact extension match
  .blend: "Blender"
  .csv: "Data"

mimetypes:                  # MIME type detected by Magika
  application/pdf: "PDF"
  image/jpeg: "Photos"
```

Every key is optional: missing ones fall back to their default value. Destinations may include subfolders (`"Code/Python"`). See [`config.example.yaml`](src/mimedy/config.example.yaml), the file copied by `--init-config`, for a complete, commented example.

### Ignored files

Some files are never moved. They don't appear in the plan, don't count as failures, and `--verbose` lists them with the reason.

**System files.** They are created by the system or the file manager: moving them is useless (they are recreated) or breaks what they describe. Names are compared ignoring case.

| System | File | Purpose |
| :--- | :--- | :--- |
| macOS | `.DS_Store` | Finder view settings |
| macOS | `.localized` | Translated folder name |
| macOS | `Icon\r` | Custom folder icon (the name really ends with a carriage return) |
| macOS | `._*` | A file's metadata (`._photo.jpg` for `photo.jpg`), on USB drives or network shares |
| macOS | `.VolumeIcon.icns` | Custom drive icon |
| macOS | `.com.apple.timemachine.donotpresent` | Time Machine marker |
| macOS | `.apdisk` | Network share information |
| Windows | `Thumbs.db`, `ehthumbs.db`, `ehthumbs_vista.db` | Thumbnail cache |
| Windows | `desktop.ini` | Folder appearance |
| Linux | `.directory` | Folder settings in Dolphin (KDE) |
| Linux | `.hidden` | Files hidden by Files (GNOME) |

To organize them like any other file, turn this rule off:

```yaml
ignore_system_files: false
```

**Symbolic links and special files.** These are always left in place:

- **Symbolic links**, whatever they point to. A link is never moved: a relative link would break once moved, and its target may not even be in the folder. Broken links and links to folders are listed too.
- **Special files** that are neither files nor folders: named pipes, sockets, devices.

**Your own patterns.** The `ignore` list adds patterns, matched against the whole file name and ignoring case: `*` stands for any run of characters, `?` for a single character, `[abc]` for one of the listed characters.

```yaml
ignore:
  - "*.part"          # download in progress (Firefox)
  - "*.crdownload"    # download in progress (Chrome)
  - "~$*"             # lock file of an open Office document
```

These patterns come on top of the system files: no need to repeat them.

### How is a file classified?

First of all, [ignored files](#ignored-files) stay in place.

The other files go through these rules, in this order; **the first match wins**:

| # | Rule | Example |
|:-:|:---|:---|
| 1 | Hidden file | `.env` → `Hidden/` |
| 2 | Large file (100 MB by default) | `movie.mkv` (2 GB) → `Large/` |
| 3 | Extension | `scene.blend` → `Blender/` |
| 4 | MIME type (Magika) | `invoice` *(PDF with no extension)* → `PDF/` |
| 5 | Magika group | `script.py` → `Code/` |

Rules 1 to 3 don't read file contents, so they are instant. Magika only runs when they aren't enough.

**Extension or MIME type?** Both let you choose a specific folder, but they don't trust the same thing:

- A **MIME type rule** trusts the content. `text/x-python: "Python"` catches every Python script, even one with no extension or a wrong one. Prefer it for anything Magika recognizes.
- An **extension rule** trusts the name, and is a shortcut you choose: the file is never read. Use it for formats Magika cannot know (`.blend`, `.kra`), or when the extension is what matters to you (`.csv` and `.json` into `Data/`).

Since extension rules come first, a PDF renamed to `report.csv` follows your `.csv` rule. Without that rule, Magika would see it for what it is.

### Project structure

```text
mimedy/
├── pyproject.toml
├── src/mimedy/
│   ├── main.py              # CLI entry point (Typer)
│   ├── config.py            # Configuration loading and validation
│   ├── config.example.yaml  # Commented example configuration
│   ├── organizer.py         # Classification rules, planning and moves
│   └── errors.py            # Project exceptions
└── tests/                   # pytest tests (configuration, rules, plan, CLI)
```

### Development

Code is checked by [Ruff](https://docs.astral.sh/ruff/) (linting and formatting) on every commit, and tested with [pytest](https://docs.pytest.org/). Continuous integration runs both on every push, on Python 3.10 to 3.14.

```bash
git clone https://github.com/ochapeau/mimedy.git
cd mimedy
uv sync                     # create the development environment
uv run pre-commit install   # automatic checks on every commit
uv run pytest               # run the tests
uv run mimedy --help        # run the development version
```

### Roadmap

- [x] Typed, validated configuration
- [x] Global configuration in `~/.config/mimedy/`
- [x] Automated tests and continuous integration
- [x] Publish on PyPI (`uv tool install mimedy`)
- [x] Ignore system files (`.DS_Store`, `.localized`, `Thumbs.db`, `desktop.ini`…), with an option to organize them anyway
- [x] File patterns to ignore (downloads in progress: `*.part`, `*.crdownload`…)
- [ ] Undo the last run (`--undo`)
- [ ] Homebrew install (`brew install ochapeau/tap/mimedy`), once Magika ships its upcoming Rust engine: Homebrew builds Python dependencies from source, and today's `onnxruntime` dependency only exists as prebuilt wheels
- [ ] Optional terminal interface (TUI)

### License

Released under the MIT License. See [LICENSE](LICENSE).

---

<a id="français"></a>

## 🇫🇷 Français

**Sommaire :** [Pourquoi](#pourquoi-) · [Fonctionnalités](#fonctionnalités) · [Installation](#installation-1) · [Utilisation](#utilisation) · [Configuration](#configuration-1) · [Fichiers ignorés](#fichiers-ignorés) · [Comment un fichier est-il classé](#comment-un-fichier-est-il-classé-) · [Structure du projet](#structure-du-projet) · [Développement](#développement) · [Feuille de route](#feuille-de-route) · [Licence](#licence)

### Pourquoi ?

Un dossier `Téléchargements` finit toujours par ressembler à ça : des PDF, des captures d'écran, des archives, un `.json` exporté un jour, un fichier sans extension dont personne ne se souvient…

La plupart des outils de rangement se fient à l'extension. Or une extension peut mentir, manquer ou être fausse. **mimedy** utilise [Magika](https://github.com/google/magika), le modèle de deep learning de Google qui identifie un fichier **à partir de son contenu**, pour décider où il doit aller.

```text
$ mimedy ~/Downloads
[INFO] Loaded config from /Users/me/.config/mimedy/config.yaml
[INFO] Organizing /Users/me/Downloads
[INFO] 'export.csv' → Data/
[INFO] 'holidays.jpg' → Photos/
[INFO] 'invoice' → PDF/
[INFO] 'report.pdf' → PDF/report (1).pdf
[INFO] 'script.py' → Python/
[WARNING] Skipped 'locked.txt': Magika could not read the file (permission_error)
[INFO] 5 files to move into 4 folders, 1 skipped, 0 ignored
Move 5 files? [y/N]: y
[INFO] Done: 5 moved, 0 failed
```

### Fonctionnalités

- 🧠 **Détection par le contenu** : Magika reconnaît plus de 200 types de fichiers, même renommés ou sans extension.
- 🔒 **100 % local** : le modèle d'IA est livré avec l'outil et tourne sur votre machine. Aucune connexion réseau, aucun fichier ni aucune donnée n'est envoyé où que ce soit.
- 🪜 **Règles en cascade** : fichiers cachés, fichiers volumineux, extensions, types MIME, puis le groupe Magika en dernier recours.
- 📋 **Plan puis confirmation** : tous les déplacements sont affichés avant d'être effectués, et rien ne bouge sans votre accord. `--dry-run` s'arrête au plan.
- 🧯 **Robuste** : un fichier illisible ou verrouillé est signalé et ignoré, sans interrompre le rangement.
- 🙈 **Fichiers système ignorés** : `.DS_Store`, `Thumbs.db`… restent à leur place, et vous pouvez ajouter vos propres motifs (`*.part`).
- 🛡️ **Aucun écrasement** : si `photo.jpg` existe déjà, le nouveau fichier devient `photo (1).jpg`.
- 🐛 **Mode `--verbose`** : indique pour chaque fichier la règle qui a décidé de sa destination.
- ⚙️ **Configuration YAML** simple, entièrement facultative.

### Installation

mimedy est publié sur [PyPI](https://pypi.org/project/mimedy/) et nécessite Python 3.10+. Le plus simple est de l'installer comme outil isolé avec [uv](https://docs.astral.sh/uv/) ou [pipx](https://pipx.pypa.io/) :

```bash
uv tool install mimedy     # ou : pipx install mimedy
```

> ⚠️ mimedy est testé sur macOS et Linux. Windows devrait fonctionner, mais n'est pas encore testé : vos retours sont les bienvenus.

Pour l'essayer sans rien installer :

```bash
uvx mimedy ~/Downloads --dry-run
```

### Utilisation

> 💡 mimedy affiche toujours le plan complet et demande confirmation avant de déplacer quoi que ce soit.

```bash
# Afficher le plan, puis confirmer
mimedy ~/Downloads

# Afficher le plan seulement
mimedy ~/Downloads --dry-run

# Sans confirmation, par exemple dans un script
mimedy ~/Downloads --yes --config my-config.yaml

# Comprendre pourquoi un fichier va à tel endroit
mimedy ~/Downloads --dry-run --verbose
```

| Option | Description |
| :--- | :--- |
| `DIRECTORY` | Dossier à ranger *(obligatoire)*. |
| `--config`, `-c PATH` | Fichier de configuration YAML *(par défaut : voir [Configuration](#configuration-1))*. |
| `--dry-run`, `-n` | Affiche les déplacements prévus sans les effectuer. |
| `--yes`, `-y` | Déplace sans demander de confirmation. |
| `--verbose`, `-v` | Affiche la règle appliquée à chaque fichier, et les fichiers ignorés. |
| `--lowercase`, `-l` | Garde en minuscules les dossiers nommés d'après Magika (`video/` au lieu de `Video/`). |
| `--version`, `-V` | Affiche la version. |
| `--help`, `-h` | Affiche l'aide. |
| `--init-config` | Crée une configuration d'exemple commentée à l'emplacement par défaut (sans jamais écraser une configuration existante). |
| `--install-completion` | Active l'autocomplétion des options avec Tab dans votre shell, détecté automatiquement : bash, zsh, fish ou PowerShell (une seule fois suffit). |
| `--show-completion` | Affiche le script d'autocomplétion, pour l'installer vous-même (par exemple si votre configuration de shell n'est pas à l'emplacement habituel). |

Seuls les fichiers situés directement dans le dossier sont traités. Les sous-dossiers existants ne sont pas touchés, ce qui permet de relancer l'outil sans risque. Ce sont les seuls éléments laissés de côté sans être signalés : tout ce qui reste en place apparaît comme [ignoré](#fichiers-ignorés) ou sauté.

| Code de sortie | Signification |
| :-: | :--- |
| `0` | Tout s'est bien passé, ou il n'y avait rien à ranger. |
| `1` | Au moins un fichier n'a pas pu être traité, ou la confirmation a été refusée. |
| `2` | Arguments ou configuration invalides. |

### Configuration

Sans `--config`, mimedy lit le fichier de configuration personnel, s'il existe :

| Système | Emplacement |
|---|---|
| Linux, macOS | `~/.config/mimedy/config.yaml` (ou `$XDG_CONFIG_HOME/mimedy/config.yaml`) |
| Windows | `%APPDATA%\mimedy\config.yaml` |

S'il n'existe pas, les valeurs par défaut sont utilisées. Un fichier passé avec `--config` doit en revanche exister. `mimedy --help` affiche l'emplacement exact sur votre machine.

Pour démarrer, créez une configuration d'exemple commentée, puis adaptez-la :

```bash
mimedy --init-config
# Created config file: /Users/me/.config/mimedy/config.yaml
```

```yaml
ignore_system_files: true   # laisser .DS_Store, Thumbs.db… en place
ignore:                     # motifs en plus, sans tenir compte de la casse
  - "*.part"
  - "*.crdownload"

hidden: "Hidden"            # fichiers commençant par '.'

large_files:
  threshold_mb: 500         # 100 par défaut, en Mo décimaux comme le Finder
  target_dir: "Large"

extensions:                 # correspondance exacte sur l'extension
  .blend: "Blender"
  .csv: "Data"

mimetypes:                  # type MIME détecté par Magika
  application/pdf: "PDF"
  image/jpeg: "Photos"
```

Toutes les clés sont facultatives : celles qui manquent reprennent leur valeur par défaut. Les destinations peuvent contenir des sous-dossiers (`"Code/Python"`). [`config.example.yaml`](src/mimedy/config.example.yaml), le fichier copié par `--init-config`, contient un exemple complet et commenté.

### Fichiers ignorés

Certains fichiers ne sont jamais déplacés. Ils n'apparaissent pas dans le plan, ne comptent pas comme des erreurs, et `--verbose` les liste avec la raison.

**Fichiers système.** Ils sont créés par le système ou le gestionnaire de fichiers : les déplacer ne sert à rien (ils sont recréés) ou casse ce qu'ils décrivent. Les noms sont comparés sans tenir compte de la casse.

| Système | Fichier | Rôle |
| :--- | :--- | :--- |
| macOS | `.DS_Store` | Réglages d'affichage du Finder |
| macOS | `.localized` | Nom de dossier traduit |
| macOS | `Icon\r` | Icône personnalisée du dossier (le nom se termine vraiment par un retour chariot) |
| macOS | `._*` | Métadonnées d'un fichier (`._photo.jpg` pour `photo.jpg`), sur clé USB ou partage réseau |
| macOS | `.VolumeIcon.icns` | Icône personnalisée d'un disque |
| macOS | `.com.apple.timemachine.donotpresent` | Marqueur Time Machine |
| macOS | `.apdisk` | Informations de partage réseau |
| Windows | `Thumbs.db`, `ehthumbs.db`, `ehthumbs_vista.db` | Cache des miniatures |
| Windows | `desktop.ini` | Apparence du dossier |
| Linux | `.directory` | Réglages du dossier dans Dolphin (KDE) |
| Linux | `.hidden` | Fichiers masqués par Fichiers (GNOME) |

Pour les ranger comme les autres fichiers, désactivez cette règle :

```yaml
ignore_system_files: false
```

**Liens symboliques et fichiers spéciaux.** Ils restent toujours en place :

- **Les liens symboliques**, quelle que soit leur cible. Un lien n'est jamais déplacé : un lien relatif serait cassé une fois déplacé, et sa cible n'est pas forcément dans le dossier. Les liens cassés et les liens vers des dossiers sont listés aussi.
- **Les fichiers spéciaux**, qui ne sont ni des fichiers ni des dossiers : tubes nommés, sockets, périphériques.

**Vos propres motifs.** La liste `ignore` ajoute des motifs, comparés au nom complet du fichier sans tenir compte de la casse : `*` remplace n'importe quelle suite de caractères, `?` un seul caractère, `[abc]` un caractère parmi ceux indiqués.

```yaml
ignore:
  - "*.part"          # téléchargement en cours (Firefox)
  - "*.crdownload"    # téléchargement en cours (Chrome)
  - "~$*"             # fichier de verrouillage d'un document Office ouvert
```

Ces motifs s'ajoutent aux fichiers système : inutile de les répéter.

### Comment un fichier est-il classé ?

Avant tout, les [fichiers ignorés](#fichiers-ignorés) restent en place.

Les autres fichiers passent par ces règles, dans cet ordre ; **la première qui correspond l'emporte** :

| # | Règle | Exemple |
|:-:|:---|:---|
| 1 | Fichier caché | `.env` → `Hidden/` |
| 2 | Fichier volumineux (100 Mo par défaut) | `film.mkv` (2 Go) → `Large/` |
| 3 | Extension | `scene.blend` → `Blender/` |
| 4 | Type MIME (Magika) | `facture` *(PDF sans extension)* → `PDF/` |
| 5 | Groupe Magika | `script.py` → `Code/` |

Les règles 1 à 3 ne lisent pas le contenu des fichiers : elles sont instantanées. Magika n'est appelé que si elles ne suffisent pas.

**Extension ou type MIME ?** Les deux permettent de choisir un dossier précis, mais elles ne se fient pas à la même chose :

- Une **règle MIME** se fie au contenu. `text/x-python: "Python"` attrape tous les scripts Python, même sans extension ou avec une mauvaise. À privilégier pour tout ce que Magika reconnaît.
- Une **règle d'extension** se fie au nom : c'est un raccourci que vous choisissez, et le fichier n'est jamais lu. À utiliser pour les formats que Magika ne peut pas connaître (`.blend`, `.kra`), ou quand c'est l'extension qui compte pour vous (`.csv` et `.json` dans `Data/`).

Comme les règles d'extension passent en premier, un PDF renommé en `rapport.csv` suit votre règle `.csv`. Sans cette règle, Magika le reconnaîtrait pour ce qu'il est.

### Structure du projet

```text
mimedy/
├── pyproject.toml
├── src/mimedy/
│   ├── main.py              # Point d'entrée de la CLI (Typer)
│   ├── config.py            # Chargement et validation de la configuration
│   ├── config.example.yaml  # Configuration d'exemple commentée
│   ├── organizer.py         # Règles de classement, planification et déplacements
│   └── errors.py            # Exceptions du projet
└── tests/                   # Tests pytest (configuration, règles, plan, CLI)
```

### Développement

Le code est vérifié par [Ruff](https://docs.astral.sh/ruff/) (lint et formatage) à chaque commit, et testé avec [pytest](https://docs.pytest.org/). L'intégration continue lance les deux à chaque push, sur Python 3.10 à 3.14.

```bash
git clone https://github.com/ochapeau/mimedy.git
cd mimedy
uv sync                     # crée l'environnement de développement
uv run pre-commit install   # vérifications automatiques à chaque commit
uv run pytest               # lancer les tests
uv run mimedy --help        # lancer la version en cours de développement
```

### Feuille de route

- [x] Configuration typée et validée
- [x] Configuration globale dans `~/.config/mimedy/`
- [x] Tests automatisés et intégration continue
- [x] Publication sur PyPI (`uv tool install mimedy`)
- [x] Ignorer les fichiers système (`.DS_Store`, `.localized`, `Thumbs.db`, `desktop.ini`…), avec une option pour les ranger quand même
- [x] Motifs de fichiers à ignorer (téléchargements en cours : `*.part`, `*.crdownload`…)
- [ ] Annuler le dernier rangement (`--undo`)
- [ ] Installation avec Homebrew (`brew install ochapeau/tap/mimedy`), dès que Magika publiera son futur moteur en Rust : Homebrew compile les dépendances Python depuis leurs sources, et `onnxruntime`, dont Magika dépend aujourd'hui, n'existe qu'en paquets précompilés
- [ ] Interface en terminal (TUI), en option

### Licence

Distribué sous licence MIT. Voir [LICENSE](LICENSE).
