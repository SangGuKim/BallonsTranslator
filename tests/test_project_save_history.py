import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from ballontranslator.utils.proj_imgtrans import ProjImgTrans
from ballontranslator.utils.textblock import TextBlock


class ProjectSaveHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        Image.new('RGB', (40, 40), 'white').save(self.root / '01.png')
        self.project = ProjImgTrans(str(self.root))
        self.path = Path(self.project.proj_path)
        self.history = self.root / '.project_history' / self.path.name

    def snapshots(self) -> list[bytes]:
        return [p.read_bytes() for p in self.history.glob('*.json')]

    def test_changed_saves_keep_every_previous_version_and_reopen(self) -> None:
        first = self.path.read_bytes()
        self.project.pages['01.png'] = [TextBlock(text=['原文'], translation='첫째')]
        self.project.save(save_history=True)
        second = self.path.read_bytes()
        self.project.pages['01.png'][0].translation = '둘째'
        self.project.save(save_history=True)
        self.assertCountEqual(self.snapshots(), [first, second])
        self.assertEqual(ProjImgTrans(str(self.root)).pages['01.png'][0].translation, '둘째')

    def test_identical_save_does_not_add_history(self) -> None:
        self.project.save()
        self.project.save()
        self.assertFalse(self.snapshots())

    def test_legacy_backup_is_archived_before_replacement(self) -> None:
        legacy = Path(str(self.path) + '.backup')
        old_legacy = b'{"old": "backup"}'
        legacy.write_bytes(old_legacy)
        previous = self.path.read_bytes()
        self.project.pages['01.png'] = [TextBlock(translation='changed')]
        self.project.save(keep_exist_as_backup=True)
        self.assertEqual(legacy.read_bytes(), previous)
        self.assertFalse(self.snapshots())

    def test_history_failure_keeps_existing_project(self) -> None:
        previous = self.path.read_bytes()
        self.project.pages['01.png'] = [TextBlock(translation='changed')]
        with patch.object(self.project, 'backup', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.project.save(save_history=True)
        self.assertEqual(self.path.read_bytes(), previous)
        self.assertFalse(list(self.root.glob('.project-save-*.tmp')))

    def test_replace_failure_keeps_existing_project_and_history(self) -> None:
        import os

        previous = self.path.read_bytes()
        self.project.pages['01.png'] = [TextBlock(translation='changed')]
        replace = os.replace

        def fail_project_replace(source, destination):
            if str(destination) == str(self.path):
                raise OSError('project locked')
            return replace(source, destination)

        with patch('ballontranslator.utils.proj_imgtrans.os.replace', side_effect=fail_project_replace):
            with self.assertRaises(OSError):
                self.project.save(save_history=True)
        self.assertEqual(self.path.read_bytes(), previous)
        self.assertEqual(self.snapshots(), [previous])
        self.assertFalse(list(self.root.glob('.project-save-*.tmp')))

    def test_automatic_save_does_not_add_history(self) -> None:
        self.project.pages['01.png'] = [TextBlock(translation='automatic')]
        self.project.save()
        self.assertFalse(self.snapshots())
        self.assertEqual(ProjImgTrans(str(self.root)).pages['01.png'][0].translation, 'automatic')

    def test_explicit_snapshot_does_not_change_project(self) -> None:
        previous = self.path.read_bytes()
        snapshot = self.project.backup()
        self.assertEqual(Path(snapshot).read_bytes(), previous)
        self.assertEqual(self.path.read_bytes(), previous)

