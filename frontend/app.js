/**
 * AgentCraft — Frontend Builder App
 *
 * ALGORITHM:
 * GOAL:   Interactive AI-driven frontend builder with split-pane editor and live preview.
 * INPUT:  User intent (text description or direct HTML/CSS/JS code) + optional API key.
 * OUTPUT: Live-rendered HTML preview + generated code in the editor.
 *
 * STEPS:
 *   1. Initialize state from localStorage (projects, API key config, tier).
 *   2. Render project list in sidebar.
 *   3. Set up code editor with line numbers sync.
 *   4. Set up live preview iframe (re-renders on code change with debounce).
 *   5. Handle pane resize (drag the handle).
 *   6. Handle Build button — call Moonshot API with user intent + code context.
 *   7. Handle project CRUD (new, save, delete, switch).
 *   8. Handle API key modal and tier toggle.
 *   9. Handle export (HTML file, ZIP, GitHub).
 */

// ─────────────────────────────────────────────────────────────────
//  State
// ─────────────────────────────────────────────────────────────────

const STATE = {
  currentProjectId: null,
  currentTab: 'html',         // 'html' | 'css' | 'js'
  tier: 'free',               // 'free' | 'premium'
  apiKey: '',
  apiBaseUrl: 'https://api.moonshot.cn/v1',
  buildInProgress: false,
  isDraggingResize: false,
  projects: [],
};

// ─────────────────────────────────────────────────────────────────
//  DOM References
// ─────────────────────────────────────────────────────────────────

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const DOM = {
  // Shell
  app:          $('#app'),
  sidebar:      $('#sidebar'),
  sidebarToggle:$('#sidebar-toggle'),
  workspace:    $('#workspace'),
  newProjectBtn:$('#new-project-btn'),

  // Topbar
  projectName:  $('#project-name'),
  buildBtn:     $('#build-btn'),
  importBtn:    $('#import-btn'),
  tierBadge:    $('#tier-badge'),
  tierBadgeLabel:$('#tier-badge-label'),
  tierToggleBtn:$('#tier-toggle-btn'),
  tierLabel:    $('#tier-label'),

  // Editor
  editorPane:   $('#editor-pane'),
  codeEditor:   $('#code-editor'),
  lineNumbers:  $('#line-numbers'),
  paneTabs:     $$('.pane-tab'),
  charCount:    $('#char-count'),
  lineColInfo:  $('#line-col-info'),
  copyBtn:      $('#copy-btn'),
  formatBtn:    $('#format-btn'),

  // Preview
  previewPane:  $('#preview-pane'),
  previewFrame: $('#preview-frame'),
  previewWrapper:$('#preview-frame-wrapper'),
  deviceBtns:   $$('.device-btn'),
  refreshBtn:   $('#refresh-btn'),
  openNewTabBtn:$('#open-new-tab-btn'),
  previewStatus:$('#preview-status'),
  previewDims:  $('#preview-dimensions'),

  // Resize
  resizeHandle: $('#resize-handle'),
  panes:        $('.panes'),

  // Build panel
  buildPanel:   $('#build-panel'),
  buildLog:     $('#build-log'),
  buildStatusLabel:$('#build-status-label'),
  closeBuildPanel:$('#close-build-panel'),

  // Project list
  projectList:  $('#project-list'),

  // API key
  apiKeyBtn:    $('#api-key-btn'),
  apiKeyStatus: $('#api-key-status'),
  apiKeyModal:  $('#api-key-modal'),
  closeApiKeyModal:$('#close-api-key-modal'),
  apiKeyInput:  $('#api-key-input'),
  baseUrlInput: $('#base-url-input'),
  toggleKeyVis: $('#toggle-api-key-visibility'),
  saveApiKeyBtn:$('#save-api-key-btn'),
  clearApiKeyBtn:$('#clear-api-key-btn'),
  apiKeyError:  $('#api-key-error'),
  freeTierCard: $('#free-tier-card'),
  premiumTierCard:$('#premium-tier-card'),

  // Export
  exportModal:  $('#export-modal'),
  closeExportModal:$('#close-export-modal'),
  exportHtmlBtn:$('#export-html-btn'),
  exportZipBtn: $('#export-zip-btn'),
  exportGithubBtn:$('#export-github-btn'),
};

// ─────────────────────────────────────────────────────────────────
//  Project Management
// ─────────────────────────────────────────────────────────────────

/**
 * Generate a unique project ID.
 * @returns {string}
 */
