from django.db import models
from django.contrib.auth.models import User
from projects.models import Project
from django.utils import timezone


class TaskCategory(models.Model):
    """Category เฉพาะสำหรับ Task (แยกออกจาก Project Category)"""
    name  = models.CharField(max_length=100)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='task_categories')

    class Meta:
        ordering = ['name']
        unique_together = ['name', 'owner']

    def __str__(self):
        return self.name


class Task(models.Model):
    STATUS_CHOICES = [
        ('todo',  'To Do'),
        ('doing', 'Doing'),
        ('done',  'Done'),
    ]
    PRIORITY_CHOICES = [
        ('low',    'Low'),
        ('medium', 'Medium'),
        ('high',   'High'),
    ]

    title       = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    status      = models.CharField(max_length=10, choices=STATUS_CHOICES, default='todo')
    priority    = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    # ใช้ TaskCategory แทน Category ของ project
    category    = models.ForeignKey(TaskCategory, on_delete=models.SET_NULL, null=True, blank=True)
    project     = models.ForeignKey(Project, on_delete=models.CASCADE)
    assigned_to = models.ForeignKey(User, on_delete=models.CASCADE)
    due_date    = models.DateField()          # ← required (ไม่มี null/blank)
    created_at  = models.DateTimeField(auto_now_add=True)

    @property
    def is_overdue(self):
        """
        Overdue if due_date is in the past and task is not completed.
        """
        if not self.due_date:
            return False
        today = timezone.localdate()
        return self.due_date < today and self.status != 'done'

    def __str__(self):
        return self.title


class Comment(models.Model):
    task       = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments')
    user       = models.ForeignKey(User, on_delete=models.CASCADE)
    message    = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.user.username}: {self.message[:40]}"