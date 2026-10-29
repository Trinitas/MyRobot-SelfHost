"""
MyRobot Local AI - one file that runs everything the game needs for self hosting:

  * LLM  (text)  : KoboldCpp + Qwen2.5 7B Instruct, on your NVIDIA GPU
  * TTS  (voice) : KittenTTS 0.8 (voice "Kiki"), always on the CPU

First run downloads everything automatically (about 5 GB) into this folder.
Start it with START.bat. Close the window or press Ctrl+C to stop everything.

In MyRobot: Pause (ESC) -> AI Setup
  Text Generation : Manual,     server address  http://localhost:5001
  Text to Speech  : Self Host,  server address  http://localhost:8005/tts
                    parameters: text = content (cyan), voice = Kiki
"""

# ============================== SETTINGS ==============================
# Change these if you want. Everything else in this file can stay as it is.

# --- LLM (text generation) ---
LLM_ENABLED    = True
LLM_MODEL_URL  = ("https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/"
                  "resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf")
LLM_MODEL_FILE = ""       # Use your own model instead: put the .gguf in the "data\models" folder
                          # and write its file name here, e.g. "MyModel.Q4_K_M.gguf"
LLM_GPU        = "auto"   # Which ONE NVIDIA GPU runs the LLM:
                          # "auto" = the first GPU (number 0 in nvidia-smi)
                          # "3090" = the GPU whose name contains this text
                          # "1"    = GPU number 1 (numbers as shown by nvidia-smi)
                          # The whole model must fit in its VRAM, otherwise the LLM is not started.
LLM_VRAM_RESERVE_GB = 1.5 # VRAM that must stay free for the game and Windows.
LLM_CONTEXT    = 8192     # How much of the conversation the robot remembers.
LLM_PORT       = 5001
LLM_SHOW_PROMPTS = False  # True = print the full prompt the game sends (for troubleshooting)

# --- Console ---
SHOW_DETAILS   = False    # True = show everything KoboldCpp and the voice engine print.
                          # False = only short status lines (details go to data\llm_log.txt).

# --- TTS (voice) - always runs on the CPU ---
TTS_ENABLED    = True
TTS_MODEL      = "KittenML/kitten-tts-mini-0.8"   # Faster, lower quality: "KittenML/kitten-tts-nano-0.8"
TTS_VOICE      = "Kiki"   # Default voice: Bella, Jasper, Luna, Bruno, Rosie, Hugo, Kiki, Leo
TTS_SPEED      = 1.0      # 1.0 = normal, 1.3 = faster, 0.8 = slower
TTS_PORT       = 8005
TTS_CANCEL_OLD = True     # A new line stops work on an older, unfinished one, so she answers faster.
TTS_PLAY_ON_PC = False    # Most responsive mode: True = the voice plays directly through the PC's
                          # speakers and starts after the FIRST sentence is ready. The game gets a
                          # silent clip, so its own volume slider / lip sync will not follow the voice.
# =====================================================================

import io
import json
import os
import platform
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")              # everything downloaded or created goes in here
VENV = os.path.join(DATA, ".venv")
MODELS = os.path.join(DATA, "models")
TTS_CACHE = os.path.join(DATA, "tts_cache")
IS_WINDOWS = os.name == "nt"

KITTEN_WHEEL = ("https://github.com/KittenML/KittenTTS/releases/download/0.8.1/"
                "kittentts-0.8.1-py3-none-any.whl")
# KittenTTS normally pulls in spaCy + PyTorch (several GB) for an English module it never uses.
# We install only what it really needs (~300 MB) and stub out that module in start_tts().
PIP_NO_DEPS = [KITTEN_WHEEL, "misaki==0.9.4"]
PIP_DEPS = ["espeakng_loader", "phonemizer-fork==3.3.2", "onnxruntime", "soundfile", "numpy",
            "huggingface_hub", "sounddevice"]
