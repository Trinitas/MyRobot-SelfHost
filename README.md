# MyRobot Local AI

Free, offline **text and voice** for [MyRobot](https://store.steampowered.com/app/3597510/) – no subscription, nothing leaves your PC.

One double-click starts everything the game's *self host* options need:

| | What | Runs on |
|---|---|---|
| **Text** | [KoboldCpp](https://github.com/LostRuins/koboldcpp) + [Qwen2.5 7B Instruct](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct) | your NVIDIA GPU |
| **Voice** | [KittenTTS 0.8](https://github.com/KittenML/KittenTTS) (voice "Kiki") | your CPU |

> Fan-made tool. Not affiliated with the MyRobot developer.

## Requirements

- Windows 10/11
- An NVIDIA GPU with **8 GB VRAM or more** (Qwen2.5 7B uses about 6 GB).
  It checks your free VRAM first and tells you if it is not enough, instead of crashing.
- About 5.5 GB free disk space
- Internet for the first run (everything is downloaded automatically)

## Setup

1. **Install Python 3.12** from [python.org](https://www.python.org/downloads/).
   Tick **"Add python.exe to PATH"** in the installer.
   *(3.10 and 3.11 also work. 3.13 and newer do **not** work with KittenTTS.)*
2. **Download this tool:** click the green **Code** button at the top of this page → **Download ZIP**,
   and unzip it to a folder, e.g. `Desktop\MyRobotAI`.
3. **Double-click `START.bat`.**
   The first run downloads the voice engine (~300 MB), KoboldCpp, the Qwen model (~4.7 GB) and the
   voice model, each with a progress bar. This takes a while – after that it starts in seconds.
   Everything goes into the `data` folder. Only ever start `START.bat`.
4. Wait until it says **"ALL SET! You can start MyRobot now."**
   Keep the window open while you play. Close it to stop everything.

## In the game

Press **ESC → AI Setup**:

| Section | Setting | Value |
|---|---|---|
| **Text Generation** | Mode | `Manual` |
| | Server address | `http://localhost:5001` |
| **Text to Speech** | Mode | `Self Host` |
| | Server address | `http://localhost:8005/tts` |
| | Parameter (use **Add**) | `text` = `content` ← must turn **cyan** |
| | Parameter (use **Add**) | `voice` = `Kiki` |

Test the voice in your browser: <http://localhost:8005/tts?text=Hello%20there>

## Settings

Open `myrobot_ai.py` in Notepad. All settings are at the top:

| Setting | What it does |
|---|---|
| `LLM_GPU` | Which **one** GPU runs the text: `"auto"` = the first GPU, part of the name like `"3090"`, or a number as shown by `nvidia-smi` |
| `LLM_MODEL_FILE` | Use your own `.gguf` model from `data\models`. Left empty, the biggest `.gguf` already there is used and nothing is downloaded. |
| `LLM_VRAM_RESERVE_GB` | VRAM kept free for the game and Windows |
| `TTS_VOICE` | `Bella`, `Jasper`, `Luna`, `Bruno`, `Rosie`, `Hugo`, `Kiki`, `Leo` |
| `TTS_SPEED` | How fast she talks (`1.0` = normal) |
| `TTS_CANCEL_OLD` | A new line stops an unfinished old one, so she answers faster (on by default) |
| `TTS_PLAY_ON_PC` | Most responsive: the voice plays straight through your speakers and starts after the first sentence. The game's own volume / lip sync won't follow it. |
| `SHOW_DETAILS` | Show everything KoboldCpp and the voice engine print (for troubleshooting) |

The voice always runs on the CPU, so it never takes VRAM from the game or the text model.

## Troubleshooting

- **"No Python 3.10, 3.11 or 3.12 found"** – install Python 3.12 (step 1).
  *Anaconda users:* `START.bat` can't see conda environments. Open Anaconda Prompt, activate an
  environment with Python 3.10–3.12, go to the folder and run `python myrobot_ai.py` once.
  After that, `START.bat` works by itself.
- **"ERROR OTHER_ERROR" in the game** – check the TTS address and that `content` is cyan.
- **"Not enough free VRAM"** – close other programs using the GPU, pick another GPU with `LLM_GPU`,
  or use a smaller model.
- **Antivirus removes `koboldcpp.exe`** – a known false alarm (it is packed with PyInstaller).
  Restore it from quarantine, or download it yourself from the
  [KoboldCpp releases](https://github.com/LostRuins/koboldcpp/releases) and put it in `data\koboldcpp`.
- **Logs** – install problems: `data\install_log.txt`. Text model problems: `data\llm_log.txt`.
- **Start over** – delete the `data\.venv` folder and run `START.bat` again.

## Credits

This tool only downloads and starts these projects – all the hard work is theirs.
Each is used under its own license:

- [KoboldCpp](https://github.com/LostRuins/koboldcpp) by LostRuins – runs the text model
- [Qwen2.5](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct) by the Qwen team, GGUF by [bartowski](https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF)
- [KittenTTS](https://github.com/KittenML/KittenTTS) by KittenML – the voice
- [MyRobot](https://store.steampowered.com/app/3597510/) by sgthale – the game
