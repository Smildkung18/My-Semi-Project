from django.urls import path
from .views import (
    task_list, create_task, update_status, task_detail, edit_task, delete_task,
    create_task_category, list_task_categories, edit_task_category, delete_task_category,
    get_comments, add_comment, edit_comment, delete_comment, activity_log,
    delete_attachment,
)

urlpatterns = [
    path('<int:project_id>/',                    task_list),
    path('<int:project_id>/activity/',            activity_log),
    path('<int:project_id>/add/',                create_task),
    # ✅ specific paths MUST come before <str:status>
    path('task/<int:task_id>/detail/',           task_detail),
    path('task/<int:task_id>/edit/',             edit_task),
    path('task/<int:task_id>/delete/',           delete_task),
    # ── Comments ─────────────────────────────────────────
    path('task/<int:task_id>/comments/',         get_comments),
    path('task/<int:task_id>/comments/add/',     add_comment),
    path('comment/<int:comment_id>/edit/',       edit_comment),
    path('comment/<int:comment_id>/delete/',     delete_comment),
    # ⚠ keep this after specific endpoints (e.g. comments)
    path('task/<int:task_id>/<str:status>/',     update_status),

    # ── Task Category endpoints ──────────────────────────
    path('task-category/',                       create_task_category),
    path('task-category/list/',                  list_task_categories),
    path('task-category/<int:cat_id>/edit/',     edit_task_category),
    path('task-category/<int:cat_id>/delete/',   delete_task_category),

    # ── Task Attachments ─────────────────────────────────
    path('attachment/<int:attachment_id>/delete/', delete_attachment),
]