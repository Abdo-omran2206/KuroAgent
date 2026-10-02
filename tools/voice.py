import sys
import os
import re
import asyncio
import tempfile
import subprocess
import threading
from typing import Tuple, List, Dict, Optional

# Suppress pygame's "Hello from the pygame community" startup banner
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")


VOICE_ENABLED = False
ACTIVE_VOICE = "en-US-AvaNeural"  # Default ultra-realistic ChatGPT-like female voice

# Catalog of realistic Microsoft Neural voices (human sound quality)
NEURAL_VOICES: Dict[str, str] = {
    "ava":      "en-US-AvaNeural",       # Natural Female (Warm, ChatGPT style)
    "andrew":   "en-US-AndrewNeural",    # Natural Male (Friendly & Clear)
    "emma":     "en-US-EmmaNeural",      # Natural Female (Professional)
    "brian":    "en-US-BrianNeural",     # Natural Male (Deep & Smooth)
    "guy":      "en-US-GuyNeural",       # Natural Male (Conversational)
    "jenny":    "en-US-JennyNeural",     # Natural Female (Standard)
    "ryan":     "en-GB-RyanNeural",      # British Male
    "sonia":    "en-GB-SoniaNeural",     # British Female
}


def set_voice_enabled(state: bool) -> bool:
    global VOICE_ENABLED
    VOICE_ENABLED = state
    return VOICE_ENABLED


def is_voice_enabled() -> bool:
    return VOICE_ENABLED


def set_voice_name(short_name: str) -> Tuple[bool, str]:
    """Sets the active neural voice (e.g. ava, andrew, emma, brian, guy, jenny, ryan, sonia)."""
    global ACTIVE_VOICE
    key = short_name.lower().strip()
    if key in NEURAL_VOICES:
        ACTIVE_VOICE = NEURAL_VOICES[key]
        return True, f"Voice set to ultra-realistic neural speaker '{key.upper()}' ({ACTIVE_VOICE})"
    # Check if full identifier passed
    for k, v in NEURAL_VOICES.items():
        if key == v.lower():
            ACTIVE_VOICE = v
            return True, f"Voice set to '{k.upper()}' ({v})"

    valid_list = ", ".join(NEURAL_VOICES.keys())
    return False, f"Unknown voice '{short_name}'. Available realistic voices: {valid_list}"


def get_active_voice() -> str:
    return ACTIVE_VOICE


def list_available_voices() -> Dict[str, str]:
    return NEURAL_VOICES


def speak_text(text: str, async_mode: bool = True):
    """
    TTS Output: Speaks text using Microsoft Edge Neural TTS (ultra-realistic human sound).
    Falls back to Windows SAPI5 if offline.
    """
    if not text:
        return

    # Clean text for natural speech rendering
    clean = re.sub(r'```[^\n]*\n.*?```', ' (code block omitted) ', text, flags=re.DOTALL)
    clean = re.sub(r'`[^`]+`', '', clean)
    clean = re.sub(r'[*_#~>|\[\]\(\)]', '', clean).strip()[:500]

    if not clean:
        return

    def _play_mp3(mp3_path: str) -> bool:
        """Tries multiple methods to play an MP3 file. Returns True if succeeded."""
        # Method 1: pygame (most reliable, cross-platform)
        try:
            import pygame
            pygame.mixer.init()
            pygame.mixer.music.load(mp3_path)
            pygame.mixer.music.play()
            import time as _time
            while pygame.mixer.music.get_busy():
                _time.sleep(0.05)
            pygame.mixer.music.unload()
            return True
        except Exception:
            pass

        # Method 2: playsound (simple, works on Windows)
        try:
            from playsound import playsound
            playsound(mp3_path, block=True)
            return True
        except Exception:
            pass

        # Method 3: winsound via WAV conversion (pydub required)
        try:
            wav_path = mp3_path.replace(".mp3", ".wav")
            from pydub import AudioSegment
            AudioSegment.from_mp3(mp3_path).export(wav_path, format="wav")
            import winsound
            winsound.PlaySound(wav_path, winsound.SND_FILENAME)
            try:
                os.remove(wav_path)
            except Exception:
                pass
            return True
        except Exception:
            pass

        # Method 4: PowerShell MediaPlayer (last resort)
        try:
            mp3_escaped = mp3_path.replace("\\", "/")
            ps_cmd = (
                f"Add-Type -AssemblyName presentationCore; "
                f"$p = New-Object System.Windows.Media.MediaPlayer; "
                f"$p.Open([uri]'{mp3_escaped}'); "
                f"$p.Play(); "
                f"Start-Sleep -Milliseconds 8000; "
                f"$p.Stop()"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=12,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            return True
        except Exception:
            pass

        return False

    def _worker():
        # ── Step 1: Generate MP3 via Edge-TTS (Ultra-Realistic Neural Voice) ──
        mp3_path = None
        generated_ok = False
        try:
            import edge_tts
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
            mp3_path = tmp.name
            tmp.close()

            async def _gen():
                communicate = edge_tts.Communicate(clean, ACTIVE_VOICE)
                await communicate.save(mp3_path)

            asyncio.run(_gen())
            generated_ok = os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 0
        except Exception:
            generated_ok = False

        # ── Step 2: Play the generated MP3 ──────────────────────────────────
        if generated_ok and mp3_path:
            _play_mp3(mp3_path)
            try:
                os.remove(mp3_path)
            except Exception:
                pass
            return

        # ── Step 3: SAPI5 Fallback (robotic but always works offline) ────────
        if sys.platform == "win32":
            ps_text = clean.replace("'", "''").replace('"', '`"')
            ps_script = (
                f"Add-Type -AssemblyName System.Speech; "
                f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"$s.Rate = 1; $s.Volume = 100; "
                f"$s.Speak('{ps_text}')"
            )
            try:
                subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
            except Exception:
                pass

    if async_mode:
        t = threading.Thread(target=_worker, daemon=True)
        t.start()
    else:
        _worker()


# Alias for backward compatibility
speak_text_async = speak_text


def listen_microphone() -> Tuple[bool, str]:
    """
    Speech-To-Text (STT):
    Captures user voice input from microphone using speech_recognition or Windows System.Speech.Recognition.
    """
    try:
        import speech_recognition as sr
        r = sr.Recognizer()
        with sr.Microphone() as source:
            r.adjust_for_ambient_noise(source, duration=0.5)
            audio = r.listen(source, timeout=5, phrase_time_limit=10)
            text = r.recognize_google(audio)
            return True, text
    except ImportError:
        pass
    except Exception as e:
        return False, f"Speech recognition error: {str(e)}"

    # Windows PowerShell SAPI Speech Recognition Fallback
    if sys.platform == "win32":
        ps_script = """
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$engine = New-Object System.Speech.Recognition.SpeechRecognitionEngine
$engine.SetInputToDefaultAudioDevice()
$grammar = New-Object System.Speech.Recognition.DictationGrammar
$engine.LoadGrammar($grammar)
$result = $engine.Recognize([TimeSpan]::FromSeconds(6))
if ($result) { Write-Output $result.Text } else { Write-Output "" }
"""
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            )
            out = res.stdout.strip()
            if out:
                return True, out
            return False, "No speech detected (timed out)."
        except Exception as e:
            return False, f"Voice capture failed: {str(e)}"

    return False, "Speech recognition requires microphone permissions or 'pip install SpeechRecognition pyaudio'."
