from django.contrib import admin
from .models import Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'status', 'category', 'deadline', 'created_at')
    list_filter = ('status', 'owner', 'category')
    search_fields = ('name', 'description')
    ordering = ('-created_at',)