function generateId() {
  return `proj_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

/**
 * Get all projects from localStorage.
 * @returns {Array}
 */
function loadProjects() {
  try {
    const raw = localStorage.getItem('agentcraft_projects');
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

/**
 * Persist projects to localStorage.
 * @param {Array} projects
 */
function saveProjects(projects) {
  try {
    localStorage.setItem('agentcraft_projects', JSON.stringify(projects));
  } catch (e) {
    console.warn('[AgentCraft] Could not save projects:', e);
  }
}

/**
 * Create a new project and make it active.
 * @param {string} [name]
 * @returns {object}
 */
function createProject(name) {
  const project = {
    id: generateId(),
    name: name || `Project ${STATE.projects.length + 1}`,
    html: DEFAULT_HTML,
    css:  DEFAULT_CSS,
    js:   DEFAULT_JS,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };
  STATE.projects.unshift(project);
  saveProjects(STATE.projects);
  renderProjectList();
  activateProject(project.id);
  return project;
}

/**
 * Activate a project by ID.
 * @param {string} id
 */
function activateProject(id) {
  const project = STATE.projects.find(p => p.id === id);
  if (!project) return;

  // Save current project first
  if (STATE.currentProjectId) {
    saveCurrentProject();
  }

  STATE.currentProjectId = id;
  DOM.projectName.value = project.name;
  setEditorContent(project.html);
  renderPreview();
  renderProjectList();
}

/**
 * Save the currently active project back to state + localStorage.
 */
function saveCurrentProject() {
  if (!STATE.currentProjectId) return;
  const project = STATE.projects.find(p => p.id === STATE.currentProjectId);
  if (!project) return;
  project.html = getEditorContent();
  project.updatedAt = new Date().toISOString();
  saveProjects(STATE.projects);
}

/**
 * Delete a project by ID.
 * @param {string} id
 */
function deleteProject(id) {
  STATE.projects = STATE.projects.filter(p => p.id !== id);
  saveProjects(STATE.projects);
  if (STATE.currentProjectId === id) {
    if (STATE.projects.length > 0) {
      activateProject(STATE.projects[0].id);
    } else {
      createProject();
    }
  }
  renderProjectList();
}

/**
 * Render the project list in the sidebar.
 */
function renderProjectList() {
  const html = STATE.projects.map(p => {
    const date = new Date(p.updatedAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    const active = p.id === STATE.currentProjectId ? 'active' : '';
    return `
      <div class="project-item ${active}" data-id="${p.id}" role="listitem" tabindex="0"
           aria-current="${p.id === STATE.currentProjectId ? 'true' : 'false'}">
        <i class="ti ti-file-code project-item-icon"></i>
        <span class="project-item-name">${escHtml(p.name)}</span>
        <span class="project-item-date">${date}</span>
      </div>
    `;
  }).join('');

  DOM.projectList.innerHTML = html || '<p style="padding:12px 16px;font-size:12px;color:var(--text-muted)">No projects yet.</p>';
}

// ─────────────────────────────────────────────────────────────────
//  Editor
// ─────────────────────────────────────────────────────────────────

/** Default starter HTML */
const DEFAULT_HTML = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>My Frontend</title>
  <link rel="stylesheet" href="styles.css" />
</head>
<body>
  <main class="container">
    <h1>Hello, World</h1>
    <p>Start building your frontend below.</p>
  </main>
  <script src="app.js"></script>
</body>
</html>`;

const DEFAULT_CSS = `/* AgentCraft — your styles here */
:root {
  --font-sans: system-ui, sans-serif;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: var(--font-sans);
  line-height: 1.6;
  color: #1a1a1a;
  background: #fafaf9;
  padding: 2rem;
}

.container {
  max-width: 720px;
  margin: 0 auto;
}

h1 {
  font-size: clamp(2rem, 5vw, 3rem);
  font-weight: 700;
  letter-spacing: -0.02em;
  margin-bottom: 1rem;
}`;

const DEFAULT_JS = `// AgentCraft — your JavaScript here
document.addEventListener('DOMContentLoaded', () => {
  console.log('AgentCraft: ready');
});`;

/**
 * Get current editor content.
 * @returns {string}
 */
function getEditorContent() {
  return DOM.codeEditor.value;
}

/**
 * Set editor content and update line numbers.
 * @param {string} content
 */
function setEditorContent(content) {
  DOM.codeEditor.value = content;
  updateLineNumbers();
  updateCharCount();
}

/**
 * Update line number gutter to match editor content.
 */
function updateLineNumbers() {
  const lines = DOM.codeEditor.value.split('\n').length;
  const currentLine = DOM.codeEditor.value.substring(
    0,
    DOM.codeEditor.selectionStart
  ).split('\n').length;

  const nums = Array.from({ length: lines }, (_, i) => i + 1).join('\n');
  DOM.lineNumbers.textContent = nums;

  // Sync scroll
  DOM.lineNumbers.scrollTop = DOM.codeEditor.scrollTop;

  // Update Ln/Col status
  const col = DOM.codeEditor.selectionStart -
    DOM.codeEditor.value.lastIndexOf('\n', DOM.codeEditor.selectionStart - 1);
  DOM.lineColInfo.textContent = `Ln ${currentLine}, Col ${col}`;
}

/**
 * Update character count display.
 */
function updateCharCount() {
  const count = getEditorContent().length;
  DOM.charCount.textContent = `${count.toLocaleString()} chars`;
}

/**
 * Sync editor scroll with line numbers.
 */
function syncEditorScroll() {
  DOM.lineNumbers.scrollTop = DOM.codeEditor.scrollTop;
  updateLineNumbers();
}

// ─────────────────────────────────────────────────────────────────
//  Preview
// ─────────────────────────────────────────────────────────────────

let previewDebounceTimer = null;

/**
 * Render the current editor content into the preview iframe.
 */
function renderPreview() {
  const html = buildPreviewDocument();
  const blob = new Blob([html], { type: 'text/html' });
  const url = URL.createObjectURL(blob);
  DOM.previewFrame.src = url;
  DOM.previewFrame.onload = () => {
    URL.revokeObjectURL(url);
    DOM.previewStatus.textContent = 'Rendered';
  };
}

/**
 * Debounced preview render (500ms).
 */
function schedulePreviewRender() {
  clearTimeout(previewDebounceTimer);
  previewDebounceTimer = setTimeout(renderPreview, 500);
}

/**
 * Build a complete HTML document for the preview iframe.
 * Combines HTML editor content + CSS + JS.
 * @returns {string}
 */
function buildPreviewDocument() {
  const htmlContent = getEditorContent();

  // Simple heuristic: if the editor content looks like a full HTML doc, use it directly
  if (htmlContent.trim().toLowerCase().startsWith('<!doctype') ||
      htmlContent.trim().toLowerCase().startsWith('<html')) {
    return htmlContent;
  }

  // Otherwise wrap as a full document
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <style>
    /* Reset */
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: system-ui, sans-serif; }
  </style>
</head>
<body>
${htmlContent}
</body>
</html>`;
}

// ─────────────────────────────────────────────────────────────────
//  Build — AI Code Generation
// ─────────────────────────────────────────────────────────────────

/**
 * Call the Moonshot API to generate frontend code from a text description.
 * @param {string} userIntent
 * @returns {Promise<string>} Generated HTML/CSS/JS code
 */
async function generateFrontend(userIntent) {
  const apiKey = STATE.apiKey || loadApiKey();
  if (!apiKey) {
    throw new Error('API key not configured. Please set your Moonshot API key.');
  }

  const currentCode = getEditorContent();

  const systemPrompt = `You are AgentCraft, an expert frontend engineer.
You produce clean, production-ready HTML, CSS, and JavaScript.
The user will describe what they want. Generate the complete frontend implementation.

Rules:
- Use semantic HTML5 elements
- CSS must be valid and work without any external dependencies
- JavaScript must be vanilla (no frameworks)
- Output complete code — no placeholders, no TODOs
- Use modern CSS (custom properties, flexbox, grid)
- Keep the design clean and professional — no generic AI aesthetics
- Always use a system font stack for body text
- Dark backgrounds should use #0e0e0e, not pure black
- Accent colors should be warm (amber/gold), not electric blue or purple

Respond ONLY with a JSON object in this exact format:
{
  "html": "...full HTML content...",
  "css": "...styles to add to <style> tag or CSS file...",
  "js": "...JavaScript to add to <script> tag...",
  "description": "brief description of what was built"
}`;

  const response = await fetch(`${STATE.apiBaseUrl}/chat/completions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      model: 'kimi-k2.5',
      max_tokens: 4000,
      temperature: 0.7,
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: `Current project:\n${currentCode}\n\n---\n\nUser request:\n${userIntent}` },
      ],
    }),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.error?.message || `API error: ${response.status}`);
  }

  const data = await response.json();
  const content = data.choices?.[0]?.message?.content || '';
  return parseGeneratedResponse(content);
}

