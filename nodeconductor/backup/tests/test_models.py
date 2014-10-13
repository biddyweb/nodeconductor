from __future__ import unicode_literals

from datetime import timedelta
from mock import patch, MagicMock

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from nodeconductor.backup.tests import factories
from nodeconductor.backup import models
from nodeconductor.backup import tasks


class BackupScheduleTest(TestCase):

    def test_update_next_trigger_at(self):
        now = timezone.now()
        schedule = factories.BackupScheduleFactory.build()
        schedule.schedule = '*/10 * * * *'
        schedule._update_next_trigger_at()
        self.assertTrue(schedule.next_trigger_at)
        self.assertGreater(schedule.next_trigger_at, now)

    def test_create_backup(self):
        now = timezone.now()
        schedule = factories.BackupScheduleFactory(retention_time=3)
        schedule._create_backup()
        backup = models.Backup.objects.get(backup_schedule=schedule)
        self.assertFalse(backup.kept_until is None)
        self.assertGreater(backup.kept_until, now - timedelta(days=schedule.retention_time))

    def test_execute(self):
        # we have schedule
        schedule = factories.BackupScheduleFactory(maximal_number_of_backups=1)
        # with 2 backups ready backups
        old_backup1 = factories.BackupFactory(backup_schedule=schedule)
        old_backup2 = factories.BackupFactory(backup_schedule=schedule)
        # and 1 deleted
        deleted_backup = factories.BackupFactory(backup_schedule=schedule, state=models.Backup.States.DELETED)

        schedule.execute()
        # after execution old backups have to be deleted
        old_backup1 = models.Backup.objects.get(pk=old_backup1.pk)
        self.assertEqual(old_backup1.state, models.Backup.States.DELETING)
        old_backup2 = models.Backup.objects.get(pk=old_backup2.pk)
        self.assertEqual(old_backup2.state, models.Backup.States.DELETING)
        # deleted backup have to stay deleted
        self.assertEqual(deleted_backup.state, models.Backup.States.DELETED)
        # new backup have to be created
        self.assertTrue(models.Backup.objects.filter(
            backup_schedule=schedule, state=models.Backup.States.BACKING_UP).exists())
        # and schedule time have to be changed
        self.assertGreater(schedule.next_trigger_at, timezone.now())

    def test_save(self):
        # new schedule
        schedule = factories.BackupScheduleFactory(next_trigger_at=None)
        self.assertGreater(schedule.next_trigger_at, timezone.now())
        # schedule become active
        schedule.is_active = False
        schedule.next_trigger_at = None
        schedule.save()
        schedule.is_active = True
        schedule.save()
        self.assertGreater(schedule.next_trigger_at, timezone.now())
        # schedule was changed
        schedule.next_trigger_at = None
        schedule.schedule = '*/10 * * * *'
        schedule.save()
        self.assertGreater(schedule.next_trigger_at, timezone.now())


class BackupTest(TestCase):

    mocked_task_result = type(str('MockedTaskResult'), (object, ), {'id': 'result_id'})

    class MockedAsyncResult(object):

        def __call__(self, *args):
            return self if not self._is_none else None

        def __init__(self, ready, is_none=False):
            self._ready = ready
            self._is_none = is_none

        def ready(self):
            return self._ready

    def test_save(self):
        backup = factories.BackupFactory()
        with self.assertRaises(IntegrityError):
            backup.save()

    @patch('nodeconductor.backup.tasks.backup_task.delay', return_value=mocked_task_result)
    def test_start_backup(self, mocked_task):
        backup = factories.BackupFactory()
        backup.start_backup()
        mocked_task.assert_called_with(backup.backup_source)
        self.assertEqual(backup.result_id, BackupTest.mocked_task_result().id)
        self.assertEqual(backup.state, models.Backup.States.BACKING_UP)

    @patch('nodeconductor.backup.tasks.restoration_task.delay', return_value=mocked_task_result)
    def test_start_restoration(self, mocked_task):
        backup = factories.BackupFactory()
        backup.start_restoration()
        mocked_task.assert_called_with(backup.backup_source, replace_original=False)
        self.assertEqual(backup.result_id, BackupTest.mocked_task_result().id)
        self.assertEqual(backup.state, models.Backup.States.RESTORING)

    @patch('nodeconductor.backup.tasks.deletion_task.delay', return_value=mocked_task_result)
    def test_start_deletion(self, mocked_task):
        backup = factories.BackupFactory()
        backup.start_deletion()
        mocked_task.assert_called_with(backup.backup_source)
        self.assertEqual(backup.result_id, BackupTest.mocked_task_result().id)
        self.assertEqual(backup.state, models.Backup.States.DELETING)

    def test_check_task_result(self):
        backup = factories.BackupFactory()
        # result is ready:
        task = type(str('MockedTask'), (object, ), {'AsyncResult': self.MockedAsyncResult(True)})
        mocked_func = MagicMock()
        backup._check_task_result(task, mocked_func)
        mocked_func.assert_called_with()
        # result is not ready:
        task = type(str('MockedTask'), (object, ), {'AsyncResult': self.MockedAsyncResult(False)})
        mocked_func = MagicMock()
        backup._check_task_result(task, mocked_func)
        self.assertFalse(mocked_func.called)
        # no result:
        task = type(str('MockedTask'), (object, ), {'AsyncResult': self.MockedAsyncResult(True, is_none=True)})
        mocked_func = MagicMock()
        backup._check_task_result(task, mocked_func)
        self.assertFalse(mocked_func.called)
        self.assertEqual(backup.state, models.Backup.States.ERRED)

    def test_poll_current_state(self):
        # backup
        backup = factories.BackupFactory(state=models.Backup.States.BACKING_UP)
        backup._check_task_result = MagicMock()
        backup.poll_current_state()
        backup._check_task_result.assert_called_with(tasks.backup_task, backup._confirm_backup)
        # restoration
        backup = factories.BackupFactory(state=models.Backup.States.RESTORING)
        backup._check_task_result = MagicMock()
        backup.poll_current_state()
        backup._check_task_result.assert_called_with(tasks.restoration_task, backup._confirm_restoration)
        # deletion
        backup = factories.BackupFactory(state=models.Backup.States.DELETING)
        backup._check_task_result = MagicMock()
        backup.poll_current_state()
        backup._check_task_result.assert_called_with(tasks.deletion_task, backup._confirm_deletion)