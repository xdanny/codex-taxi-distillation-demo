const selector = document.querySelector('#selector');
const video = document.querySelector('#video');
const activeTitle = document.querySelector('#active-title');
const receipt = document.querySelector('#receipt');
const comparisonBody = document.querySelector('#comparison-body');
const downloadTitle = document.querySelector('#download-title');
const downloadList = document.querySelector('#download-list');
const stageButton = document.querySelector('#stage-button');
const takeSelect = document.querySelector('#take-select');
const experimentLabel = document.querySelector('#experiment-label');

let manifest;
let activeRunId;

const formatDuration = (seconds) => {
  const rounded = Math.round(Number(seconds));
  return `${Math.floor(rounded / 60)}m ${String(rounded % 60).padStart(2, '0')}s`;
};

const formatTokens = (run) =>
  new Intl.NumberFormat('en-US').format(Number(run.inputTokens) + Number(run.outputTokens));

const treatmentCopy = {
  'qwen-bare': 'dbt + DuckDB skills',
  'qwen-skill': 'dbt + DuckDB + distilled Taxi skill',
  terra: 'dbt + DuckDB skills',
};

function renderSelector() {
  const primaryRuns = manifest.recordings.filter((run) => run.primary);
  const active = manifest.recordings.find((run) => run.id === activeRunId);
  selector.replaceChildren(...primaryRuns.map((run) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `run-button${run.arm === active?.arm ? ' active' : ''}`;
    button.innerHTML = `
      <strong>${run.label}</strong>
      <span class="duration">${formatDuration(run.duration)}</span>
      <small>${run.runId}</small>
    `;
    button.addEventListener('click', () => selectRun(run.id));
    return button;
  }));
}

function renderTakeSelector(run) {
  const takes = manifest.recordings.filter((item) => item.arm === run.arm);
  takeSelect.replaceChildren(...takes.map((take) => {
    const option = document.createElement('option');
    option.value = take.id;
    option.textContent = `${take.takeLabel} · ${formatDuration(take.elapsedSeconds)}`;
    option.selected = take.id === run.id;
    return option;
  }));
  takeSelect.disabled = takes.length === 1;
}

function renderReceipt(run) {
  const cells = [
    ['Run ID', run.runId, ''],
    ['Model route', `${run.model} · ${run.provider}`, ''],
    ['Mounted skills', String(run.skills.length), ''],
    ['Elapsed', formatDuration(run.elapsedSeconds), ''],
    ['Outside verifier', run.accepted ? 'Accepted' : 'Not accepted', run.accepted ? 'accepted' : ''],
  ];
  receipt.innerHTML = cells.map(([label, value, className]) => `
    <div class="${className}"><span>${label}</span><strong>${value}</strong></div>
  `).join('');
}

function renderDownloads(run) {
  downloadTitle.textContent = `Files for ${run.label}`;
  const files = [
    ['Raw Codex event stream', run.evidence['events.jsonl']],
    ['Model request and prompt', run.evidence['request.json']],
    ['Outside verifier result', run.evidence['verification.json']],
    ['Run receipt and usage', run.evidence['run.json']],
    ['Mounted-input receipt', run.evidence['input-receipt.json']],
    ['Terminal replay source', run.cast],
    ['Download MP4', run.video],
  ];
  downloadList.innerHTML = files.map(([label, href]) => `
    <a href="${href}" target="_blank" rel="noreferrer">
      <strong>${label}</strong><code>${href.split('/').at(-1)}</code>
    </a>
  `).join('');
}

function selectRun(runId) {
  activeRunId = runId;
  const run = manifest.recordings.find((item) => item.id === runId);
  if (!run) return;
  const wasPlaying = !video.paused;
  video.src = run.video;
  video.poster = run.poster;
  activeTitle.textContent = run.label;
  renderSelector();
  renderTakeSelector(run);
  renderReceipt(run);
  renderDownloads(run);
  if (wasPlaying) video.play().catch(() => {});
}

function renderComparison() {
  comparisonBody.innerHTML = manifest.recordings.map((run) => `
    <tr>
      <td><strong>${run.label}</strong><br><code>${run.runId}</code></td>
      <td>${run.takeLabel}</td>
      <td><code>${run.model}<br>${run.provider}</code></td>
      <td>${treatmentCopy[run.arm]}</td>
      <td>${formatDuration(run.elapsedSeconds)}</td>
      <td>${formatTokens(run)}<br><code>${new Intl.NumberFormat('en-US').format(run.cachedInputTokens)} cached input</code></td>
      <td class="${run.accepted ? 'status-pass' : ''}">${run.accepted ? 'Accepted' : 'Not accepted'}</td>
    </tr>
  `).join('');
}

takeSelect.addEventListener('change', () => selectRun(takeSelect.value));

stageButton.addEventListener('click', async () => {
  if (document.fullscreenElement) {
    await document.exitFullscreen();
  } else {
    await video.requestFullscreen();
  }
});

fetch('assets/manifest.json')
  .then((response) => {
    if (!response.ok) throw new Error(`manifest returned ${response.status}`);
    return response.json();
  })
  .then((loaded) => {
    manifest = loaded;
    experimentLabel.textContent = `Experiment ${manifest.experimentId}`;
    renderComparison();
    activeRunId = manifest.recordings.find((run) => run.arm === 'qwen-bare' && run.primary)?.id;
    selectRun(activeRunId);
  })
  .catch((error) => {
    activeTitle.textContent = 'Recordings are not built yet';
    receipt.innerHTML = `<div><span>Next step</span><strong>uv run taxi-demo record-demos</strong></div>`;
    console.error(error);
  });
