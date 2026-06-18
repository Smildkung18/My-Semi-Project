from django.contrib import admin
from .models import Task, Comment


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'project', 'assigned_to', 'status', 'priority', 'category', 'due_date', 'created_at')
    list_filter = ('status', 'priority', 'project', 'project__owner', 'assigned_to', 'category')
    search_fields = ('title', 'description', 'project__name', 'assigned_to__username')
    ordering = ('-created_at',)


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('user', 'task', 'created_at')
    list_filter = ('user', 'task__project', 'task__project__owner')
    search_fields = ('message', 'user__username', 'task__title', 'task__project__name')
    ordering = ('-created_at',)