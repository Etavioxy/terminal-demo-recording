import * as AsciinemaPlayer from 'asciinema-player';
import 'asciinema-player/dist/bundle/asciinema-player.css';

let player = null;
let selectedUrl = null;
let activeProject = null;
let casts = [];
let playbackSpeed = 1;
let skipIdle = true;
const PAGE_SIZE = 21;
const pageByProject = new Map();

const fileList = document.getElementById('file-list');

function getUpdatedAt(item) {
  const value = Number(item?.updatedAt);
  return Number.isFinite(value) ? value : 0;
}

function sortByUpdatedDesc(a, b) {
  const delta = getUpdatedAt(b) - getUpdatedAt(a);
  if (delta !== 0) return delta;
  return a.name.localeCompare(b.name);
}

function groupOrder(a, b, latestByProject) {
  if (a === 'demo' && b !== 'demo') return -1;
  if (a !== 'demo' && b === 'demo') return 1;
  const delta = (latestByProject.get(b) || 0) - (latestByProject.get(a) || 0);
  if (delta !== 0) return delta;
  return a.localeCompare(b);
}

function getActivePage(totalPages) {
  if (!activeProject) return 1;
  const rawPage = pageByProject.get(activeProject) || 1;
  const page = Math.min(Math.max(rawPage, 1), totalPages);
  pageByProject.set(activeProject, page);
  return page;
}

function buildPageTokens(totalPages, currentPage) {
  if (totalPages <= 7) {
    return Array.from({length: totalPages}, (_, index) => index + 1);
  }

  const tokens = [1];
  const start = Math.max(2, currentPage - 1);
  const end = Math.min(totalPages - 1, currentPage + 1);
  if (start > 2) tokens.push('ellipsis-left');
  for (let page = start; page <= end; page += 1) tokens.push(page);
  if (end < totalPages - 1) tokens.push('ellipsis-right');
  tokens.push(totalPages);
  return tokens;
}

function refreshSpeedButtons() {
  document.querySelectorAll('.controls button:not(#skip-btn)').forEach(btn => {
    const speed = Number.parseFloat(btn.textContent);
    btn.classList.toggle('active', Number.isFinite(speed) && Math.abs(speed - playbackSpeed) < 0.001);
  });
}

function refreshSkipButton() {
  const btn = document.getElementById('skip-btn');
  if (btn) btn.classList.toggle('active', skipIdle);
}

function loadCast(url, startAt = 0) {
  const container = document.getElementById('player-container');
  if (player?.dispose) {
    player.dispose();
  }
  container.innerHTML = '';
  selectedUrl = url;
  const options = {
    autoPlay: true,
    speed: playbackSpeed,
    theme: 'monokai',
  };
  if (skipIdle) {
    options.idleTimeLimit = 1;
  }
  if (startAt > 0) {
    options.startAt = startAt;
  }
  player = AsciinemaPlayer.create(url, container, options);
  refreshSpeedButtons();
}

function updateQuery(project, castName) {
  const params = new URLSearchParams(window.location.search);
  if (project) params.set('project', project);
  else params.delete('project');
  if (castName) params.set('cast', castName);
  else params.delete('cast');
  const qs = params.toString();
  window.history.replaceState(null, '', `${window.location.pathname}${qs ? `?${qs}` : ''}`);
}

function formatTime(ms) {
  const date = new Date(ms);
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  const hh = String(date.getHours()).padStart(2, '0');
  const mm = String(date.getMinutes()).padStart(2, '0');
  return `${y}-${m}-${d} ${hh}:${mm}`;
}