/**
 * Parse the JSON response from the AI.
 * @param {string} raw
 * @returns {string} HTML code
 */
function parseGeneratedResponse(raw) {
  // Try JSON first
  try {
    const parsed = JSON.parse(raw);
    return buildFullDocument(parsed.html, parsed.css, parsed.js);
  } catch {
    // Try extracting JSON from markdown code blocks
    const match = raw.match(/```(?:json)?\s*(\{[\s\S]*?\})\s*```/);
    if (match) {
      try {
        const parsed = JSON.parse(match[1]);
        return buildFullDocument(parsed.html, parsed.css, parsed.js);
      } catch { /* fall through */ }
    }
  }
  // If parsing fails, return the raw content as HTML
  return raw;
}

/**
 * Build a full HTML document from parts.
 * @param {string} html
 * @param {string} css
 * @param {string} js
 * @returns {string}
 */
function buildFullDocument(html = '', css = '', js = '') {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Generated Frontend</title>
  <style>
${css}
  </style>
</head>
<body>
${html}
  <script>
${js}
  </script>
</body>
</html>`;
}

// ─────────────────────────────────────────────────────────────────
//  Build Panel — Log UI
// ─────────────────────────────────────────────────────────────────

/**
 * Show the build panel with a message.
 * @param {string} label
 * @param {string} [phase]
 * @param {string} [message]
 * @param {'info'|'success'|'error'} [type]
 */
function showBuildPanel(label, phase, message, type = 'info') {
  DOM.buildPanel.hidden = false;
  DOM.buildStatusLabel.textContent = label;
  if (phase && message) {
    appendBuildLog(phase, message, type);
  }
}

/**
 * Append an entry to the build log.
 * @param {string} phase
 * @param {string} message
 * @param {'info'|'success'|'error'} [type]
 */
function appendBuildLog(phase, message, type = 'info') {
  const time = new Date().toLocaleTimeString('en-US', { hour12: false });
  const entry = document.createElement('div');
  entry.className = `build-log-entry ${type}`;
  entry.innerHTML = `
    <span class="timestamp">${time}</span>
    <span class="phase">${escHtml(phase)}</span>
    <span class="message">${escHtml(message)}</span>
  `;
  DOM.buildLog.appendChild(entry);
  DOM.buildLog.scrollTop = DOM.buildLog.scrollHeight;
}

/**
 * Hide the build panel.
 */
function hideBuildPanel() {
  DOM.buildPanel.hidden = true;
  DOM.buildLog.innerHTML = '';
}

/**
 * Run the full build pipeline.
 * @param {string} userIntent  Text description from user (empty = use editor content)
 */
async function runBuild(userIntent) {
  if (STATE.buildInProgress) return;
  if (!STATE.apiKey && !loadApiKey()) {
    openApiKeyModal();
    return;
  }

  STATE.buildInProgress = true;
  DOM.buildBtn.disabled = true;
  DOM.buildBtn.innerHTML = '<i class="ti ti-loader"></i> Building...';

  showBuildPanel('Building...', '', 'Starting build pipeline');

  try {
    // Phase 1: Parse intent
    appendBuildLog('PARSE', 'Analyzing user intent and project context', 'info');

    // Phase 2: Generate
    appendBuildLog('GENERATE', 'Calling AI code generation model', 'info');
    const generated = await generateFrontend(userIntent);

    // Phase 3: Update editor
    setEditorContent(generated);
    saveCurrentProject();
    renderPreview();

    appendBuildLog('DEPLOY', 'Code ready in editor', 'success');
    DOM.buildStatusLabel.textContent = 'Build complete';
    DOM.previewStatus.textContent = 'Updated';

  } catch (err) {
    appendBuildLog('ERROR', err.message, 'error');
    DOM.buildStatusLabel.textContent = 'Build failed';
  } finally {
    STATE.buildInProgress = false;
    DOM.buildBtn.disabled = false;
    DOM.buildBtn.innerHTML = '<i class="ti ti-spark"></i> Build';
  }
}

// ─────────────────────────────────────────────────────────────────
//  Pane Resize
// ─────────────────────────────────────────────────────────────────

/**
 * Handle split-pane resize by dragging the handle.
 */
function initResize() {
  const handle = DOM.resizeHandle;
  const panes  = DOM.panes;

  handle.addEventListener('mousedown', (e) => {
    e.preventDefault();
    STATE.isDraggingResize = true;
    handle.classList.add('active');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  });

  document.addEventListener('mousemove', (e) => {
    if (!STATE.isDraggingResize) return;
    const containerRect = panes.getBoundingClientRect();
    const ratio = (e.clientX - containerRect.left) / containerRect.width;
    const clamped = Math.max(0.2, Math.min(0.8, ratio));
    panes.style.gridTemplateColumns = `${clamped} 6px ${1 - clamped}`;
  });

  document.addEventListener('mouseup', () => {
    if (!STATE.isDraggingResize) return;
    STATE.isDraggingResize = false;
    handle.classList.remove('active');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  });

  // Keyboard resize (accessibility)
  handle.addEventListener('keydown', (e) => {
    const current = panes.style.gridTemplateColumns;
    if (!current) return;
    const [, , right] = current.split(' ');
    const leftRatio = parseFloat(current.split('fr')[0]) / (parseFloat(current.split('fr')[0]) + parseFloat(right));
    if (e.key === 'ArrowLeft') {
      panes.style.gridTemplateColumns = `${Math.max(0.2, leftRatio - 0.05)}fr 6px ${1 - Math.max(0.2, leftRatio - 0.05)}fr`;
    } else if (e.key === 'ArrowRight') {
      panes.style.gridTemplateColumns = `${Math.min(0.8, leftRatio + 0.05)}fr 6px ${1 - Math.min(0.8, leftRatio + 0.05)}fr`;
    }
  });
}

// ─────────────────────────────────────────────────────────────────
//  Tab Switching
// ─────────────────────────────────────────────────────────────────

function switchTab(tabName) {
  STATE.currentTab = tabName;
  DOM.paneTabs.forEach(tab => {
    const isActive = tab.dataset.tab === tabName;
    tab.classList.toggle('active', isActive);
    tab.setAttribute('aria-selected', isActive);
  });

  // Map tab to content — in this single-editor model, we only edit HTML
  // CSS and JS are embedded; in future we'd switch editor instances
  // For now the same editor holds the active file type's content
  const project = STATE.projects.find(p => p.id === STATE.currentProjectId);
  if (!project) return;

  if (tabName === 'html') setEditorContent(project.html);
  else if (tabName === 'css')  setEditorContent(project.css);
  else if (tabName === 'js')   setEditorContent(project.js);

  updateLineNumbers();
  updateCharCount();
}

// ─────────────────────────────────────────────────────────────────
//  API Key Management
// ─────────────────────────────────────────────────────────────────

const API_KEY_STORAGE = 'agentcraft_api_key';
const API_BASE_STORAGE = 'agentcraft_api_base';

/**
 * Load API key from localStorage.
 * @returns {string}
 */
function loadApiKey() {
  try {
    return localStorage.getItem(API_KEY_STORAGE) || '';
  } catch { return ''; }
}

/**
 * Load API base URL from localStorage.
 * @returns {string}
 */
function loadApiBase() {
  try {
    return localStorage.getItem(API_BASE_STORAGE) || STATE.apiBaseUrl;
  } catch { return STATE.apiBaseUrl; }
}

/**
 * Save API key to localStorage.
 * @param {string} key
 */
function saveApiKey(key) {
  try {
    localStorage.setItem(API_KEY_STORAGE, key);
    STATE.apiKey = key;
    updateApiKeyStatus();
  } catch (e) {
    console.warn('[AgentCraft] Could not save API key:', e);
  }
}

/**
 * Update the API key status indicator in the sidebar.
 */
function updateApiKeyStatus() {
  const hasKey = !!(STATE.apiKey || loadApiKey());
  DOM.apiKeyStatus.textContent = hasKey ? 'API Key set' : 'Set API Key';
  DOM.apiKeyStatus.parentElement.classList.toggle('has-key', hasKey);
}

/**
 * Open the API key modal.
 */
function openApiKeyModal() {
  DOM.apiKeyModal.hidden = false;
  DOM.apiKeyInput.value = STATE.apiKey || loadApiKey();
  DOM.baseUrlInput.value = STATE.apiBaseUrl || loadApiBase();
  DOM.apiKeyError.hidden = true;

  // Highlight free tier by default (premium requires subscription)
  DOM.freeTierCard.style.outline = '2px solid var(--accent)';
  DOM.freeTierCard.style.outlineOffset = '-2px';
  DOM.premiumTierCard.style.outline = 'none';
}

/**
 * Close the API key modal.
 */
function closeApiKeyModal() {
  DOM.apiKeyModal.hidden = true;
}

/**
 * Validate the API key by making a test request.
 * @param {string} key
 * @param {string} baseUrl
 * @returns {Promise<boolean>}
 */
async function validateApiKey(key, baseUrl) {
  try {
    const response = await fetch(`${baseUrl}/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${key}`,
      },
      body: JSON.stringify({
        model: 'kimi-k2.5',
        max_tokens: 10,
        messages: [{ role: 'user', content: 'ping' }],
      }),
    });
    return response.ok;
  } catch {
    return false;
  }
}

// ─────────────────────────────────────────────────────────────────
//  Tier Management
// ─────────────────────────────────────────────────────────────────

/**
 * Toggle between free and premium tier.
 */
function toggleTier() {
  STATE.tier = STATE.tier === 'free' ? 'premium' : 'free';
  applyTier();
}

/**
 * Apply the current tier to the UI.
 */
function applyTier() {
  const isPremium = STATE.tier === 'premium';
  DOM.tierBadge.classList.toggle('premium', isPremium);
  DOM.tierBadgeLabel.textContent = isPremium ? 'Premium' : 'Free';
  DOM.tierLabel.textContent = isPremium ? 'AgentCraft Premium' : 'Free Tier';
}

// ─────────────────────────────────────────────────────────────────
//  Export
// ─────────────────────────────────────────────────────────────────

/**
 * Export the current project as a single HTML file.
 */
function exportAsHtml() {
  const html = buildFullDocument(
    getEditorContent(),
    STATE.projects.find(p => p.id === STATE.currentProjectId)?.css || '',
    STATE.projects.find(p => p.id === STATE.currentProjectId)?.js || ''
  );
  downloadFile(html, `${getProjectSlug()}.html`, 'text/html');
  closeExportModal();
}

/**
 * Export the current project as a folder of files.
 */
function exportAsFolder() {
  const project = STATE.projects.find(p => p.id === STATE.currentProjectId);
  if (!project) return;

  const files = {
    'index.html': buildFullDocument(project.html, project.css, project.js),
    'styles.css': project.css,
    'app.js': project.js,
  };

  // Simple download of combined structure (ZIP requires JSZip)
  const combined = `<!-- index.html -->\n${files['index.html']}\n\n<!-- styles.css -->\n/* ${'='.repeat(40)} */\n/* styles.css */\n/* ${'='.repeat(40)} */\n${files['styles.css']}\n\n/* app.js */\n/* ${'='.repeat(40)} */\n${files['app.js']}`;
  downloadFile(combined, `${getProjectSlug()}_project.html`, 'text/html');
  closeExportModal();
}

/**
 * Export to GitHub — create a new repo via gh CLI.
 */
async function exportToGithub() {
  closeExportModal();
  const slug = getProjectSlug();
  const project = STATE.projects.find(p => p.id === STATE.currentProjectId);
  if (!project) return;

  // Save current project first
  saveCurrentProject();

  // Use gh CLI to create repo and push
  const readme = `# ${project.name}\n\nGenerated by AgentCraft.\n`;
  const html = buildFullDocument(project.html, project.css, project.js);

  // Create temp directory
  const tmpDir = `/tmp/${slug}`;
  try {
    const { exec } = await import('node:fs/promises');
    await exec(`mkdir -p ${tmpDir}`);
    await exec(`cat > ${tmpDir}/README.md << 'EOF'\n${readme}\nEOF`);
    await exec(`cat > ${tmpDir}/index.html << 'EOF'\n${html}\nEOF`);
    await exec(`cd ${tmpDir} && git init && git add . && git commit -m "Initial commit from AgentCraft"`);

    // Check if gh is authenticated
    const ghCheck = await exec(`gh auth status 2>&1 || echo "NOT_AUTHED"`);
    if (ghCheck.stdout.includes('NOT_AUTHED')) {
      appendBuildLog('GITHUB', 'Please run: gh auth login', 'error');
      return;
    }

    const repoUrl = `https://github.com/${await getGithubUsername()}/${slug}.git`;
    await exec(`cd ${tmpDir} && gh repo create ${slug} --public --source=. --push`);
    appendBuildLog('GITHUB', `Repository created: ${repoUrl}`, 'success');
  } catch (err) {
    appendBuildLog('GITHUB', `Export failed: ${err.message}`, 'error');
  }
}

