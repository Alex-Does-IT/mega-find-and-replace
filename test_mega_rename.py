"""Exercise the public CLI on disposable trees and simulate interrupted system calls."""
import codecs
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).with_name("mega-rename").resolve()
loader = importlib.machinery.SourceFileLoader("mega_rename", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
sweep = importlib.util.module_from_spec(spec)
sys.modules[loader.name] = sweep
loader.exec_module(sweep)


class SweepTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.root = self.tmp / "BobProject"
        self.root.mkdir()

    def run_cli(self, action, *args, success=True):
        cmd = [sys.executable, '-X', 'utf8', SCRIPT, action, self.root, *args]
        run = subprocess.run(cmd, capture_output=True, encoding='utf-8')
        self.assertEqual(run.returncode == 0, success, (cmd, run.stdout, run.stderr))
        return run.stdout if success else run.stderr

    def file(self, name, data):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p

    def test_editor_find_preview_diff_and_stale_apply(self):
        src = self.file('BobV1/BobV2.txt', b'first\nbobv3 BOBv4\n')
        pattern = r'bob(v\d+)'
        hits = json.loads(self.run_cli('preview', '--json', '--find-only', '--regex', pattern, ''))
        self.assertEqual(len(hits['results']), 2)
        self.assertEqual(hits['results'][0]['sample']['line'], 2)
        args = ('--json', '--regex', pattern, 'martin$1')
        preview = json.loads(self.run_cli('preview', *args))
        self.assertEqual((preview['edits'], preview['renames']), (1, 2))
        row = preview['results'][0]
        self.assertEqual(row['final'], 'MartinV1/MartinV2.txt')
        self.assertEqual(row['sample']['after'], 'martinv3 MARTINv4')
        render = ('--render-file', row['path'], '--source-hash', row['hash'])
        self.assertEqual(json.loads(self.run_cli('preview', *args, *render))['text'], 'first\nmartinv3 MARTINv4\n')
        guard = '--expect-plan=' + preview['fingerprint']
        src.write_bytes(b'bobv99')
        self.run_cli('preview', *args, *render, success=False)
        self.run_cli('apply', *args, guard, success=False)
        self.assertFalse((self.root / sweep.STATE).exists())
        refreshed = json.loads(self.run_cli('preview', *args))
        self.run_cli('apply', *args, '--expect-plan=' + refreshed['fingerprint'])
        self.assertEqual((self.root / row['final']).read_bytes(), b'martinv99')
        self.run_cli('undo')
        self.assertEqual(src.read_bytes(), b'bobv99')

    def test_nested_full_sweep_and_scope(self):
        original = (b'Bob bob BOB BobDoesThis bobDoesThis getBob BOB_DOES_THIS Bob2\r\n'
                    b'Bob/BobPlugins/Bob.txt Bobby bobcat kebob\r\n')
        expected = (b'Martin martin MARTIN MartinDoesThis martinDoesThis getMartin MARTIN_DOES_THIS Martin2\r\n'
                    b'Martin/MartinPlugins/Martin.txt Bobby bobcat kebob\r\n')
        src = self.file('Bob/BobPlugins/Bob.txt', original)
        src.chmod(0o751)
        before = src.stat()
        outside = self.tmp / 'Bob.txt'
        outside.write_bytes(b'Bob')
        (self.root / 'BobLink').symlink_to(outside)
        (self.root / 'BobEmpty').mkdir()
        preview = self.run_cli('preview', 'Bob', 'Martin', '--diff')
        self.assertIn('Martin/MartinPlugins/Martin.txt', preview)
        self.assertEqual(src.read_bytes(), original)
        self.assertFalse((self.root / sweep.STATE).exists())
        self.run_cli('apply', 'Bob', 'Martin')
        dst = self.root / 'Martin/MartinPlugins/Martin.txt'
        self.assertEqual(dst.read_bytes(), expected)
        self.assertEqual(stat.S_IMODE(dst.stat().st_mode), stat.S_IMODE(before.st_mode))
        self.assertTrue((self.root / 'MartinEmpty').is_dir())
        self.assertTrue((self.root / 'BobLink').is_symlink())
        self.assertEqual(outside.read_bytes(), b'Bob')
        self.run_cli('undo')
        self.assertEqual(src.read_bytes(), original)
        self.assertEqual(src.stat().st_ino, before.st_ino)
        self.assertEqual(src.stat().st_mtime_ns, before.st_mtime_ns)
        self.assertTrue((self.root / 'BobEmpty').is_dir())
        self.assertFalse(dst.exists())

    def test_word_styles_substrings_and_history(self):
        src = self.file('OldWidget.txt', b'oldWidget OldWidget OLD_WIDGET Old Widget old-widget old.widget')
        self.run_cli('apply', 'OldWidget', 'NewGadget')
        dst = self.root / 'NewGadget.txt'
        self.assertEqual(dst.read_bytes(), b'newGadget NewGadget NEW_GADGET New Gadget new-gadget new.gadget')
        dst2 = self.file('extra', b'widgetry')
        self.run_cli('apply', 'widget', 'tool', '--substring')
        self.assertEqual(dst2.read_bytes(), b'toolry')
        self.run_cli('undo')
        self.assertEqual(dst2.read_bytes(), b'widgetry')
        self.run_cli('undo')
        self.assertTrue(src.exists())

    def test_multiword_target_in_an_identifier(self):
        src = self.file('main', b'bobReads getBob BobReads BOB_READS bob_reads bob-reads')
        self.run_cli('apply', 'Bob', 'RedFox')
        self.assertEqual(src.read_bytes(), b'redFoxReads getRedFox RedFoxReads RED_FOX_READS red_fox_reads red-fox-reads')

    def test_case_aware_regex_sweep_and_undo(self):
        original = b'BobRegex/bobREGEX.txt\r\nBOBregex bobRegex bobOther\r\n'
        changed = b'MartinRegex/martinREGEX.txt\r\nMARTINregex martinRegex bobOther\r\n'
        src = self.file('BobRegex/bobREGEX.txt', original)
        outside = self.tmp / 'BobRegex.txt'
        outside.write_bytes(original)
        args = ('--regex', 'bob(regex)', 'martin$1')
        preview = self.run_cli('preview', *args, '--diff')
        self.assertIn('MartinRegex/martinREGEX.txt', preview)
        self.assertIn('+MARTINregex martinRegex bobOther', preview)
        self.assertEqual(src.read_bytes(), original)
        self.assertFalse((self.root / sweep.STATE).exists())
        self.run_cli('apply', *args)
        self.assertEqual((self.root / 'MartinRegex/martinREGEX.txt').read_bytes(), changed)
        self.assertEqual(outside.read_bytes(), original)
        self.run_cli('undo')
        self.assertEqual(src.read_bytes(), original)

    def test_regex_constraints_and_identifier_conventions(self):
        src = self.file('refs', b'oldWidget12 OldWidget7 OLD_WIDGET19 old-widget1 old-widget OLD-WIDGETX\n'
                                b'bobA12 bobx12 bobA123 getBobA12\n')
        self.run_cli('apply', '--regex', r'old[_-]?widget(\d+)', 'newGadget$1')
        self.assertTrue(src.read_bytes().startswith(
            b'newGadget12 NewGadget7 NEW_GADGET19 new-gadget1 old-widget OLD-WIDGETX\n'))
        self.run_cli('apply', '--regex', r'\bbob((?-i:[A-Z])\d{2})(?!\d)', 'martin$1')
        self.assertTrue(src.read_bytes().endswith(b'martinA12 bobx12 bobA123 getBobA12\n'))

    def test_regex_capture_template(self):
        src = self.file('notes', b'bob1-AA bob2')
        self.run_cli('apply', '--regex', r'bob(?P<num>\d)(?:-(\w+))?',
                     'x/${2}/${num}0/$1/$$/$0')
        self.assertEqual(src.read_bytes(), b'x/AA/10/1/$/bob1-AA x//20/2/$/bob2')
        self.run_cli('undo')
        self.assertEqual(src.read_bytes(), b'bob1-AA bob2')

    def test_regex_exact_and_zero_width(self):
        src = self.file('refs', b'Bob1 bob2 BOB3')
        self.run_cli('apply', '--regex-exact', r'Bob(\d)', 'fixedID$1')
        self.assertEqual(src.read_bytes(), b'fixedID1 bob2 BOB3')
        self.run_cli('apply', '--regex', r'(?=\d)', ':')
        self.assertEqual(src.read_bytes(), b'fixedID:1 bob:2 BOB:3')
        self.run_cli('apply', '--regex', r':(?=\d)', '')
        self.assertEqual(src.read_bytes(), b'fixedID1 bob2 BOB3')

    def test_regex_capture_lookaround_and_unicode_casing(self):
        src = self.file('refs', 'prefix:ÉCHO1 prefix:Écho2 Écho3'.encode())
        self.run_cli('apply', '--regex', r'(?<=(prefix):)écho(\d)', 'jalapeño$2[$1]')
        self.assertEqual(src.read_bytes(), 'prefix:JALAPEÑO1[prefix] prefix:Jalapeño2[prefix] Écho3'.encode())

    def test_regex_rejects_invalid_input_even_without_matches(self):
        for pattern, template in [('(', 'x'), ('x(y)', '$2'), ('x', '${missing}'),
                                  ('x', '${1'), ('x', '${}')]:
            with self.subTest(pattern=pattern, template=template):
                msg = self.run_cli('apply', '--regex', pattern, template, success=False)
                self.assertNotIn('Traceback', msg)
                self.assertFalse((self.root / sweep.STATE).exists())

    def test_regex_dynamic_destinations_are_checked_before_writes(self):
        ref = self.file('a-ref', b'bob1 bob2')
        src = self.file('bob1', b'bob1')
        other = self.file('bob2', b'bob2')
        for template in ('martin', '../$1', '/$1', r'priv\$1', '\n$1', '.', '..', '.git', ''):
            with self.subTest(template=template):
                self.run_cli('apply', '--regex', r'bob(\d)', template, success=False)
                self.assertEqual(src.read_bytes(), b'bob1')
                self.assertEqual(other.read_bytes(), b'bob2')
                self.assertEqual(ref.read_bytes(), b'bob1 bob2')
                self.assertFalse((self.root / sweep.STATE).exists())
        reserved = self.file('bob.git', b'bob2')
        self.run_cli('apply', '--regex', r'bob(\..+)', '$1', success=False)
        self.assertEqual(reserved.read_bytes(), b'bob2')
        self.assertFalse((self.root / '.git').exists())

    def test_binary_bom_readonly_and_hardlink(self):
        binary = b'\x00Bob\xff'
        self.file('Bob.bin', binary)
        self.file('Bob.pdf', b'%PDF-1.4 Bob')
        ext = self.tmp / 'outside'
        ext.write_bytes(b'Bob')
        os.link(ext, self.root / 'ref')
        src = self.file('utf16', codecs.BOM_UTF16_BE + 'Bob\r\n'.encode('utf-16-be'))
        src.chmod(0o440)
        mode = stat.S_IMODE(src.stat().st_mode)
        self.run_cli('apply', 'Bob', 'Martin')
        self.assertEqual((self.root / 'Martin.bin').read_bytes(), binary)
        self.assertEqual((self.root / 'Martin.pdf').read_bytes(), b'%PDF-1.4 Bob')
        self.assertEqual(ext.read_bytes(), b'Bob')
        self.assertEqual((self.root / 'ref').read_bytes(), b'Martin')
        self.assertEqual(src.read_bytes(), codecs.BOM_UTF16_BE + 'Martin\r\n'.encode('utf-16-be'))
        self.assertEqual(stat.S_IMODE(src.stat().st_mode), mode)
        self.run_cli('undo')
        self.assertTrue(ext.samefile(self.root / 'ref'))

    def test_git_ignores_and_explicit_scope(self):
        subprocess.run(['git', 'init', '-q', self.tmp], check=True)
        self.file('.gitignore', b'BobCache/\n*.log\n')
        (self.root / 'BobCache').mkdir()
        ignore = self.file('logs/Bob.log', b'Bob')
        dep = self.file('node_modules/Bob.js', b'Bob')
        hidden = self.file('.github/workflows/task.yml', b'Bob')
        explicit = self.file('BobExtra', b'Bob')
        (self.tmp / 'Bob').write_bytes(b'Bob')
        self.run_cli('apply', 'Bob', 'Martin', '--exclude', '*Extra')
        self.assertTrue(ignore.exists())
        self.assertTrue(dep.exists())
        self.assertTrue((self.root / 'BobCache').is_dir())
        self.assertEqual(hidden.read_bytes(), b'Martin')
        self.assertEqual(explicit.read_bytes(), b'Bob')
        self.assertEqual((self.tmp / 'Bob').read_bytes(), b'Bob')
        ignored = subprocess.run(['git', '-C', self.root, 'check-ignore', '-q', '.mega-rename/format'])
        self.assertEqual(ignored.returncode, 0)
        self.run_cli('undo')
        self.run_cli('apply', 'Bob', 'Martin', '--include-ignored')
        self.assertTrue((self.root / 'logs/Martin.log').is_file())
        self.assertTrue((self.root / 'MartinCache').is_dir())
        self.run_cli('undo')

    def test_git_reincluded_folder_with_only_ignored_files(self):
        subprocess.run(['git', 'init', '-q', self.root], check=True)
        self.file('.gitignore', b'*/\n!Bob/\n*.log\n')
        self.file('Bob/Bob.log', b'Bob')
        self.run_cli('apply', 'Bob', 'Martin')
        self.assertEqual((self.root / 'Martin/Bob.log').read_bytes(), b'Bob')
        self.run_cli('undo')

    def test_overlapping_words_and_size_limit(self):
        src = self.file('notes', b'xfoo foo foo')
        self.run_cli('apply', 'foo foo', 'red fox')
        self.assertEqual(src.read_bytes(), b'xfoo red fox')
        self.run_cli('undo')
        self.run_cli('apply', 'foo', 'bar', '--max-mib', '0')
        self.assertEqual(src.read_bytes(), b'xfoo foo foo')

    def test_collisions_including_dangling_link(self):
        src = self.file('Bob.txt', b'Bob')
        dst = self.file('Martin.txt', b'keep')
        ref = self.file('main', b'Bob')
        for kind in ('file', 'dangling'):
            if kind == 'dangling':
                dst.unlink()
                dst.symlink_to(self.tmp / 'missing')
            self.run_cli('apply', 'Bob', 'Martin', success=False)
            self.assertEqual(src.read_bytes(), b'Bob')
            self.assertEqual(ref.read_bytes(), b'Bob')
            self.assertFalse((self.root / sweep.STATE).exists())

    def test_case_only_literal_folder_and_file(self):
        self.file('Bob/Bob.txt', b'Bob bob BOB')
        self.run_cli('apply', 'Bob', 'BOB', '--literal')
        self.assertIn('BOB', os.listdir(self.root))
        self.assertIn('BOB.txt', os.listdir(self.root / 'BOB'))
        self.assertEqual((self.root / 'BOB/BOB.txt').read_bytes(), b'BOB bob BOB')
        self.run_cli('undo')
        self.assertIn('Bob', os.listdir(self.root))
        self.assertIn('Bob.txt', os.listdir(self.root / 'Bob'))

    def test_undo_conflicts_preserve_current_tree(self):
        self.file('Bob/Bob.txt', b'Bob')
        self.run_cli('apply', 'Bob', 'Martin')
        dst = self.root / 'Martin/Martin.txt'
        dst.write_bytes(b'later edit')
        self.run_cli('undo', success=False)
        self.assertEqual(dst.read_bytes(), b'later edit')
        dst.write_bytes(b'Martin')
        collision = self.file('Martin/Bob.txt', b'other work')
        self.run_cli('undo', success=False)
        self.assertTrue(dst.exists())
        self.assertEqual(collision.read_bytes(), b'other work')
        collision.unlink()
        self.run_cli('undo')
        self.assertEqual((self.root / 'Bob/Bob.txt').read_bytes(), b'Bob')

    def test_reserved_directory_and_invalid_name(self):
        src = self.file('Bob', b'Bob')
        self.run_cli('apply', 'Bob', '.git', '--literal', success=False)
        self.run_cli('apply', 'Bob', '../elsewhere', '--literal', success=False)
        outside = self.tmp / 'metadata'
        outside.mkdir()
        (self.root / sweep.STATE).symlink_to(outside, target_is_directory=True)
        self.run_cli('apply', 'Bob', 'Martin', success=False)
        self.assertEqual(src.read_bytes(), b'Bob')
        self.assertEqual(list(outside.iterdir()), [])

    def test_late_collision_rolls_back_edits(self):
        src = self.file('Bob', b'Bob')
        real_move = sweep.exclusive_move
        def late_collision(a, b):
            if b == self.root / 'Martin':
                b.write_bytes(b'created during apply')
            real_move(a, b)
        plan = sweep.Plan(edits=[(Path('Bob'), Path('Martin'), sweep.identity(src.stat()),
                                  sweep.digest(b'Bob'), sweep.digest(b'Martin'))],
                          renames=[(Path('Bob'), 'Martin', Path('Martin'), sweep.identity(src.stat()))])
        with mock.patch.object(sweep, 'exclusive_move', late_collision), self.assertRaises(FileExistsError):
            sweep.apply(self.root, plan, lambda s: s.replace('Bob', 'Martin'))
        self.assertEqual(src.read_bytes(), b'Bob')
        self.assertEqual((self.root / 'Martin').read_bytes(), b'created during apply')

    def test_recover_each_possible_interrupted_apply(self):
        for completed in range(7):
            with self.subTest(completed=completed):
                src = self.file('Bob/Bob.txt', b'Bob')
                plan = sweep.Plan(edits=[(Path('Bob/Bob.txt'), Path('BOB/BOB.txt'),
                                          sweep.identity(src.stat()), sweep.digest(b'Bob'), sweep.digest(b'BOB'))])
                for rel in (Path('Bob/Bob.txt'), Path('Bob')):
                    plan.renames.append((rel, rel.name.replace('Bob', 'BOB'),
                                         Path(str(rel).replace('Bob', 'BOB')), sweep.identity((self.root / rel).stat())))
                session, moves = sweep.prepare(self.root, sweep.storage(self.root, True), plan, str.upper)
                for i, move in enumerate(moves[:completed], 1):
                    sweep.status(session, 'applying', i)
                    sweep.transfer(self.root, session, move)
                # Simulate a kill after recording the next move and before its syscall.
                sweep.status(session, 'applying', min(completed+1, len(moves)))
                self.run_cli('undo')
                self.assertIn('Bob', os.listdir(self.root))
                self.assertIn('Bob.txt', os.listdir(src.parent))
                self.assertEqual(src.read_bytes(), b'Bob')

    def test_resume_interrupted_undo(self):
        src = self.file('Bob/Bob.txt', b'Bob')
        self.run_cli('apply', 'Bob', 'Martin')
        session = sweep.latest(sweep.storage(self.root))
        real_move = sweep.exclusive_move
        def interrupt_after_move(a, b):
            real_move(a, b)
            raise KeyboardInterrupt
        with mock.patch.object(sweep, 'exclusive_move', interrupt_after_move), self.assertRaises(KeyboardInterrupt):
            sweep.restore(self.root, session)
        self.run_cli('undo')
        self.assertEqual(src.read_bytes(), b'Bob')

    def test_second_process_cannot_sweep_a_locked_root(self):
        src = self.file('Bob.txt', b'Bob')
        with sweep.locked(self.root):
            self.assertIn('Another sweep', self.run_cli('apply', 'Bob', 'Martin', success=False))
        self.assertEqual(src.read_bytes(), b'Bob')
        self.assertFalse((self.root / sweep.STATE).exists())
        self.run_cli('apply', 'Bob', 'Martin')

    def test_windows_component_rules(self):
        for name in ('NUL.txt', 'CON', 'COM¹.csv', 'file.', 'file ', 'a:b', 'a\\b', 'x?', 'a' * 256):
            self.assertFalse(sweep.valid_windows_name(name), name)
        for name in ('null.txt', 'com10.txt', 'a' * 255, 'résumé.md'):
            self.assertTrue(sweep.valid_windows_name(name), name)

    @unittest.skipUnless(os.name == 'nt', 'Windows path and stream semantics')
    def test_windows_filename_validation_and_stream_preservation(self):
        src = self.file('Bob.cmd', b'Bob\r\n')
        stream = Path(str(src) + ':example')
        stream.write_bytes(b'original stream')
        for target in ('NUL', 'AUX.txt', 'Martin:', 'Martin.', 'Martin '):
            self.run_cli('apply', 'Bob.cmd', target, '--literal', success=False)
        for token in ('tree/C:escape', 'tree/..\\outside', 'tree/file:stream', 'tree/NUL'):
            with self.assertRaises(sweep.Problem):
                sweep.location(self.root, None, token)
        self.assertFalse((self.root / sweep.STATE).exists())
        self.run_cli('apply', 'Bob', 'Martin')
        self.assertEqual((self.root / 'Martin.cmd:example').read_bytes(), b'original stream')
        self.run_cli('undo')
        self.assertEqual(stream.read_bytes(), b'original stream')
        self.assertEqual(src.read_bytes(), b'Bob\r\n')

    @unittest.skipUnless(os.name == 'nt', 'Windows directory junction')
    def test_windows_junction_stays_outside_sweep_and_journal(self):
        outside = self.tmp / 'other'
        outside.mkdir()
        ref = outside / 'Bob.txt'
        ref.write_bytes(b'Bob')
        self.file('Bob.txt', b'Bob')
        def junction(path):
            subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J', str(path), str(outside)],
                           check=True, capture_output=True)
        junction(self.root / 'BobLink')
        self.run_cli('apply', 'Bob', 'Martin')
        self.assertTrue((self.root / 'BobLink').is_dir())
        self.assertEqual(ref.read_bytes(), b'Bob')
        self.run_cli('undo')
        (self.root / 'BobLink').rmdir()
        sweep.remove_session(self.root / sweep.STATE)
        junction(self.root / sweep.STATE)
        self.run_cli('apply', 'Bob', 'Martin', success=False)
        self.assertEqual(list(outside.iterdir()), [ref])


if __name__ == '__main__':
    unittest.main()
