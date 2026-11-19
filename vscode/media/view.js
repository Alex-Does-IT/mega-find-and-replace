'use strict';

// A restored webview can replay its script in the same window. Acquire the
// bridge once and bind controls once per document body.
(function bootstrap(mount) {
  const key = Symbol.for('alexdoesitllc.mega-replace.mount');
  if (!window[key]) {
    const api = acquireVsCodeApi();
    let body, listeners;
    window[key] = () => {
      if (body === document.body) return;
      listeners?.abort();
      listeners = new AbortController();
      body = document.body;
      mount(api, listeners.signal);
    };
  }
  window[key]();
})(function mount(api, signal) {
  const $ = id => document.getElementById(id);
  let revision = 0, plan, folder, busy = false, visibleCount = 80;
  const saved = api.getState() || {};
  for (const key of ['find', 'replace', 'exclude']) $(key).value = saved[key] || '';
  for (const key of ['ignored', 'substring', 'deleting']) $(key).checked = !!saved[key];
  for (const key of ['exact', 'regex']) $(key).setAttribute('aria-pressed', String(!!saved[key]));
  const pressed = id => $(id).getAttribute('aria-pressed') === 'true';

  function input() {
    return {
      find: $('find').value, replace: $('replace').value, exclude: $('exclude').value,
      regex: pressed('regex'), exact: pressed('exact'), substring: $('substring').checked,
      ignored: $('ignored').checked, deleting: $('deleting').checked
    };
  }

  function controls() {
    for (const key of ['find', 'replace', 'exclude', 'exact', 'regex', 'ignored', 'deleting', 'scope']) $(key).disabled = busy;
    $('substring').disabled = busy || pressed('regex') || pressed('exact');
    $('deleteRow').hidden = !pressed('regex') || !!$('replace').value;
    $('apply').disabled = busy || !plan || plan.findOnly || !(plan.edits || plan.renames);
    $('undo').disabled = busy || !folder;
    $('refresh').disabled = busy || !folder || !$('find').value;
  }

  function query(clearNotice = true) {
    plan = undefined;
    visibleCount = 80;
    $('results').replaceChildren();
    $('more').hidden = true;
    if (clearNotice) $('notice').textContent = '';
    $('status').className = '';
    $('status').textContent = !folder ? 'Choose a folder to search.' : $('find').value ? 'Searching…' : '';
    const q = input();
    api.setState(q);
    api.postMessage({type: 'search', revision: ++revision, query: q});
    controls();
  }

  function textRow(className, value) {
    const el = document.createElement('span');
    el.className = className;
    el.textContent = value;
    return el;
  }

  function renderResults(start = 0) {
    const rows = plan.results;
    if (!start) $('results').replaceChildren();
    for (let i = start; i < Math.min(visibleCount, rows.length); i++) {
      const row = rows[i];
      const button = document.createElement('button');
      button.className = 'result';
      const pathText = row.path + (row.directory ? '/' : '');
      button.append(textRow('path', pathText));
      if (row.final !== row.path) button.append(textRow('destination', '→ ' + row.final));
      button.title = row.hash ? 'Open replacement diff for ' + row.path : 'Open ' + pathText;
      if (row.sample) {
        const sample = row.sample;
        button.append(textRow('snippet' + (row.hash ? ' before' : ''), sample.line + '  ' + sample.before));
        if (row.hash) button.append(textRow('snippet after', '+  ' + sample.after));
      }
      button.addEventListener('click', () => api.postMessage({type: 'open', index: i, revision}));
      $('results').append(button);
    }
    $('more').hidden = visibleCount >= rows.length;
  }
  $('more').onclick = () => { const start = visibleCount; visibleCount += 80; renderResults(start); };

  for (const key of ['find', 'replace', 'exclude', 'substring', 'ignored', 'deleting']) {
    $(key).addEventListener('input', () => query());
  }
  for (const key of ['exact', 'regex']) $(key).onclick = () => {
    $(key).setAttribute('aria-pressed', String(!pressed(key)));
    query();
  };
  $('scope').onclick = () => api.postMessage({type: 'pick'});
  $('refresh').onclick = () => query();
  $('find').onkeydown = $('replace').onkeydown = event => {
    if (event.key === 'Enter' && !event.isComposing) {
      if ((event.ctrlKey || event.metaKey) && !$('apply').disabled) $('apply').click();
      else query();
    }
  };
  for (const type of ['apply', 'undo']) $(type).onclick = () => {
    if ($(type).disabled) return;
    busy = true;
    controls();
    api.postMessage({type, revision, fingerprint: plan?.fingerprint});
  };
  window.addEventListener('message', ({data: msg}) => {
    if (msg.type === 'scope') {
      folder = msg.folder;
      $('scope').textContent = msg.name || 'Choose folder…';
      $('scope').title = folder ? folder + ' — choose a different folder' : 'Choose a folder';
      busy = msg.busy;
      query();
    } else if (msg.type === 'focus') {
      $('find').focus(); $('find').select();
    } else if (msg.type === 'done') {
      busy = false;
      $('notice').className = msg.error ? 'error' : '';
      $('notice').textContent = msg.message;
      query(false);
    } else if (msg.revision === revision && msg.type === 'error') {
      plan = undefined;
      $('status').className = 'error';
      $('status').textContent = msg.message;
      controls();
    } else if (msg.revision === revision && msg.type === 'result') {
      plan = msg.plan;
      const n = plan.results.length;
      $('status').textContent = !n ? 'No results.' : plan.findOnly
        ? n + (n === 1 ? ' matching file or folder.' : ' matching files and folders.')
        : plan.edits + (plan.edits === 1 ? ' file edit' : ' file edits') + ' · ' + plan.renames + (plan.renames === 1 ? ' rename' : ' renames');
      $('status').title = Object.entries(plan.skipped).map(([kind, count]) => count + ' ' + kind).join(', ');
      renderResults();
      controls();
    }
  }, {signal});
  controls();
  api.postMessage({type: 'ready'});
});
