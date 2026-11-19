'use strict';

const vscode = require('vscode');
const fs = require('node:fs');
const path = require('node:path');
const { randomUUID } = require('node:crypto');
const { execFile } = require('node:child_process');
const { promisify } = require('node:util');
const execute = promisify(execFile);
const DIFF_SCHEME = 'mega-replace-preview';

function inside(parent, child) {
  const rel = path.relative(parent, child);
  return rel === '' || (!path.isAbsolute(rel) && rel !== '..' && !rel.startsWith('..' + path.sep));
}

function flags(q) {
  const args = [];
  if (q.regex) args.push(q.exact ? '--regex-exact' : '--regex');
  else if (q.exact) args.push('--literal');
  else if (q.substring) args.push('--substring');
  if (q.ignored) args.push('--include-ignored');
  for (const glob of q.exclude.split(',').map(s => s.trim()).filter(Boolean)) args.push('--exclude=' + glob);
  return args;
}

function validQuery(q) {
  return q && ['find', 'replace', 'exclude'].every(k => typeof q[k] === 'string') &&
    ['regex', 'exact', 'substring', 'ignored', 'deleting'].every(k => typeof q[k] === 'boolean');
}

async function protectBuffers(folder, rows) {
  const documents = [...vscode.workspace.textDocuments, ...vscode.workspace.notebookDocuments]
    .filter(d => d.isDirty && d.uri.scheme === 'file');
  if (!documents.length) return;
  const root = await fs.promises.realpath(folder.fsPath);
  for (const doc of documents) {
    const file = await fs.promises.realpath(doc.uri.fsPath).catch(() => path.resolve(doc.uri.fsPath));
    if (!inside(root, file)) continue;
    const relative = path.relative(root, file);
    if (!rows || rows.some(row => [row.path, row.final].some(
      entry => entry === relative || (row.directory && inside(entry, relative))))) {
      throw new Error('Save or revert the unsaved changes in ' + relative + ' before continuing.');
    }
  }
}

class SearchView {
  constructor(context) {
    this.context = context;
    this.epoch = 0;
    this.busy = false;
    this.documents = new Map();
    this.media = vscode.Uri.joinPath(context.extensionUri, 'vscode', 'media');
  }

  defaultFolder() {
    const editor = vscode.window.activeTextEditor;
    const folder = (editor && vscode.workspace.getWorkspaceFolder(editor.document.uri)) || vscode.workspace.workspaceFolders?.[0];
    return folder?.uri.scheme === 'file' ? folder.uri : undefined;
  }

  post(message) { return this.view?.webview.postMessage(message); }

  sendScope() {
    this.post({type: 'scope', folder: this.folder?.fsPath, name: this.folder && path.basename(this.folder.fsPath),
      busy: this.busy});
  }

  invalidate() {
    clearTimeout(this.timer);
    this.controller?.abort();
    this.controller = undefined;
    this.review = undefined;
    return ++this.epoch;
  }

  async open(folder) {
    if (folder && !this.busy) {
      if (folder.scheme !== 'file' || !(await fs.promises.stat(folder.fsPath)).isDirectory()) {
        throw new Error('Choose a folder on a local filesystem.');
      }
      this.invalidate();
      this.folder = folder;
      this.sendScope();
    }
    await vscode.commands.executeCommand('megaReplace.search.focus');
    this.post({type: 'focus'});
  }

  async pick() {
    const selected = await vscode.window.showOpenDialog({canSelectFiles: false, canSelectFolders: true,
      canSelectMany: false, defaultUri: this.folder, openLabel: 'Search in this folder'});
    if (selected?.length) await this.open(selected[0]);
  }

  resolveWebviewView(view) {
    this.view = view;
    this.folder ??= this.defaultFolder();
    const web = view.webview;
    web.options = {enableScripts: true, localResourceRoots: [this.media]};
    const resource = name => web.asWebviewUri(vscode.Uri.joinPath(this.media, name)).toString();
    const nonce = randomUUID();
    web.html = fs.readFileSync(path.join(this.media.fsPath, 'view.html'), 'utf8')
      .replaceAll('{{source}}', web.cspSource).replaceAll('{{nonce}}', nonce)
      .replace('{{style}}', resource('view.css')).replace('{{script}}', resource('view.js'));
    web.onDidReceiveMessage(async msg => {
      try {
        if (msg.type === 'ready') this.sendScope();
        else if (msg.type === 'pick' && !this.busy) await this.pick();
        else if (msg.type === 'search' && validQuery(msg.query)) this.search(msg);
        else if (msg.type === 'apply' || msg.type === 'undo') await this.mutate(msg);
        else if (msg.type === 'open' && !this.busy) await this.openResult(msg);
      } catch (error) {
        vscode.window.showErrorMessage('Mega Replace: ' + error.message);
      }
    });
    view.onDidDispose(() => {
      if (this.view === view) {
        this.view = undefined;
        this.invalidate();
      }
    });
  }