function renderList() {
  const groups = new Map();
  casts.forEach(item => {
    if (!groups.has(item.project)) groups.set(item.project, []);
    groups.get(item.project).push(item);
  });
  groups.forEach(list => list.sort(sortByUpdatedDesc));

  fileList.innerHTML = '';
  const latestByProject = new Map(
    [...groups.entries()].map(([project, list]) => [project, getUpdatedAt(list[0])]),
  );
  const projectNames = [...groups.keys()].sort((a, b) =>
    groupOrder(a, b, latestByProject),
  );
  if (projectNames.length === 0) {
    fileList.innerHTML = '<div class="cast-meta">No cast files found.</div>';
    return;
  }
  if (!activeProject || !groups.has(activeProject)) {
    activeProject = projectNames[0];
    if (activeProject && !pageByProject.has(activeProject)) {
      pageByProject.set(activeProject, 1);
    }
  }

  const selectorRow = document.createElement('div');
  selectorRow.className = 'selector-row';

  const label = document.createElement('span');
  label.className = 'selector-label';
  label.textContent = 'Project';
  selectorRow.appendChild(label);

  const select = document.createElement('select');
  select.className = 'project-select';
  projectNames.forEach(project => {
    const option = document.createElement('option');
    option.value = project;
    option.textContent = `${project} (${groups.get(project).length})`;
    if (project === activeProject) option.selected = true;
    select.appendChild(option);
  });
  select.onchange = () => {
    activeProject = select.value;
    const list = groups.get(activeProject) || [];
    const fallback = list.find(item => item.url === selectedUrl) || list[0];
    const fallbackIndex = fallback
      ? list.findIndex(item => item.url === fallback.url)
      : -1;
    pageByProject.set(
      activeProject,
      fallbackIndex >= 0 ? Math.floor(fallbackIndex / PAGE_SIZE) + 1 : 1,
    );
    if (fallback) loadCast(fallback.url);
    updateQuery(activeProject, fallback ? fallback.url.split('/').pop() : null);
    renderList();
  };
  selectorRow.appendChild(select);
  fileList.appendChild(selectorRow);

  const entries = groups.get(activeProject) || [];
  const totalPages = Math.max(1, Math.ceil(entries.length / PAGE_SIZE));
  const currentPage = getActivePage(totalPages);
  const start = (currentPage - 1) * PAGE_SIZE;
  const visibleEntries = entries.slice(start, start + PAGE_SIZE);
  const list = document.createElement('div');
  list.className = 'project-list';
  visibleEntries.forEach(({name, url, updatedAt, source}) => {
    const item = document.createElement('button');
    item.className = `cast-item ${selectedUrl === url ? 'active' : ''}`;
    item.onclick = () => {
      const index = entries.findIndex(entry => entry.url === url);
      if (index >= 0 && activeProject) {
        pageByProject.set(activeProject, Math.floor(index / PAGE_SIZE) + 1);
      }
      loadCast(url);
      updateQuery(activeProject, url.split('/').pop());
      renderList();
    };

    const title = document.createElement('span');
    title.className = 'cast-name';
    title.textContent = name;
    item.appendChild(title);

    const meta = document.createElement('span');
    meta.className = 'cast-meta';
    meta.textContent = `${source} • ${formatTime(updatedAt)}`;
    item.appendChild(meta);

    list.appendChild(item);
  });
  fileList.appendChild(list);

  if (totalPages > 1) {
    const paginationRow = document.createElement('div');
    paginationRow.className = 'pagination-row';

    const prev = document.createElement('button');
    prev.className = 'page-btn';
    prev.textContent = '<';
    prev.disabled = currentPage === 1;
    prev.onclick = () => {
      if (!activeProject || currentPage === 1) return;
      pageByProject.set(activeProject, currentPage - 1);
      renderList();
    };
    paginationRow.appendChild(prev);

    const tokens = buildPageTokens(totalPages, currentPage);
    tokens.forEach(token => {
      if (typeof token !== 'number') {
        const ellipsis = document.createElement('span');
        ellipsis.className = 'page-ellipsis';
        ellipsis.textContent = '...';
        paginationRow.appendChild(ellipsis);
        return;
      }

      const pageBtn = document.createElement('button');
      pageBtn.className = `page-btn ${token === currentPage ? 'active' : ''}`;
      pageBtn.textContent = String(token);
      pageBtn.onclick = () => {
        if (!activeProject) return;
        pageByProject.set(activeProject, token);
        renderList();
      };
      paginationRow.appendChild(pageBtn);
    });

    const next = document.createElement('button');
    next.className = 'page-btn';
    next.textContent = '>';
    next.disabled = currentPage === totalPages;
    next.onclick = () => {
      if (!activeProject || currentPage === totalPages) return;
      pageByProject.set(activeProject, currentPage + 1);
      renderList();
    };
    paginationRow.appendChild(next);

    const pageInfo = document.createElement('span');
    pageInfo.className = 'pagination-info';
    pageInfo.textContent = `Page ${currentPage} / ${totalPages}`;
    paginationRow.appendChild(pageInfo);

    fileList.appendChild(paginationRow);
  }
}

