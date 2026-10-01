# 📂 mimedy

**mimedy** is an intelligent, rule-based command-line tool designed to clean up and organize messy directories automatically. 

Instead of relying solely on file extensions (which can be misleading or missing), `mimedy` leverages **[Google Magika](https://github.com/google/magika)**—a deep-learning-based file type identification tool—to accurately detect file types via their binary content.

---

## ✨ Features

- 🧠 **AI-Powered File Identification**: Uses Google Magika's ML model to detect actual MIME types and content groups regardless of file extensions.
- ⚙️ **Flexible Configuration**: Cascading rule system matching hidden files, size thresholds, extensions, and MIME types.
- 🛡️ **Dry-Run Mode**: Test and preview how your files will be moved before any changes are made on disk.
- 📐 **Clean Architecture**: Built with modern Python standards (`pathlib`, `typer`, `annotated-types`, and `pyyaml`).

---

## 🚀 Installation

### Prerequisites

Ensure you have **Python 3.10+** installed on your system.

### Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-username/mimedy.git
   cd mimedy
   ```

2. **Create a virtual environment & install dependencies:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install typer pyyaml magika
   ```

---

## 🛠️ Usage

Run `mimedy` directly by passing the target directory you want to organize:

```bash
python src/mimedy/main.py /path/to/target-directory
```

### Options

| Option | Description |
| :--- | :--- |
| `DIRECTORY` | *(Required)* Path to the directory you want to organize. |
| `--config PATH` | Custom YAML configuration file path *(default: `config.yaml`)*. |
| `--dry-run` | Preview the file movements without actually moving any files. |
| `--lowercase` | Keep auto-generated folder names lowercase (e.g., `code/` instead of `Code/`). |

### Examples

**Safe Preview (Dry Run):**
```bash
python src/mimedy/main.py ~/Downloads --dry-run
```

**Using a Custom Configuration:**
```bash
python src/mimedy/main.py ~/Downloads --config custom_config.yaml
```

---

## ⚙️ Configuration (`config.yaml`)

`mimedy` merges user-defined rules with built-in defaults. You can override any setting by providing a YAML configuration file.

### Example `config.yaml`

```yaml
# Folder for UNIX hidden files (starting with '.')
hidden: "Hidden"

# Large files routing (size in MB)
large_files:
  threshold_mb: 100
  target_dir: "Large"

# Priority 1: Direct Extension Mapping
extensions:
  .gd: "Godot"
  .blend: "Blender"
  .yaml: "Data"
  .csv: "Data"

# Priority 2: MIME Type Mapping (detected via Magika)
mimetypes:
  application/pdf: "Documents"
  image/png: "Images"
  text/x-python: "Code"
```

### 🧠 Decision Cascade

When evaluating a file, `mimedy` applies rules in the following strict order:

1. **Hidden Files**: If the file starts with `.`, it goes to `config["hidden"]` *(e.g., `Hidden/`)*.
2. **Large Files**: If size >= `threshold_mb` (calculated using decimal MB to match OS file managers), it goes to `config["large_files"]["target_dir"]` *(e.g., `Large/`)*.
3. **Extension Rules**: If the extension matches an entry in `extensions`, it goes to the specified directory.
4. **MIME Type Rules**: If Magika detects a MIME type matching `mimetypes`, it goes to the specified directory.
5. **Fallback (Magika Group)**: If no prior rules match, the file is routed to its broad content group identified by Magika *(e.g., `Code/`, `Audio/`, `Executable/`)*.

---

## 🏗️ Project Structure

```text
mimedy/
├── config.yaml          # Sample/default configuration file
└── src/
    └── mimedy/
        ├── __init__.py
        ├── main.py      # CLI entrypoint (Typer interface)
        ├── organizer.py # Core logic, Magika integration, and file movements
        └── utils.py     # Configuration loading and logging initialization
```

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.