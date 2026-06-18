# tasks/management/commands/check_due_dates.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from tasks.models import Task
from projects.models import Project, Notification


class Command(BaseCommand):
    help = 'Create notifications for tasks and projects due within 3 days'

    def handle(self, *args, **kwargs):
        today    = timezone.now().date()
        in_3days = today + timedelta(days=3)
        task_count    = self._check_tasks(today, in_3days)
        project_count = self._check_projects(today, in_3days)
        self.stdout.write(
            f'Created {task_count} task + {project_count} project deadline notifications.'
        )

    # ── Task notifications ────────────────────────────────
    def _check_tasks(self, today, in_3days):
        upcoming = Task.objects.filter(
            due_date__range=[today, in_3days]
        ).exclude(status='done').select_related('assigned_to', 'project')

        count = 0
        for task in upcoming:
            already = Notification.objects.filter(
                user=task.assigned_to,
                notif_type='due_soon',
                message__contains=task.title,
                created_at__date=today,
            ).exists()

            if not already:
                days_left = (task.due_date - today).days
                if days_left == 0:
                    time_str = 'due today!'
                elif days_left == 1:
                    time_str = 'due tomorrow'
                else:
                    time_str = f'due in {days_left} days'

                Notification.objects.create(
                    user=task.assigned_to,
                    message=f'⏰ Task "{task.title}" is {time_str} ({task.project.name})',
                    notif_type='due_soon',
                )
                count += 1
        return count

    # ── Project deadline notifications ────────────────────
    def _check_projects(self, today, in_3days):
        upcoming = Project.objects.filter(
            deadline__range=[today, in_3days]
        ).exclude(status='completed').select_related('owner')

        count = 0
        for project in upcoming:
            already = Notification.objects.filter(
                user=project.owner,
                notif_type='due_soon',
                message__contains=project.name,
                created_at__date=today,
            ).exists()

            if not already:
                days_left = (project.deadline - today).days
                if days_left == 0:
                    time_str = 'deadline is today!'
                elif days_left == 1:
                    time_str = 'deadline is tomorrow'
                else:
                    time_str = f'deadline in {days_left} days'

                Notification.objects.create(
                    user=project.owner,
                    message=f'📁 Project "{project.name}" {time_str}',
                    notif_type='due_soon',
                )
                count += 1
        return count
