"""
AI Scribe Blueprint - Routes for AI-assisted note writing
"""

from flask import Blueprint, request, Response, jsonify, render_template, redirect, url_for
import json

ai_bp = Blueprint('ai', __name__)

# Database reference (set by init_blueprint)
_db = None

def init_blueprint(db):
    """Initialize blueprint with database instance."""
    global _db
    _db = db


@ai_bp.route('/api/ai/status')
def ai_status():
    """Get current AI model status."""
    from ai import is_model_downloaded, is_model_loaded, get_model_info
    
    info = get_model_info()
    return jsonify(info)


@ai_bp.route('/api/ai/capability')
def ai_capability():
    """Check if system can run AI."""
    from ai import check_system_capability
    
    can_run, message = check_system_capability()
    return jsonify({
        'capable': can_run,
        'message': message,
    })


@ai_bp.route('/api/ai/download', methods=['POST'])
def ai_download():
    """
    Start downloading the AI model with progress updates via SSE.
    """
    from ai import is_model_downloaded, MODEL_REPO, MODEL_FILENAME, MODEL_DIR
    
    if is_model_downloaded():
        return jsonify({'success': True, 'message': 'Model already downloaded'})
    
    def download_with_progress():
        """Generator that yields SSE events during download."""
        import os
        import tempfile
        from pathlib import Path
        from huggingface_hub import HfApi
        import requests
        
        try:
            # Get file info from HuggingFace
            yield f"data: {json.dumps({'status': 'checking', 'message': 'Getting file info...'})}\n\n"
            
            try:
                api = HfApi()
                repo_info = api.repo_info(MODEL_REPO, files_metadata=True)
                total_size = None
                for sibling in repo_info.siblings:
                    if sibling.rfilename == MODEL_FILENAME:
                        total_size = sibling.size
                        break
            except Exception as e:
                print(f"[AI Scribe] Could not get file size: {e}")
                total_size = None
            
            total_gb = f"{total_size / (1024**3):.1f}" if total_size else "~7"
            yield f"data: {json.dumps({'status': 'downloading', 'message': f'Downloading model ({total_gb} GB)...', 'total': total_size})}\n\n"
            
            # Ensure models directory exists
            MODEL_DIR.mkdir(parents=True, exist_ok=True)
            
            # Construct download URL
            download_url = f"https://huggingface.co/{MODEL_REPO}/resolve/main/{MODEL_FILENAME}"
            
            # Download with streaming and progress tracking
            model_path = MODEL_DIR / MODEL_FILENAME
            temp_path = MODEL_DIR / f"{MODEL_FILENAME}.tmp"
            
            try:
                response = requests.get(download_url, stream=True, timeout=(30, None), allow_redirects=True)
                response.raise_for_status()
                
                # Get content length from response if we don't have it
                if total_size is None:
                    total_size = int(response.headers.get('content-length', 0)) or None
                
                downloaded = 0
                last_update = 0
                chunk_size = 1024 * 1024  # 1MB chunks

                # Hash incrementally while streaming so verification adds
                # no second pass over the ~5GB file.
                import hashlib
                from ai import MODEL_SHA256
                hasher = hashlib.sha256()

                with open(temp_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            hasher.update(chunk)
                            downloaded += len(chunk)
                            
                            # Send progress update every ~10MB
                            if downloaded - last_update >= 10 * 1024 * 1024:
                                progress_data = {
                                    'status': 'progress',
                                    'downloaded': downloaded,
                                    'total': total_size,
                                }
                                yield f"data: {json.dumps(progress_data)}\n\n"
                                last_update = downloaded

                # Verify against the pinned official hash before accepting.
                # A mismatch means corruption in transit or a tampered file
                # — either way it must never be loaded into memory.
                yield f"data: {json.dumps({'status': 'verifying', 'message': 'Verifying download integrity...'})}\n\n"
                if hasher.hexdigest() != MODEL_SHA256:
                    temp_path.unlink(missing_ok=True)
                    raise RuntimeError(
                        "Downloaded model failed SHA-256 verification and "
                        "was deleted. The file was corrupted in transit or "
                        "does not match the official release — try again."
                    )

                # Move temp file to final location
                temp_path.rename(model_path)
                
                yield f"data: {json.dumps({'status': 'complete', 'message': 'Download complete and verified!'})}\n\n"
                
            except Exception as e:
                # Clean up temp file on error
                if temp_path.exists():
                    temp_path.unlink()
                raise e
                
        except Exception as e:
            yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n"
    
    return Response(
        download_with_progress(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )


@ai_bp.route('/api/ai/delete', methods=['POST'])
def ai_delete():
    """Delete the downloaded model."""
    from ai import delete_model, is_model_downloaded
    
    if not is_model_downloaded():
        return jsonify({'success': True, 'message': 'Model not present'})
    
    try:
        delete_model()
        return jsonify({'success': True, 'message': 'Model deleted'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@ai_bp.route('/api/ai/delete-retired', methods=['POST'])
def ai_delete_retired():
    """Delete retired model files left behind by an earlier release.

    Only filenames on ai.assistant.RETIRED_MODELS are ever touched.
    """
    from ai import delete_retired_models

    try:
        removed = delete_retired_models()
        return jsonify({'success': True, 'removed': removed})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@ai_bp.route('/api/ai/load', methods=['POST'])
def ai_load():
    """Load the model into memory."""
    from ai import load_model, is_model_downloaded
    
    if not is_model_downloaded():
        return jsonify({'success': False, 'error': 'Model not downloaded'}), 400
    
    try:
        success = load_model()
        if success:
            return jsonify({'success': True, 'message': 'Model loaded'})
        else:
            return jsonify({'success': False, 'error': 'Failed to load model'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@ai_bp.route('/api/ai/unload', methods=['POST'])
def ai_unload():
    """Unload the model from memory."""
    from ai import unload_model
    
    unload_model()
    return jsonify({'success': True, 'message': 'Model unloaded'})


def _action_temperature(action):
    """Per-action sampling temperature.

    Proofread wants maximum determinism (0.1); every other action returns
    None, which lets generate() fall back to the GENERATION_PARAMS default
    (0.3). Agreed 2026-07-18 alongside the Gemma 4 swap.
    """
    return 0.1 if action == 'proofread' else None


@ai_bp.route('/api/ai/process', methods=['POST'])
def ai_process():
    """
    Process text with AI and stream the response.
    
    POST JSON:
        action: 'writeup', 'proofread', 'expand', or 'contract'
        text: The notes to process
    
    Returns: Server-Sent Events stream
    """
    from ai import load_model, is_model_loaded, generate, build_prompt, get_system_prompt
    
    data = request.json
    if not data:
        return jsonify({'error': 'No JSON data'}), 400
    
    action = data.get('action')
    text = data.get('text', '').strip()
    
    if not action:
        return jsonify({'error': 'No action specified'}), 400
    if not text:
        return jsonify({'error': 'No text provided'}), 400
    
    # Ensure model is loaded
    if not is_model_loaded():
        success = load_model()
        if not success:
            return jsonify({'error': 'Failed to load model'}), 500
    
    # Build prompts
    try:
        user_prompt = build_prompt(action, text)
        system_prompt = get_system_prompt()
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    
    temperature = _action_temperature(action)

    def generate_stream():
        """Generator that yields SSE events."""
        try:
            for token in generate(user_prompt, system_prompt=system_prompt,
                                  temperature=temperature):
                # Send each token as an SSE event
                yield f"data: {json.dumps({'token': token})}\n\n"
            
            # Send completion event
            yield f"data: {json.dumps({'done': True})}\n\n"
            
        except Exception as e:
            # Send error event
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return Response(
        generate_stream(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',  # Disable nginx buffering
        }
    )


@ai_bp.route('/api/ai/diff', methods=['POST'])
def ai_diff():
    """
    Word-level diff between original and generated text as char-faithful
    segments, for the Scribe per-change review overlay. Pure text
    transform: no database, no model. Returns JSON data, not HTML — the
    client renders segment text via textContent (see
    generate_diff_segments for the tiling invariants the overlay's
    Apply Selected reconstruction depends on).
    """
    from web.utils import generate_diff_segments

    data = request.get_json(silent=True) or {}
    original = data.get('original', '')
    generated = data.get('generated', '')
    if not isinstance(original, str) or not isinstance(generated, str):
        return jsonify({'error': 'original and generated must be strings'}), 400
    if len(original) > 200_000 or len(generated) > 200_000:
        return jsonify({'error': 'Text too large to diff'}), 413
    return jsonify({'segments': generate_diff_segments(original, generated)})


@ai_bp.route('/ai/scribe/<int:entry_id>')
def scribe_page(entry_id):
    """
    AI Scribe page - side-by-side editor for processing session notes.
    """
    from ai import is_model_downloaded, is_model_loaded, get_actions
    
    if not _db:
        return redirect(url_for('auth.login'))
    
    # Get the entry
    entry = _db.get_entry(entry_id)
    if not entry:
        return "Entry not found", 404
    
    # Only works with session entries
    if entry.get('class') != 'session':
        return "AI Scribe only works with session entries", 400

    # AI Scribe is deliberately only available for unlocked drafts — the
    # session form hides the Scribe button once an entry is locked. Enforce
    # that here too, so a stale tab/bookmark can't reach a locked entry.
    if _db.is_entry_locked(entry_id):
        return "AI Scribe is not available for locked sessions", 403

    # Get client info for display
    client = _db.get_client(entry.get('client_id'))
    
    return render_template('ai_scribe.html',
        entry=entry,
        client=client,
        original_text=entry.get('content', ''),
        actions=get_actions(),
        model_downloaded=is_model_downloaded(),
        model_loaded=is_model_loaded(),
    )


@ai_bp.route('/ai/scribe/<int:entry_id>/save', methods=['POST'])
def scribe_save(entry_id):
    """
    Save the AI-processed text back to the session entry.
    """
    if not _db:
        return jsonify({'error': 'Not logged in'}), 401
    
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'No JSON data'}), 400
    new_content = data.get('content', '').strip()
    
    if not new_content:
        return jsonify({'error': 'No content provided'}), 400
    
    # Get the entry
    entry = _db.get_entry(entry_id)
    if not entry:
        return jsonify({'error': 'Entry not found'}), 404
    
    # AI Scribe only operates on unlocked drafts (the session form hides
    # the Scribe button once locked; scribe_page also refuses locked
    # entries). Enforce it here as well so a direct POST can't silently
    # modify a locked clinical record — locked-entry edits must go through
    # the session edit form, which logs to edit history (M11).
    if _db.is_entry_locked(entry_id):
        return jsonify({'error': 'AI Scribe is not available for locked sessions'}), 403

    try:
        _db.update_entry(entry_id, {'content': new_content})
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