/**
 * Get the current project name as a URL-safe slug.
 * @returns {string}
 */
function getProjectSlug() {
  const name = DOM.projectName.value || 'frontend';
  return name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}

/**
 * Get the authenticated GitHub username.
 * @returns {Promise<string>}
 */
async function getGithubUsername() {
  try {
    const { exec } = await import('node:child_process');
    return new Promise((resolve) => {
      exec('gh api user --jq .login', (err, stdout) => {
        resolve(err ? 'user' : stdout.trim());
      });
    });
  } catch { return 'user'; }
}

/**
 * Trigger a file download in the browser.
 * @param {string} content
 * @param {string} filename
 * @param {string} mimeType
 */
function downloadFile(content, filename, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function openExportModal() {
  DOM.exportModal.hidden = false;
}

function closeExportModal() {
  DOM.exportModal.hidden = true;
}

// ─────────────────────────────────────────────────────────────────
//  Utilities
// ─────────────────────────────────────────────────────────────────

/**
 * Escape HTML special characters to prevent XSS.
 * @param {string} str
 * @returns {string}
 */
function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * Format code (basic indentation normalization).
 * @param {string} code
 * @returns {string}
 */
function formatCode(code) {
  // Very basic format: collapse multiple blank lines to one
  return code.replace(/\n{3,}/g, '\n\n').trim();
}

// ─────────────────────────────────────────────────────────────────
//  Event Binding
// ─────────────────────────────────────────────────────────────────

function bindEvents() {
  // Sidebar toggle
  DOM.sidebarToggle.addEventListener('click', () => {
    DOM.app.classList.toggle('sidebar-collapsed');
    const isCollapsed = DOM.app.classList.contains('sidebar-collapsed');
    DOM.sidebarToggle.setAttribute('aria-expanded', !isCollapsed);
    DOM.sidebarToggle.innerHTML = isCollapsed
      ? '<i class="ti ti-layout-sidebar-left-expand"></i>'
      : '<i class="ti ti-layout-sidebar-left-collapse"></i>';
  });

  // New project
  DOM.newProjectBtn.addEventListener('click', () => createProject());

  // Project list delegation
  DOM.projectList.addEventListener('click', (e) => {
    const item = e.target.closest('.project-item');
    if (!item) return;
    activateProject(item.dataset.id);
  });

  // Keyboard navigation on project items
  DOM.projectList.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      const item = e.target.closest('.project-item');
      if (item) activateProject(item.dataset.id);
    }
  });

  // Project name change
  DOM.projectName.addEventListener('change', () => {
    const project = STATE.projects.find(p => p.id === STATE.currentProjectId);
    if (project) {
      project.name = DOM.projectName.value || 'Untitled';
      saveProjects(STATE.projects);
      renderProjectList();
    }
  });

  // Editor input
  DOM.codeEditor.addEventListener('input', () => {
    updateLineNumbers();
    updateCharCount();
    schedulePreviewRender();
    saveCurrentProjectDebounced();
  });

  // Editor cursor position
  DOM.codeEditor.addEventListener('click', updateLineNumbers);
  DOM.codeEditor.addEventListener('keyup', updateLineNumbers);

  // Editor scroll sync
  DOM.codeEditor.addEventListener('scroll', syncEditorScroll);

  // Tab switching
  DOM.paneTabs.forEach(tab => {
    tab.addEventListener('click', () => switchTab(tab.dataset.tab));
  });

  // Build button
  DOM.buildBtn.addEventListener('click', async () => {
    const intent = getEditorContent().trim();
    // If the content looks like a full HTML doc with actual elements, use it directly
    // Otherwise treat the content as a text description
    const looksLikeHtml = intent.match(/^<(html|head|body|main|section|div|p|h[1-6]|ul|ol|nav|header|footer|article)/i);
    if (looksLikeHtml) {
      saveCurrentProject();
      renderPreview();
      return;
    }
    // Otherwise run AI build with the editor content as intent description
    await runBuild(intent);
  });

  // Import button
  DOM.importBtn.addEventListener('click', () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.html,.htm,.txt';
    input.onchange = async (e) => {
      const file = e.target.files?.[0];
      if (!file) return;
      const text = await file.text();
      setEditorContent(text);
      saveCurrentProject();
      renderPreview();
    };
    input.click();
  });

  // Copy button
  DOM.copyBtn.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(getEditorContent());
      DOM.copyBtn.innerHTML = '<i class="ti ti-check"></i>';
      setTimeout(() => {
        DOM.copyBtn.innerHTML = '<i class="ti ti-copy"></i>';
      }, 1500);
    } catch {
      // Fallback
      DOM.codeEditor.select();
      document.execCommand('copy');
    }
  });

  // Format button
  DOM.formatBtn.addEventListener('click', () => {
    const formatted = formatCode(getEditorContent());
    setEditorContent(formatted);
    saveCurrentProject();
  });

  // Refresh preview
  DOM.refreshBtn.addEventListener('click', renderPreview);

  // Open in new tab
  DOM.openNewTabBtn.addEventListener('click', () => {
    const html = buildPreviewDocument();
    const blob = new Blob([html], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank');
  });

  // Device switcher
  DOM.deviceBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const device = btn.dataset.device;
      DOM.deviceBtns.forEach(b => b.setAttribute('aria-pressed', 'false'));
      btn.setAttribute('aria-pressed', 'true');
      DOM.previewWrapper.dataset.device = device;
      const width = device === 'mobile' ? '375px' : device === 'tablet' ? '768px' : '100%';
      DOM.previewDims.textContent = device === 'mobile' ? '375px' : device === 'tablet' ? '768px' : '100%';
    });
  });

  // Build panel close
  DOM.closeBuildPanel.addEventListener('click', hideBuildPanel);

  // API key modal
  DOM.apiKeyBtn.addEventListener('click', openApiKeyModal);
  DOM.closeApiKeyModal.addEventListener('click', closeApiKeyModal);
  DOM.saveApiKeyBtn.addEventListener('click', async () => {
    const key = DOM.apiKeyInput.value.trim();
    const baseUrl = DOM.baseUrlInput.value.trim() || STATE.apiBaseUrl;

    if (key) {
      DOM.apiKeyError.hidden = true;
      const valid = await validateApiKey(key, baseUrl);
      if (!valid) {
        DOM.apiKeyError.textContent = 'Invalid API key. Please check and try again.';
        DOM.apiKeyError.hidden = false;
        return;
      }
    }

    saveApiKey(key);
    STATE.apiBaseUrl = baseUrl;
    try { localStorage.setItem(API_BASE_STORAGE, baseUrl); } catch {}
    closeApiKeyModal();
  });

  DOM.clearApiKeyBtn.addEventListener('click', () => {
    DOM.apiKeyInput.value = '';
    STATE.apiKey = '';
    try { localStorage.removeItem(API_KEY_STORAGE); } catch {}
    updateApiKeyStatus();
    closeApiKeyModal();
  });

  // Toggle API key visibility
  DOM.toggleKeyVis.addEventListener('click', () => {
    const isPassword = DOM.apiKeyInput.type === 'password';
    DOM.apiKeyInput.type = isPassword ? 'text' : 'password';
    DOM.toggleKeyVis.innerHTML = isPassword
      ? '<i class="ti ti-eye-off"></i>'
      : '<i class="ti ti-eye"></i>';
  });

  // Tier toggle
  DOM.tierToggleBtn.addEventListener('click', toggleTier);
  DOM.tierBadge.addEventListener('click', toggleTier);

  // Tier card selection (visual only — premium is display-only)
  DOM.premiumTierCard.addEventListener('click', () => {
    DOM.premiumTierCard.style.outline = '2px solid var(--accent)';
    DOM.freeTierCard.style.outline = 'none';
  });
  DOM.freeTierCard.addEventListener('click', () => {
    DOM.freeTierCard.style.outline = '2px solid var(--accent)';
    DOM.premiumTierCard.style.outline = 'none';
  });

  // Export modal
  DOM.exportHtmlBtn.addEventListener('click', exportAsHtml);
  DOM.exportZipBtn.addEventListener('click', exportAsFolder);
  DOM.exportGithubBtn.addEventListener('click', exportToGithub);

  // Modal backdrop click to close
  DOM.apiKeyModal.addEventListener('click', (e) => {
    if (e.target === DOM.apiKeyModal) closeApiKeyModal();
  });
  DOM.exportModal.addEventListener('click', (e) => {
    if (e.target === DOM.exportModal) closeExportModal();
  });

  // Keyboard shortcuts
  document.addEventListener('keydown', (e) => {
    // Cmd/Ctrl+S — save project
    if ((e.metaKey || e.ctrlKey) && e.key === 's') {
      e.preventDefault();
      saveCurrentProject();
    }
    // Cmd/Ctrl+B — build
    if ((e.metaKey || e.ctrlKey) && e.key === 'b') {
      e.preventDefault();
      DOM.buildBtn.click();
    }
  });
}

// ─────────────────────────────────────────────────────────────────
//  Save Debounce
// ─────────────────────────────────────────────────────────────────

let saveDebounceTimer = null;

function saveCurrentProjectDebounced() {
  clearTimeout(saveDebounceTimer);
  saveDebounceTimer = setTimeout(saveCurrentProject, 1000);
}

// ─────────────────────────────────────────────────────────────────
//  Init
// ─────────────────────────────────────────────────────────────────

async function init() {
  // Load persisted state
  STATE.apiKey = loadApiKey();
  STATE.apiBaseUrl = loadApiBase();
  STATE.projects = loadProjects();
  STATE.tier = localStorage.getItem('agentcraft_tier') || 'free';

  // Apply tier
  applyTier();
  updateApiKeyStatus();

  // Ensure at least one project exists
  if (STATE.projects.length === 0) {
    createProject('My First Frontend');
  } else {
    // Activate the most recent project
    activateProject(STATE.projects[0].id);
  }

  // Bind all events
  bindEvents();

  // Initialize resize
  initResize();

  // Initial preview render
  renderPreview();

  console.log('[AgentCraft] Initialized');
}

// Start the app
init();
