"""
AI Scribe - Local LLM Assistant for EdgeCase Equalizer
Handles model loading, unloading, and text generation.
Uses Hermes 3 with ChatML prompt format.
Auto-configures for the user's system (Mac/Windows/Linux, GPU/CPU).
"""

from pathlib import Path
from typing import Generator, Optional
import threading
import platform
import os

# Model will be loaded lazily
_llm = None
_llm_lock = threading.Lock()
_model_loaded = False

# Default model configuration
MODEL_REPO = "NousResearch/Hermes-3-Llama-3.1-8B-GGUF"
MODEL_FILENAME = "Hermes-3-Llama-3.1-8B.Q4_K_M.gguf"
MODEL_DIR = Path(__file__).parent.parent / "models"

# Generation parameters (tuned for clinical notes - low temp for consistency)
GENERATION_PARAMS = {
    'temperature': 0.3,
    'top_p': 0.9,
    'top_k': 40,
    'repeat_penalty': 1.1,
    'max_tokens': 2048,
}

# ChatML stop tokens for Hermes 3
STOP_TOKENS = ['<|im_start|>', '<|im_end|>']


def get_model_path() -> Path:
    """Get the path where the model should be stored."""
    return MODEL_DIR / MODEL_FILENAME


def is_model_downloaded() -> bool:
    """Check if the model file exists."""
    return get_model_path().exists()


def is_model_loaded() -> bool:
    """Check if the model is currently loaded in memory."""
    return _model_loaded and _llm is not None


def get_model_info() -> dict:
    """Get information about the model."""
    model_path = get_model_path()
    info = {
        'name': 'Hermes 3 Llama 3.1 8B',
        'filename': MODEL_FILENAME,
        'downloaded': model_path.exists(),
        'loaded': is_model_loaded(),
        'size_gb': None,
    }
    
    if model_path.exists():
        info['size_gb'] = round(model_path.stat().st_size / (1024**3), 2)
    
    return info


def _get_system_config() -> dict:
    """
    Auto-detect system capabilities and return optimal model configuration.
    
    Returns dict with:
        - n_gpu_layers: -1 for full GPU, 0 for CPU-only
        - n_ctx: Context window size
        - n_threads: CPU threads (for CPU/hybrid inference)
        - use_gpu: bool indicating if GPU acceleration is available
        - platform_info: Human-readable platform description
    """
    system = platform.system()
    machine = platform.machine()
    
    # Get available RAM
    try:
        import psutil
        ram_gb = psutil.virtual_memory().total / (1024**3)
    except ImportError:
        ram_gb = 16  # Assume decent RAM if psutil unavailable
    
    # Get CPU count for threading
    cpu_count = os.cpu_count() or 4
    # Use most cores but leave some for system
    n_threads = max(1, cpu_count - 2)
    
    config = {
        'n_ctx': 4096,
        'n_threads': n_threads,
        'use_gpu': False,
        'n_gpu_layers': 0,
        'platform_info': f"{system} ({machine})",
    }
    
    # macOS with Apple Silicon - Metal acceleration
    if system == 'Darwin' and machine == 'arm64':
        config['use_gpu'] = True
        config['n_gpu_layers'] = -1  # Offload all layers to Metal
        config['platform_info'] = f"Apple Silicon Mac ({ram_gb:.0f}GB RAM) - Metal GPU"
    
    # macOS with Intel - CPU only (no Metal for Intel Macs in llama.cpp)
    elif system == 'Darwin':
        config['use_gpu'] = False
        config['n_gpu_layers'] = 0
        config['platform_info'] = f"Intel Mac ({ram_gb:.0f}GB RAM) - CPU"
    
    # Windows/Linux - check for CUDA
    elif system in ('Windows', 'Linux'):
        # Try to detect CUDA availability
        cuda_available = _check_cuda_available()
        if cuda_available:
            config['use_gpu'] = True
            config['n_gpu_layers'] = -1
            config['platform_info'] = f"{system} ({ram_gb:.0f}GB RAM) - CUDA GPU"
        else:
            config['use_gpu'] = False
            config['n_gpu_layers'] = 0
            config['platform_info'] = f"{system} ({ram_gb:.0f}GB RAM) - CPU"
    
    # Adjust context based on available RAM (conservative)
    if ram_gb < 12:
        config['n_ctx'] = 2048  # Smaller context for low RAM
    elif ram_gb >= 32:
        config['n_ctx'] = 8192  # Larger context if plenty of RAM
    
    return config


def _check_cuda_available() -> bool:
    """Check if CUDA is available for GPU acceleration."""
    try:
        # Method 1: Check if llama-cpp-python was built with CUDA
        from llama_cpp import llama_supports_gpu_offload
        if llama_supports_gpu_offload():
            return True
    except (ImportError, AttributeError):
        pass
    
    try:
        # Method 2: Check for nvidia-smi (NVIDIA driver installed)
        import subprocess
        result = subprocess.run(
            ['nvidia-smi'], 
            capture_output=True, 
            timeout=5
        )
        if result.returncode == 0:
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        pass
    
    return False