  async run(action, folder, q, options = [], signal) {
    if (!vscode.workspace.isTrusted) throw new Error('Trust this workspace to use Mega Replace.');
    if (!['darwin', 'linux'].includes(process.platform)) throw new Error('The rename engine requires macOS or Linux.');
    const script = this.context.asAbsolutePath('mega-rename');
    const args = ['-I', '-X', 'utf8', script, action, ...options, ...(q ? flags(q) : []), '--', folder.fsPath];
    if (q) args.push(q.find, q.replace);
    try {
      const {stdout} = await execute('python3', args, {cwd: this.context.extensionPath, encoding: 'utf8',
        signal, maxBuffer: 96 * 1024 * 1024});
      return action === 'undo' ? stdout.trim() : JSON.parse(stdout);
    } catch (error) {
      if (error.code === 'ENOENT') throw new Error('Install Python 3.9 or newer and make python3 available to VS Code.');
      if (error.stderr) throw new Error(error.stderr.trim().replace(/^mega-rename: /, ''));
      throw error;
    }
  }

  search({revision, query}) {
    if (this.busy) return;
    const epoch = this.invalidate();
    const folder = this.folder;
    if (!query.find || !folder) return;
    this.timer = setTimeout(async () => {
      const controller = new AbortController();
      this.controller = controller;
      const findOnly = !query.replace && !(query.regex && query.deleting);
      try {
        const plan = await this.run('preview', folder, query, findOnly ? ['--json', '--find-only'] : ['--json'], controller.signal);
        if (epoch !== this.epoch) return;
        plan.findOnly = findOnly;
        this.review = {revision, folder, query, plan};
        this.post({type: 'result', revision, plan});
      } catch (error) {
        if (epoch === this.epoch) this.post({type: 'error', revision, message: error.message});
      } finally {
        if (this.controller === controller) this.controller = undefined;
      }
    }, 280);
  }

  async mutate({type, revision, fingerprint}) {
    if (this.busy) return;
    const review = this.review;
    const folder = this.folder;
    this.busy = true;
    this.invalidate();
    let message, failed = false;
    try {
      if (!folder) throw new Error('Choose a folder first.');
      if (type === 'undo') {
        await protectBuffers(folder);
        await this.run('undo', folder);
        message = 'Restored the last sweep.';
      } else {
        if (!review || review.revision !== revision || review.folder !== folder || review.plan.findOnly ||
            review.plan.fingerprint !== fingerprint || !(review.plan.edits || review.plan.renames)) {
          throw new Error('Refresh the results before replacing.');
        }
        await protectBuffers(folder, review.plan.results);
        const result = await this.run('apply', folder, review.query, ['--json', '--expect-plan=' + fingerprint]);
        message = 'Applied ' + result.edits + ' file edit(s) and ' + result.renames + ' rename(s).';
      }
    } catch (error) {
      failed = true;
      message = error.message;
    } finally {
      this.busy = false;
      this.post({type: 'done', error: failed, message});
    }
  }

  async openResult({index, revision}) {
    const review = this.review;
    if (!review || revision !== review.revision || !Number.isInteger(index)) return;
    const row = review.plan.results[index];
    if (!row) return;
    const uri = vscode.Uri.joinPath(review.folder, ...row.path.split('/'));
    const root = await fs.promises.realpath(review.folder.fsPath);
    if (!inside(root, await fs.promises.realpath(uri.fsPath))) throw new Error('This path has changed. Refresh the results.');
    if (row.directory) return vscode.commands.executeCommand('revealInExplorer', uri);
    if (row.hash) {
      await protectBuffers(review.folder, [row]);
      const result = await this.run('preview', review.folder, review.query,
        ['--render-file=' + row.path, '--source-hash=' + row.hash]);
      if (this.review !== review) return;
      const after = vscode.Uri.from({scheme: DIFF_SCHEME, path: '/' + randomUUID() + '/' + path.basename(row.final)});
      this.documents.set(after.toString(), result.text);
      try {
        await vscode.commands.executeCommand('vscode.diff', uri, after, row.final + ' · Mega Replace', {preview: true});
      } catch (error) {
        this.documents.delete(after.toString());
        throw error;
      }
    } else {
      const line = Math.max(0, (row.sample?.line || 1) - 1);
      await vscode.commands.executeCommand('vscode.open', uri, {selection: new vscode.Range(line, 0, line, 0), preview: true});
    }
  }
}

function activate(context) {
  const search = new SearchView(context);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider('megaReplace.search', search, {webviewOptions: {retainContextWhenHidden: true}}),
    vscode.commands.registerCommand('megaReplace.open', () => search.open()),
    vscode.commands.registerCommand('megaReplace.inFolder', uri => search.open(uri)),
    vscode.workspace.registerTextDocumentContentProvider(DIFF_SCHEME,
      {provideTextDocumentContent: uri => search.documents.get(uri.toString()) ?? ''}),
    vscode.workspace.onDidCloseTextDocument(doc => search.documents.delete(doc.uri.toString())),
    vscode.workspace.onDidChangeWorkspaceFolders(() => {
      if (!search.folder && !search.busy) { search.folder = search.defaultFolder(); search.sendScope(); }
    }),
    {dispose: () => search.invalidate()}
  );
}
module.exports = {activate};
