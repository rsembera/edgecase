/**
 * AI Scribe Page JavaScript
 * Handles model loading, text generation via SSE, and save/revert
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize Lucide icons
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
    
    // Elements
    const originalText = document.getElementById('original-text');
    const generatedText = document.getElementById('generated-text');
    const actionButtons = document.querySelectorAll('.action-btn');
    const resultHint = document.getElementById('result-hint');
    const btnKeep = document.getElementById('btn-keep');
    const btnShowChanges = document.getElementById('btn-show-changes');
    const btnApplySelected = document.getElementById('btn-apply-selected');
    const diffView = document.getElementById('diff-view');
    const diffHint = document.getElementById('diff-hint');
    const btnRevert = document.getElementById('btn-revert');
    const btnCancelGeneration = document.getElementById('btn-cancel-generation');
    const loadingBanner = document.getElementById('model-loading-banner');
    
    // State
    let isGenerating = false;
    let hasGeneratedContent = false;
    let currentAction = null;
    let abortController = null;
    
    /**
     * Load the AI model if not already loaded
     */
    async function ensureModelLoaded() {
        if (window.MODEL_LOADED) {
            return true;
        }
        
        // Show loading state
        if (loadingBanner) {
            loadingBanner.style.display = 'flex';
        }
        
        try {
            const response = await fetch('/api/ai/load', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            const data = await response.json();
            
            if (data.success) {
                window.MODEL_LOADED = true;
                if (loadingBanner) {
                    loadingBanner.style.display = 'none';
                }
                return true;
            } else {
                console.error('Failed to load model:', data.error);
                showError('Failed to load AI model: ' + (data.error || 'Unknown error'));
                if (loadingBanner) {
                    loadingBanner.style.display = 'none';
                }
                return false;
            }
        } catch (error) {
            console.error('Error loading model:', error);
            showError('Error loading AI model');
            if (loadingBanner) {
                loadingBanner.style.display = 'none';
            }
            return false;
        }
    }
    
    /**
     * Show error message
     */
    function showError(message) {
        resultHint.textContent = message;
    }
    
    /**
     * Process text with the selected action
     */
    async function processText(action) {
        if (isGenerating) return;
        if (!window.MODEL_DOWNLOADED) {
            showError('AI model not downloaded');
            return;
        }
        
        const text = originalText.value.trim();
        if (!text) {
            showError('No text to process');
            return;
        }
        
        // Ensure model is loaded
        const modelReady = await ensureModelLoaded();
        if (!modelReady) return;
        
        // Start generation
        isGenerating = true;
        currentAction = action;
        generatedText.value = '';
        hasGeneratedContent = false;
        
        // Update UI
        actionButtons.forEach(btn => {
            btn.disabled = true;
            if (btn.dataset.action === action) {
                btn.classList.add('active');
            }
        });
        
        btnCancelGeneration.style.visibility = 'visible';
        resultHint.textContent = 'Streaming response...';
        btnKeep.disabled = true;
        btnRevert.disabled = true;
        segmentsCache = null;
        refreshShowChangesButton();  // hides the toggle + overlay during streaming
        
        try {
            // Create AbortController so the user can cancel the stream
            abortController = new AbortController();
            
            // Make SSE request
            const response = await fetch('/api/ai/process', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    action: action,
                    text: text
                }),
                signal: abortController.signal
            });
            
            // Check if response is SSE
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Request failed');
            }
            
            // Read SSE stream
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            
            while (true) {
                const { done, value } = await reader.read();
                
                if (done) break;
                
                buffer += decoder.decode(value, { stream: true });
                
                // Process complete SSE messages
                const lines = buffer.split('\n');
                buffer = lines.pop() || ''; // Keep incomplete line in buffer
                
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const jsonStr = line.slice(6);
                        try {
                            const data = JSON.parse(jsonStr);
                            
                            if (data.token) {
                                generatedText.value += data.token;
                                hasGeneratedContent = true;
                                // Auto-scroll to bottom
                                generatedText.scrollTop = generatedText.scrollHeight;
                            }
                            
                            if (data.done) {
                                onGenerationComplete();
                            }
                            
                            if (data.error) {
                                throw new Error(data.error);
                            }
                        } catch (e) {
                            if (e.message !== 'Unexpected end of JSON input') {
                                console.error('Error parsing SSE data:', e);
                            }
                        }
                    }
                }
            }
            
        } catch (error) {
            if (error.name === 'AbortError') {
                // User cancelled — not an error, just clean up quietly
                console.log('Generation cancelled by user');
                btnCancelGeneration.style.visibility = 'hidden';
                resultHint.textContent = hasGeneratedContent
                    ? 'Cancelled — partial result above'
                    : 'Click an action to generate';
                onGenerationComplete();
            } else {
                console.error('Generation error:', error);
                showError('Generation failed: ' + error.message);
                onGenerationComplete(true);
            }
        }
    }
    
    /**
     * Called when generation completes (success or error)
     */
    // --- Per-change review overlay (Show Changes / Apply Changes) ---
    // /api/ai/diff returns char-faithful segments (generate_diff_segments):
    // {kind: 'equal'|'change', old, new}, tiling BOTH strings completely.
    // Change chunks render as clickable toggles, ACCEPTED by default (the
    // common case is vetoing a few overreaches, not opting into each edit).
    // Apply Changes reconstructs the text from the choices and writes it
    // into the AI Result box; the normal Keep Changes flow then saves it.
    // Segment text is inserted via textContent/createTextNode ONLY — the
    // payload is data, not HTML.
    let segmentsCache = null;   // segments with an added .accepted flag
    let diffShowing = false;

    function setShowChangesLabel(showing) {
        btnShowChanges.innerHTML = showing
            ? '<i data-lucide="eye-off" class="btn-icon-sm"></i> Hide Changes'
            : '<i data-lucide="diff" class="btn-icon-sm"></i> Show Changes';
        if (typeof lucide !== 'undefined') lucide.createIcons();
    }

    function changeChunks() {
        return segmentsCache ? segmentsCache.filter(s => s.kind === 'change') : [];
    }

    function updateApplyButton() {
        const chunks = changeChunks();
        const accepted = chunks.filter(s => s.accepted).length;
        btnApplySelected.classList.toggle('btn-gone', !diffShowing || chunks.length === 0);
        if (chunks.length > 0) {
            btnApplySelected.innerHTML =
                '<i data-lucide="list-checks" class="btn-icon-sm"></i> Apply '
                + accepted + ' of ' + chunks.length + ' Changes';
            if (typeof lucide !== 'undefined') lucide.createIcons();
        }
    }

    function setChunkFace(span, seg) {
        const text = seg.accepted ? seg.new : seg.old;
        span.textContent = text;
        span.classList.toggle('accepted', seg.accepted);
        span.classList.toggle('rejected', !seg.accepted);
        // A pure insertion rejected (or pure deletion accepted) has no text
        // to show; keep a small visible handle so it stays clickable.
        span.classList.toggle('diff-chunk-empty', text === '');
        span.title = seg.accepted
            ? 'AI change — click to reject and keep your original'
            : 'Rejected — showing your original; click to re-accept the AI change';
    }

    function toggleChunk(span, seg) {
        seg.accepted = !seg.accepted;
        setChunkFace(span, seg);
        updateApplyButton();
    }

    function renderSegments() {
        diffView.textContent = '';
        segmentsCache.forEach(seg => {
            if (seg.kind === 'equal') {
                diffView.appendChild(document.createTextNode(seg.old));
                return;
            }
            const span = document.createElement('span');
            span.className = 'diff-chunk';
            span.tabIndex = 0;
            span.setAttribute('role', 'button');
            setChunkFace(span, seg);
            span.addEventListener('click', () => toggleChunk(span, seg));
            span.addEventListener('keydown', (e) => {
                if (e.key === ' ' || e.key === 'Enter') {
                    e.preventDefault();
                    toggleChunk(span, seg);
                }
            });
            diffView.appendChild(span);
        });
    }

    function hideDiff() {
        diffView.style.display = 'none';
        diffHint.style.display = 'none';
        generatedText.style.display = '';
        diffShowing = false;
        setShowChangesLabel(false);
        updateApplyButton();
    }

    async function showDiff() {
        try {
            if (segmentsCache === null) {
                const response = await fetch('/api/ai/diff', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        original: originalText.value,
                        generated: generatedText.value
                    })
                });
                const data = await response.json();
                if (!response.ok) throw new Error(data.error || 'Diff failed');
                segmentsCache = data.segments;
                segmentsCache.forEach(s => { if (s.kind === 'change') s.accepted = true; });
            }
            renderSegments();  // re-render keeps prior accept/reject choices
            // Mirror the AI Result textarea's current box height (measured
            // while it's still visible, so manual resizes are respected) so
            // the swap doesn't change the panel's size.
            diffView.style.height = generatedText.offsetHeight + 'px';
            generatedText.style.display = 'none';
            diffView.style.display = 'block';
            diffHint.style.display = 'block';
            diffShowing = true;
            setShowChangesLabel(true);
            updateApplyButton();
        } catch (error) {
            console.error('Diff error:', error);
            showError('Could not generate diff: ' + error.message);
        }
    }

    /**
     * Rebuild the result text from the per-chunk choices and put it in the
     * AI Result box (Keep Changes then saves it as usual).
     *
     * All-accepted and none-accepted short-circuit to the exact generated /
     * original strings. Mixed selections reconstruct from the segments,
     * with 'equal' segments contributing the user's ORIGINAL slice — so a
     * whitespace-only difference the model made inside an untouched run is
     * never applied silently.
     */
    function applySelected() {
        if (!segmentsCache) return;
        const chunks = changeChunks();
        const acceptedCount = chunks.filter(s => s.accepted).length;

        let text;
        if (acceptedCount === chunks.length) {
            text = generatedText.value;
        } else if (acceptedCount === 0) {
            text = originalText.value;
        } else {
            text = segmentsCache.map(s =>
                s.kind === 'equal' ? s.old : (s.accepted ? s.new : s.old)
            ).join('');
        }

        generatedText.value = text;
        hasGeneratedContent = text.trim().length > 0;
        segmentsCache = null;  // result text changed; segments are stale
        hideDiff();
        refreshShowChangesButton();
        resultHint.textContent = 'Applied ' + acceptedCount + ' of ' + chunks.length
            + ' changes — review and Keep';
    }

    function refreshShowChangesButton() {
        const usable = !isGenerating && generatedText.value.trim().length > 0;
        btnShowChanges.classList.toggle('btn-gone', !usable);
        if (!usable) hideDiff();
    }

    btnShowChanges.addEventListener('click', () => (diffShowing ? hideDiff() : showDiff()));
    btnApplySelected.addEventListener('click', applySelected);

    generatedText.addEventListener('input', () => {
        segmentsCache = null;  // edits change what a diff would show
        refreshShowChangesButton();
    });

    function onGenerationComplete(hadError = false) {
        isGenerating = false;
        abortController = null;
        
        // Re-enable buttons
        actionButtons.forEach(btn => {
            btn.disabled = !window.MODEL_DOWNLOADED;
            btn.classList.remove('active');
        });
        
        if (!hadError) {
            resultHint.textContent = 'Review and edit as needed';
        }
        btnCancelGeneration.style.visibility = 'hidden';
        
        // Enable keep/revert if we have content
        if (hasGeneratedContent) {
            btnKeep.disabled = false;
            btnRevert.disabled = false;
        }
        refreshShowChangesButton();
    }
    
    /**
     * Save the generated content back to the session entry
     */
    async function saveContent() {
        const content = generatedText.value.trim();
        if (!content) return;
        
        btnKeep.disabled = true;
        btnKeep.innerHTML = '<i data-lucide="loader" class="spinning"></i> Saving...';
        
        try {
            const response = await fetch(`/ai/scribe/${window.ENTRY_ID}/save`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ content: content })
            });
            
            const data = await response.json();
            
            if (data.success) {
                // Redirect back to the session entry
                window.location.href = `/client/${window.CLIENT_ID}/session/${window.ENTRY_ID}`;
            } else {
                throw new Error(data.error || 'Save failed');
            }
        } catch (error) {
            console.error('Save error:', error);
            showError('Failed to save: ' + error.message);
            btnKeep.disabled = false;
            btnKeep.innerHTML = '<i data-lucide="check"></i> Keep Changes';
            if (typeof lucide !== 'undefined') {
                lucide.createIcons();
            }
        }
    }

    /**
     * Revert to original text (clear generated)
     */
    function revertContent() {
        generatedText.value = '';
        hasGeneratedContent = false;
        segmentsCache = null;
        refreshShowChangesButton();
        btnKeep.disabled = true;
        btnRevert.disabled = true;
        resultHint.textContent = 'Click an action to generate';
    }
    
    /**
     * Cancel the in-flight generation request
     */
    function cancelGeneration() {
        if (abortController && isGenerating) {
            abortController.abort();
        }
    }
    
    // Event Listeners
    actionButtons.forEach(btn => {
        btn.addEventListener('click', function() {
            const action = this.dataset.action;
            if (action) {
                processText(action);
            }
        });
    });
    
    btnKeep.addEventListener('click', saveContent);
    btnRevert.addEventListener('click', revertContent);
    if (btnCancelGeneration) {
        btnCancelGeneration.addEventListener('click', cancelGeneration);
    }
    
    // Auto-load model on page load if downloaded but not loaded
    if (window.MODEL_DOWNLOADED && !window.MODEL_LOADED) {
        ensureModelLoaded();
    }
});
