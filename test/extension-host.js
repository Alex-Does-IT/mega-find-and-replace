'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const vscode = require('vscode');
const {SearchView} = require('../vscode/extension');

exports.run = async function () {
  const extension = vscode.extensions.getExtension('alexdoesitllc.mega-find-and-replace');
  await extension.activate();
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'Mega Replace é '));
  const folder = vscode.Uri.file(root);
  const view = new SearchView({extensionUri: extension.extensionUri, extensionPath: extension.extensionPath,
    asAbsolutePath: p => path.join(extension.extensionPath, p)});
  view.folder = folder;
  let last;
  view.post = msg => { last = msg; };
  const query = {find: 'Bob', replace: 'Martin', exclude: ''};
  const source = path.join(root, 'src', 'Bob.txt');
  const destination = path.join(root, 'src', 'Martin.txt');
  try {
    await fs.mkdir(path.dirname(source));
    await fs.writeFile(source, 'BOB\r\n');
    await vscode.commands.executeCommand('megaReplace.inFolder', folder);
    const plan = await view.run('preview', folder, query, ['--json']);
    assert.deepEqual([plan.edits, plan.renames], [1, 1]);
    const [row] = plan.results;
    assert.equal(row.path, 'src/Bob.txt');
    const rendered = await view.run('preview', folder, query,
      ['--render-file=' + row.path, '--source-hash=' + row.hash]);
    assert.equal(rendered.text, 'MARTIN\r\n');

    const uri = vscode.Uri.file(source);
    const document = await vscode.workspace.openTextDocument(uri);
    await vscode.window.showTextDocument(document);
    const change = new vscode.WorkspaceEdit();
    change.insert(uri, new vscode.Position(0, 0), 'unsaved ');
    assert.equal(await vscode.workspace.applyEdit(change), true);
    assert.equal(document.isDirty, true);
    const apply = async () => {
      view.review = {revision: 1, folder, query, plan};
      await view.mutate({type: 'apply', revision: 1, fingerprint: plan.fingerprint});
    };
    await apply();
    assert.equal(last.error, true);
    assert.match(last.message, /unsaved changes/);
    assert.equal(await fs.readFile(source, 'utf8'), 'BOB\r\n');
    await vscode.commands.executeCommand('workbench.action.files.revert');
    await vscode.commands.executeCommand('workbench.action.closeActiveEditor');
    await apply();
    assert.equal(last.error, false, last.message);
    assert.equal(await fs.readFile(destination, 'utf8'), 'MARTIN\r\n');
    await view.mutate({type: 'undo'});
    assert.equal(last.error, false, last.message);
    assert.equal(await fs.readFile(source, 'utf8'), 'BOB\r\n');
  } finally {
    view.invalidate();
    await fs.rm(root, {recursive: true, force: true});
  }
};