PIP_EXPECTED = 50          # roughly how many packages that becomes (only used for the progress bar)
INSTALL_MARKER = os.path.join(VENV, "myrobot_installed_kitten_0.8.1_slim")
INSTALL_LOG = os.path.join(DATA, "install_log.txt")
LLM_LOG = os.path.join(DATA, "llm_log.txt")
KOBOLD_DIR = os.path.join(DATA, "koboldcpp")
KOBOLD_BASE = "https://github.com/LostRuins/koboldcpp/releases/latest/download/"
KOBOLD_FILE = "koboldcpp.exe" if IS_WINDOWS else "koboldcpp-linux-x64"

processes = []


# ------------------------------ helpers ------------------------------

def say(tag, color, text):
    print(f"\033[{color}m[{tag}]\033[0m {text}", flush=True)


def detail(tag, color, text):
    """Only shown when SHOW_DETAILS = True."""
    if SHOW_DETAILS:
        say(tag, color, text)


def step(text):
    print(f"\n \033[96m>\033[0m {text}", flush=True)


def done(text):
    print(f"   \033[92m{text}\033[0m", flush=True)


def note(text):
    print(f"   {text}", flush=True)


def warn(text):
    print(f"   \033[93m! {text}\033[0m", flush=True)


def info(text):
    step(text)


def fail(text):
    print(f"\n\033[91m[ERROR]\033[0m {text}\n", flush=True)
    sys.exit(1)