window.setSpeed = async s => {
  playbackSpeed = s;
  refreshSpeedButtons();
  if (!selectedUrl) return;

  let currentTime = 0;
  if (player?.getCurrentTime) {
    try {
      currentTime = (await player.getCurrentTime()) || 0;
    } catch {
      currentTime = 0;
    }
  }
  loadCast(selectedUrl, currentTime);
};

window.toggleSkip = async () => {
  skipIdle = !skipIdle;
  refreshSkipButton();
  if (!selectedUrl) return;

  let currentTime = 0;
  if (player?.getCurrentTime) {
    try {
      currentTime = (await player.getCurrentTime()) || 0;
    } catch {
      currentTime = 0;
    }
  }
  loadCast(selectedUrl, currentTime);
};

function pickInitialCast() {
  if (casts.length === 0) return null;
  const params = new URLSearchParams(window.location.search);
  const projectParam = params.get('project');
  const castParam = params.get('cast');

  if (projectParam && castParam) {
    const byUrl = casts.find(item => item.project === projectParam && item.url.endsWith(`/${castParam}`));
    if (byUrl) return byUrl;
  }

  if (projectParam) {
    const firstInProject = casts
      .filter(item => item.project === projectParam)
      .sort(sortByUpdatedDesc)[0];
    if (firstInProject) return firstInProject;
  }

  const firstDemo = casts
    .filter(item => item.project === 'demo')
    .sort(sortByUpdatedDesc)[0];
  if (firstDemo) return firstDemo;
  return [...casts].sort(sortByUpdatedDesc)[0] || null;
}

async function init() {
  const res = await fetch('./casts-index.json', {cache: 'no-store'});
  if (!res.ok) throw new Error(`Failed to load casts index: ${res.status}`);
  casts = await res.json();
  const initial = pickInitialCast();
  if (initial) {
    activeProject = initial.project;
    const projectEntries = casts
      .filter(item => item.project === initial.project)
      .sort(sortByUpdatedDesc);
    const initialIndex = projectEntries.findIndex(item => item.url === initial.url);
    pageByProject.set(
      initial.project,
      initialIndex >= 0 ? Math.floor(initialIndex / PAGE_SIZE) + 1 : 1,
    );
    loadCast(initial.url);
    updateQuery(initial.project, initial.url.split('/').pop());
  } else {
    const byProject = new Map();
    casts.forEach(item => {
      const current = byProject.get(item.project);
      const time = getUpdatedAt(item);
      if (!current || time > current) byProject.set(item.project, time);
    });
    const projectNames = [...new Set(casts.map(item => item.project))].sort((a, b) =>
      groupOrder(a, b, byProject),
    );
    activeProject = projectNames[0] || null;
    if (activeProject) pageByProject.set(activeProject, 1);
  }
  renderList();
  refreshSpeedButtons();
  refreshSkipButton();
}

init().catch(error => {
  fileList.innerHTML = `<div class="cast-meta">Failed to load casts: ${error.message}</div>`;
});