def check_system_capability() -> tuple[bool, str]:
    """
    Check if the system can run the local LLM.
    Returns (can_run, message).
    """
    try:
        import psutil
        ram_gb = psutil.virtual_memory().total / (1024**3)
    except ImportError:
        ram_gb = 16
    
    # Need at least 8GB for Q4_K_M 8B model
    if ram_gb < 8:
        return False, f"Insufficient RAM ({ram_gb:.1f}GB). Need at least 8GB."
    
    # Get auto-detected config for platform info
    config = _get_system_config()
    return True, config['platform_info']


def download_model(progress_callback=None) -> bool:
    """
    Download the model from Hugging Face.
    progress_callback(current_bytes, total_bytes) is called during download.
    Returns True on success.
    """
    from huggingface_hub import hf_hub_download
    
    # Ensure models directory exists
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    
    try:
        print(f"[AI Scribe] Downloading {MODEL_FILENAME} from {MODEL_REPO}...")
        hf_hub_download(
            repo_id=MODEL_REPO,
            filename=MODEL_FILENAME,
            local_dir=MODEL_DIR,
            local_dir_use_symlinks=False,
        )
        print(f"[AI Scribe] Download complete")
        return True
    except Exception as e:
        print(f"[AI Scribe] Download failed: {e}")
        raise


def delete_model() -> bool:
    """Delete the downloaded model file."""
    global _llm, _model_loaded
    
    # Unload first if loaded
    if _model_loaded:
        unload_model()
    
    model_path = get_model_path()
    if model_path.exists():
        model_path.unlink()
        print(f"[AI Scribe] Model deleted")
        return True
    return False


def load_model() -> bool:
    """
    Load the model into memory with auto-detected optimal settings.
    Returns True on success.
    """
    global _llm, _model_loaded
    
    if _model_loaded:
        return True
    
    model_path = get_model_path()
    if not model_path.exists():
        print("[AI Scribe] Model not downloaded")
        return False
    
    with _llm_lock:
        if _model_loaded:  # Double-check after acquiring lock
            return True
        
        try:
            from llama_cpp import Llama
            
            # Get auto-detected configuration
            config = _get_system_config()
            
            print(f"[AI Scribe] Loading model from {model_path}")
            print(f"[AI Scribe] Config: n_ctx={config['n_ctx']}, n_gpu_layers={config['n_gpu_layers']}, n_threads={config['n_threads']}")
            
            _llm = Llama(
                model_path=str(model_path),
                n_ctx=config['n_ctx'],
                n_gpu_layers=config['n_gpu_layers'],
                n_threads=config['n_threads'],
                chat_format='chatml',  # Hermes 3 uses ChatML format
                verbose=False,
            )
            _model_loaded = True
            print(f"[AI Scribe] Model loaded successfully ({config['platform_info']})")
            return True
            
        except Exception as e:
            print(f"[AI Scribe] Failed to load model: {e}")
            _llm = None
            _model_loaded = False
            return False


def unload_model():
    """Unload the model from memory."""
    global _llm, _model_loaded
    
    with _llm_lock:
        if _llm is not None:
            del _llm
            _llm = None
        _model_loaded = False
        print("[AI Scribe] Model unloaded")


def generate(prompt: str, system_prompt: str = None, max_tokens: int = None) -> Generator[str, None, None]:
    """
    Generate text using chat completion with proper ChatML formatting.
    
    Args:
        prompt: The user prompt (will be formatted as user message)
        system_prompt: Optional system message (for clinical context)
        max_tokens: Maximum tokens to generate
    
    Yields:
        Generated tokens as they're produced
    """
    global _llm
    
    if not _model_loaded or _llm is None:
        raise RuntimeError("Model not loaded. Call load_model() first.")
    
    if max_tokens is None:
        max_tokens = GENERATION_PARAMS['max_tokens']
    
    # Build messages array for chat completion
    messages = []
    
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    
    messages.append({"role": "user", "content": prompt})
    
    try:
        # Use create_chat_completion for proper ChatML formatting
        stream = _llm.create_chat_completion(
            messages=messages,
            max_tokens=max_tokens,
            temperature=GENERATION_PARAMS['temperature'],
            top_p=GENERATION_PARAMS['top_p'],
            top_k=GENERATION_PARAMS['top_k'],
            repeat_penalty=GENERATION_PARAMS['repeat_penalty'],
            stop=STOP_TOKENS,
            stream=True,
        )
        
        for chunk in stream:
            if chunk and "choices" in chunk and len(chunk["choices"]) > 0:
                delta = chunk["choices"][0].get("delta", {})
                if "content" in delta:
                    token = delta["content"]
                    if token:
                        yield token
                
    except Exception as e:
        print(f"[AI Scribe] Generation error: {e}")
        raise