def progress(pct, detail=""):
    pct = max(0, min(100, int(pct)))
    bar = "#" * (pct // 4)
    print(f"\r    [{bar:<25}] {pct:3d}%  {detail[:40]:<40}", end="", flush=True)


def download(url, dest, what):
    """Download with a progress bar. Never leaves a half-finished file behind."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    part = dest + ".part"
    note(f"Downloading {what} (first run only) ...")
    req = urllib.request.Request(url, headers={"User-Agent": "MyRobotLocalAI"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done, last = 0, 0
            while True:
                chunk = r.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if time.time() - last > 0.5:
                    last = time.time()
                    if total:
                        progress(done * 100 / total, f"{done >> 20} / {total >> 20} MB")
                    else:
                        print(f"\r    {done >> 20} MB", end="", flush=True)
        if total:
            progress(100, f"{total >> 20} MB")
        print()
    except Exception as e:
        if os.path.exists(part):
            os.remove(part)
        fail(f"Could not download {what}: {e}\n        URL: {url}")
    os.replace(part, dest)


def is_up(url):
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


# --------------------------- 1. environment ---------------------------

def venv_python():
    return os.path.join(VENV, "Scripts" if IS_WINDOWS else "bin", "python.exe" if IS_WINDOWS else "python")


def pip_install_with_bar(py):
    """Run pip quietly behind one progress bar. The full output goes to data/install_log.txt."""
    base = [py, "-m", "pip", "install", "--disable-pip-version-check", "--progress-bar", "off"]
    steps = [base + ["--no-deps"] + PIP_NO_DEPS, base + PIP_DEPS]
    seen, pct = 0, 0
    with open(INSTALL_LOG, "w", encoding="utf-8") as log:
        for cmd in steps:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace")
            for line in proc.stdout:
                log.write(line)
                text = line.strip()
                if text.startswith(("Collecting ", "Processing ")):
                    seen += 1
                    name = re.split(r"[ <>=!\[;]", text.split(" ", 1)[1])[0].rsplit("/", 1)[-1]
                    pct = max(pct, min(90, seen * 90 / PIP_EXPECTED))
                    progress(pct, name)
                elif text.startswith("Installing collected packages"):
                    pct = max(pct, 92)
                    progress(pct, "installing ...")
            if proc.wait() != 0:
                print()
                fail(f"Installing the voice engine failed. Full details in {INSTALL_LOG}")
    progress(100, "done")
    print()


def ensure_environment():
    """Create a private Python environment in data/.venv and install KittenTTS, then run inside it."""
    if not (3, 10) <= sys.version_info[:2] <= (3, 12):
        fail(f"Python {platform.python_version()} found, but KittenTTS needs Python 3.10, 3.11 or 3.12.\n"
             "        Install Python 3.12 from https://www.python.org/downloads/ and run START.bat again.")

    py = venv_python()
    if not os.path.exists(py):
        os.makedirs(DATA, exist_ok=True)
        info("Creating a private Python environment (first run only) ...")
        subprocess.check_call([sys.executable, "-m", "venv", VENV])

    if TTS_ENABLED and not os.path.exists(INSTALL_MARKER):
        info("Installing the voice engine KittenTTS 0.8.1 (first run only, ~300 MB) ...")
        pip_install_with_bar(py)
        open(INSTALL_MARKER, "w").close()

    # Restart this script with the environment's Python if we are not already in it.
    if os.path.normcase(os.path.abspath(sys.prefix)) != os.path.normcase(os.path.abspath(VENV)):
        env = dict(os.environ, MYROBOT_RELAUNCHED="1")      # so the title is not printed twice
        sys.exit(subprocess.call([py, os.path.abspath(__file__)] + sys.argv[1:], env=env))


# ------------------------------ 2. LLM ------------------------------

def find_model():
    if LLM_MODEL_FILE:
        path = LLM_MODEL_FILE if os.path.isabs(LLM_MODEL_FILE) else os.path.join(MODELS, LLM_MODEL_FILE)
        if not os.path.exists(path):
            fail(f"Model not found: {path}")
        return path
    path = os.path.join(MODELS, urllib.parse.unquote(LLM_MODEL_URL.rsplit("/", 1)[-1]))
    if os.path.exists(path):
        return path
    # Already have a .gguf in data\models (or next to this file)? Use the biggest one, skip the download.
    found = [os.path.join(d, f) for d in (MODELS, BASE) if os.path.isdir(d)
             for f in os.listdir(d) if f.lower().endswith(".gguf")]
    if found:
        best = max(found, key=os.path.getsize)
        note(f"Found {os.path.basename(best)} - using it, no download needed.")
        return best
    download(LLM_MODEL_URL, path, f"the LLM model {os.path.basename(path)} (about 4.7 GB)")
    return path


def find_kobold():
    """KoboldCpp lives in its own folder so nobody double-clicks it instead of START.bat."""
    path = os.path.join(KOBOLD_DIR, KOBOLD_FILE)
    if not os.path.exists(path):
        download(KOBOLD_BASE + KOBOLD_FILE, path, "KoboldCpp")
        if not IS_WINDOWS:
            os.chmod(path, 0o755)
    return path


def list_gpus():
    """[(index, name, total_gb, free_gb), ...] from nvidia-smi, or [] if there is no NVIDIA GPU."""
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=index,name,memory.total,memory.free",
                              "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=15).stdout
    except Exception:
        return []
    gpus = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 4 and parts[0].isdigit():
            gpus.append((parts[0], parts[1], float(parts[2]) / 1024, float(parts[3]) / 1024))
    return gpus


def choose_gpu(gpus):
    """Pick ONE GPU from the LLM_GPU setting ("auto" = the first one). Returns the GPU or None."""
    choice = str(LLM_GPU).strip().lower()
    if choice in ("", "auto"):
        return gpus[0]
    # "1" = GPU number 1 if such a number exists, otherwise text in the name (so "3090" finds an RTX 3090)
    picked = [g for g in gpus if g[0] == choice] or [g for g in gpus if choice in g[1].lower()]
    if not picked:
        warn(f"No GPU matches LLM_GPU = '{LLM_GPU}'. Your GPUs:")
        for g in gpus:
            note(f"  {g[0]}: {g[1]}")
        return None
    return picked[0]


def enough_vram(model, gpu):
    """True if the whole model fits on the GPU. Never falls back to the CPU or RAM."""
    model_gb = os.path.getsize(model) / 1024 ** 3
    need_gb = model_gb + 0.8 + 0.5 * LLM_CONTEXT / 8192      # model + working memory + conversation memory
    usable_gb = gpu[3] - LLM_VRAM_RESERVE_GB
    detail("LLM", "96", f"{gpu[1]}: {gpu[3]:.1f} of {gpu[2]:.0f} GB free, model needs about {need_gb:.1f} GB "
                        f"(+ {LLM_VRAM_RESERVE_GB} GB kept free for the game)")
    if usable_gb >= need_gb:
        return True
    warn(f"Not enough free VRAM on {gpu[1]}: the model needs about {need_gb:.1f} GB, "
         f"only {max(usable_gb, 0):.1f} GB is available")
    warn(f"(after keeping {LLM_VRAM_RESERVE_GB} GB free for the game). The LLM was NOT started.")
    note("Fix: close other programs that use the GPU, pick another GPU with LLM_GPU,")
    note("     or use a smaller model, e.g. Qwen2.5-3B-Instruct (put its .gguf in data\\models).")
    return False


def pipe_output(tag, color, proc):
    """Everything KoboldCpp prints goes to data/llm_log.txt, and to the screen only if asked for."""
    show = SHOW_DETAILS or LLM_SHOW_PROMPTS
    with open(LLM_LOG, "w", encoding="utf-8") as log:
        for raw in iter(proc.stdout.readline, b""):
            line = raw.decode("utf-8", errors="replace").rstrip()
            if line:
                log.write(line + "\n")
                log.flush()
                if show:
                    say(tag, color, line)


def log_tail(path, lines=15):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-lines:])
    except OSError:
        return ""


def start_llm():
    if is_up(f"http://127.0.0.1:{LLM_PORT}/api/v1/model"):
        note(f"An LLM is already running on port {LLM_PORT} - using that one.")
        return None
    exe, model = find_kobold(), find_model()

    gpus = list_gpus()
    if not gpus:
        warn("No NVIDIA GPU found. The LLM needs an NVIDIA GPU and was NOT started.")
        return False
    gpu = choose_gpu(gpus)
    if gpu is None or not enough_vram(model, gpu):
        return False
    note(f"{os.path.splitext(os.path.basename(model))[0]} on {gpu[1].replace('NVIDIA GeForce ', '')}")

    cmd = [exe, "--model", model, "--port", str(LLM_PORT), "--contextsize", str(LLM_CONTEXT),
           "--skiplauncher", "--usecublas", "--gpulayers", "999"]       # 999 = the whole model on the GPU
    cmd += ["--debugmode", "1"] if LLM_SHOW_PROMPTS else ["--quiet"]
    # Only this one GPU is visible to KoboldCpp, so it can't spread over several cards.
    gpu_env = {"CUDA_DEVICE_ORDER": "PCI_BUS_ID", "CUDA_VISIBLE_DEVICES": gpu[0]}

    env = dict(os.environ, **gpu_env)
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if IS_WINDOWS else 0
    proc = subprocess.Popen(cmd, cwd=KOBOLD_DIR, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, creationflags=flags)
    processes.append(proc)
    threading.Thread(target=pipe_output, args=("LLM", "96", proc), daemon=True).start()
    return proc


# ------------------------------ 3. TTS ------------------------------

SAMPLE_RATE = 24000
tts_model = None
tts_lock = threading.Lock()        # Kitten is not documented as thread-safe
voice_names = {}

# Every new line bumps this number. Work for an older line sees the change and stops,
# so a new line never has to wait for an old one to finish.
generation = 0
generation_lock = threading.Lock()


class Cancelled(Exception):
    pass


def new_generation():
    global generation
    with generation_lock:
        generation += 1
        return generation


# --- text cleanup and sentence splitting ---

TAG_RE = re.compile(r"\[[^\]]*\]|\*[^*]*\*|<[^>]*>")   # [laugh], *smiles*, <tags>
ABBREVIATIONS = {"mr", "mrs", "ms", "dr", "st", "sr", "jr", "etc", "vs", "e.g", "i.e", "a.m", "p.m"}
MIN_WORDS = 3          # very short sentences are merged with their neighbour
MAX_CHARS = 300        # longer "sentences" are left to Kitten's own splitter


def clean_for_speech(text):
    """Remove things Kitten would read out loud, like [laugh] or *smiles*."""
    text = re.sub(r"\s+", " ", TAG_RE.sub(" ", text or "")).strip()
    return re.sub(r"\s+([,.!?;:])", r"\1", text)


def split_sentences(text):
    """Split on . ! ? (but not after Mr. Dr. etc.), keep the punctuation, merge tiny pieces."""
    sentences, buf = [], ""
    for i, ch in enumerate(text):
        buf += ch
        if ch in ".!?" and (i + 1 == len(text) or text[i + 1].isspace()):
            if ch == ".":
                last = re.search(r"([A-Za-z.]+)$", buf.rstrip("."))
                if last and last.group(1).lower().rstrip(".") in ABBREVIATIONS:
                    continue
            if buf.strip():
                sentences.append(buf.strip())
            buf = ""
    if buf.strip():
        sentences.append(buf.strip())

    merged = []
    for s in sentences:
        if merged and (len(merged[-1].split()) < MIN_WORDS or len(s.split()) < MIN_WORDS):
            merged[-1] += " " + s
        else:
            merged.append(s)
    return [s for s in merged if re.search(r"[A-Za-z0-9]", s)]


# --- synthesis ---

def resolve_voice(voice):
    name = voice_names.get(str(voice or TTS_VOICE).strip().lower())
    if name is None:
        raise ValueError(f"Unknown voice. Choose one of: {', '.join(voice_names.values())}")
    return name


def quiet():
    """Hide Kitten's own prints (it prints every line it speaks) unless SHOW_DETAILS is on."""
    import contextlib
    return contextlib.nullcontext() if SHOW_DETAILS else contextlib.redirect_stdout(io.StringIO())


def synth_sentence(sentence, voice, speed):
    """One sentence -> audio. Sentence by sentence keeps the ! and ? intonation that
    Kitten's own splitter replaces with commas."""
    import numpy as np
    inner = getattr(tts_model, "model", None)
    with tts_lock, quiet():
        if inner is not None and hasattr(inner, "generate_single_chunk") and len(sentence) <= MAX_CHARS:
            text = inner.preprocessor(sentence) if hasattr(inner, "preprocessor") else sentence
            audio = inner.generate_single_chunk(text, voice, speed)
        else:
            audio = tts_model.generate(sentence, voice=voice, speed=speed, clean_text=True)
    return np.asarray(audio, dtype=np.float32).squeeze()


def synth_sentences(text, voice, speed, gen=None):
    """Yield audio one sentence at a time. Raises Cancelled if a newer line arrives."""
    voice = resolve_voice(voice)
    speed = float(speed or TTS_SPEED)
    for sentence in split_sentences(clean_for_speech(text)):
        if gen is not None and gen != generation:
            raise Cancelled()
        yield synth_sentence(sentence, voice, speed)


def to_wav(parts):
    import numpy as np
    import soundfile as sf
    gap = np.zeros(int(SAMPLE_RATE * 0.08), dtype=np.float32)     # short natural pause between sentences
    audio = np.concatenate([p for part in parts for p in (part, gap)]) if parts else gap
    buf = io.BytesIO()
    sf.write(buf, audio, SAMPLE_RATE, format="WAV", subtype="PCM_16")
    return buf.getvalue()


# --- optional: play straight through the PC speakers ---

play_queue = None


def player_loop():
    import sounddevice as sd
    while True:
        audio, gen = play_queue.get()
        if audio is None or gen != generation:
            continue
        try:
            sd.play(audio, samplerate=SAMPLE_RATE)
            sd.wait()          # returns early when stop_playback() calls sd.stop()
        except Exception as e:
            warn(f"Voice playback error: {e}")


def stop_playback():
    import queue
    import sounddevice as sd
    while True:
        try:
            play_queue.get_nowait()
        except queue.Empty:
            break
    try:
        sd.stop()
    except Exception:
        pass
    play_queue.put((None, None))      # wake the player


def speak_on_pc(text, voice, speed, gen):
    """Synthesize in the background and start playing after the FIRST sentence is ready."""
    started = time.time()
    try:
        for i, audio in enumerate(synth_sentences(text, voice, speed, gen)):
            if gen != generation:
                return
            if i == 0:
                detail("TTS", "95", f"{time.time() - started:.2f}s to first sound  \"{clean_for_speech(text)[:60]}\"")
            play_queue.put((audio, gen))
    except Cancelled:
        pass
    except Exception as e:
        warn(f"Voice error: {e}")


def make_handler():
    from http.server import BaseHTTPRequestHandler

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def send_json(self, code, data):
            self.send(code, json.dumps(data).encode(), "application/json")

        def params(self):
            url = urllib.parse.urlparse(self.path)
            data = {k: v[-1] for k, v in urllib.parse.parse_qs(url.query).items()}
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                body = self.rfile.read(length).decode("utf-8", errors="replace")
                if "json" in (self.headers.get("Content-Type") or "") or body.lstrip().startswith("{"):
                    data.update(json.loads(body))
                else:
                    data.update({k: v[-1] for k, v in urllib.parse.parse_qs(body).items()})
            return url.path.rstrip("/") or "/", data

        def speak(self, data):
            text = data.get("text", data.get("input", ""))
            voice, speed = data.get("voice"), data.get("speed")
            try:
                resolve_voice(voice)
            except ValueError as e:
                warn(f"Voice error: {e}")
                return self.send_json(400, {"error": str(e)})

            gen = new_generation() if (TTS_CANCEL_OLD or TTS_PLAY_ON_PC) else None

            if TTS_PLAY_ON_PC:
                # The PC plays the voice itself; the game just gets a tiny silent clip.
                stop_playback()
                threading.Thread(target=speak_on_pc, args=(text, voice, speed, gen), daemon=True).start()
                return self.send(200, to_wav([]), "audio/wav")

            started = time.time()
            try:
                parts = list(synth_sentences(text, voice, speed, gen))
            except Cancelled:
                detail("TTS", "95", "Skipped an old line - a newer one arrived.")
                return self.send(200, to_wav([]), "audio/wav")
            except Exception as e:
                warn(f"Voice error: {e}")
                return self.send_json(400, {"error": str(e)})
            detail("TTS", "95", f"{time.time() - started:.2f}s  \"{clean_for_speech(text)[:70]}\"")
            self.send(200, to_wav(parts), "audio/wav")

        def do_GET(self):
            path, data = self.params()
            if path in ("/tts", "/v1/audio/speech") and ("text" in data or "input" in data):
                return self.speak(data)            # e.g. http://localhost:8005/tts?text=Hello
            if path in ("/voices", "/v1/audio/voices"):
                return self.send_json(200, {"voices": list(voice_names.values())})
            if path == "/":
                return self.send_json(200, {"status": "ok", "model": TTS_MODEL, "voices": list(voice_names.values()),
                                            "try_it": f"http://localhost:{TTS_PORT}/tts?text=Hello%20there&voice={TTS_VOICE}"})
            self.send_json(404, {"error": "Use POST /tts"})

        def do_POST(self):
            try:
                path, data = self.params()
            except Exception as e:
                return self.send_json(400, {"error": f"Bad request: {e}"})
            if path in ("/tts", "/v1/audio/speech"):
                return self.speak(data)
            self.send_json(404, {"error": "Use POST /tts"})

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

    return Handler


def start_tts():
    global tts_model, play_queue
    from http.server import ThreadingHTTPServer
    if is_up(f"http://127.0.0.1:{TTS_PORT}/"):
        note(f"Something is already running on port {TTS_PORT} - using that one.")
        return False
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    if not SHOW_DETAILS:
        import logging
        import warnings
        warnings.filterwarnings("ignore")
        logging.getLogger("phonemizer").setLevel(logging.ERROR)
        import onnxruntime
        onnxruntime.set_default_logger_severity(3)        # errors only
    # Kitten imports misaki's English module but never uses it; a stub saves spaCy + PyTorch.
    import types
    import misaki
    misaki.en = sys.modules.setdefault("misaki.en", types.ModuleType("misaki.en"))
    from kittentts import KittenTTS
    try:
        with quiet():
            tts_model = KittenTTS(TTS_MODEL, cache_dir=TTS_CACHE)
    except Exception as e:
        fail(f"Could not load the voice model {TTS_MODEL}: {type(e).__name__}: {e}\n"
             "        Check your internet connection (first run downloads it from huggingface.co).")
    voice_names.update({v.lower(): v for v in tts_model.available_voices})
    if TTS_VOICE.lower() not in voice_names:
        fail(f"TTS_VOICE '{TTS_VOICE}' does not exist. Choose one of: {', '.join(voice_names.values())}")
    list(synth_sentences("Hi, I am ready to talk.", TTS_VOICE, TTS_SPEED))   # warm up: first real line is fast
    if TTS_PLAY_ON_PC:
        import queue
        play_queue = queue.Queue()
        threading.Thread(target=player_loop, daemon=True).start()
        note("The voice plays through this PC's speakers (TTS_PLAY_ON_PC = True).")
    server = ThreadingHTTPServer(("0.0.0.0", TTS_PORT), make_handler())
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return True


# ------------------------------ main ------------------------------

def stop_all():
    for p in processes:
        if p.poll() is None:
            if IS_WINDOWS:
                subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                p.terminate()


def wait_for_llm(llm):
    """Wait until KoboldCpp answers. Returns True when ready."""
    url = f"http://127.0.0.1:{LLM_PORT}/api/v1/model"
    if llm is False:                     # not started (no GPU / not enough VRAM)
        return False
    if llm is None:                      # was already running
        return is_up(url)
    for _ in range(900):
        if llm.poll() is not None:
            warn(f"The LLM stopped while loading. Last lines of {os.path.relpath(LLM_LOG, BASE)}:")
            print(log_tail(LLM_LOG))
            return False
        if is_up(url):
            return True
        time.sleep(1)
    warn(f"The LLM is taking very long to load. Details in {os.path.relpath(LLM_LOG, BASE)}.")
    return False


def main():
    os.system("")   # enables colors in the Windows console
    line = "=" * 62
    if not os.environ.get("MYROBOT_RELAUNCHED"):
        print(f"{line}\n   MyRobot Local AI  -  text on the GPU, voice on the CPU\n{line}")
    ensure_environment()

    llm, llm_ok, tts_ok = None, False, False
    if LLM_ENABLED:
        step("Starting the LLM (text) ...")
        llm = start_llm()
    if TTS_ENABLED:
        step(f"Loading the voice: {TTS_VOICE} ...")
        started = time.time()
        tts_ok = start_tts()
        if tts_ok:
            done(f"Voice ready ({time.time() - started:.0f} s)")
    if LLM_ENABLED and llm is not False:
        step("Loading the LLM into the GPU ...")
        started = time.time()
        llm_ok = wait_for_llm(llm)
        if llm_ok:
            done(f"LLM ready ({time.time() - started:.0f} s)")

    all_ok = (llm_ok or not LLM_ENABLED) and (tts_ok or not TTS_ENABLED)
    print(f"\n{line}")
    if all_ok:
        print("\033[92m  ALL SET!  You can start MyRobot now.\033[0m")
    else:
        print("\033[93m  Not everything started - see the messages above.\033[0m")
    print(f"""
  In the game, press ESC -> AI Setup:

    Text Generation : Manual
                      Server address  http://localhost:{LLM_PORT}

    Text to Speech  : Self Host
                      Server address  http://localhost:{TTS_PORT}/tts
                      Parameters      text  = content   (must turn cyan)
                                      voice = {TTS_VOICE}

  Keep this window open while you play.
  Close it (or press Ctrl+C) to stop everything.
{line}
""", flush=True)

    while tts_ok or (llm and llm.poll() is None):
        time.sleep(1)
    print("Nothing is running any more.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopping ...")
    finally:
        stop_all()
