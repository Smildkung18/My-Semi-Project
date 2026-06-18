from django.urls import path, include
from django.contrib.auth.views import LogoutView
from .views import (
    project_list, create_project, edit_project, delete_project,
    user_login, user_register,
    password_reset_request, password_reset_verify, password_reset_done,
    terms_view, privacy_view,
    my_tasks, team, settings_view, delete_account, help_view, profile_view, public_profile_view,
    personal_analytics, team_analytics,
    reports_view, export_excel, export_pdf,
    get_notifications, mark_notifications_read,
    # ── Team management ──────────────────────────────────
    team_remove_member, team_update_projects, team_member_projects, team_check_user,
    # ── Project member actions ───────────────────────────
    project_leave, project_request_upgrade,
    # ── File management ──────────────────────────────────
    file_manager, upload_file, file_detail, download_file, update_file_permissions, delete_file, rename_file,
    get_project_tasks, get_tasks,
    # ── Category management ─────────────────────────────
    create_category, edit_category, delete_category, list_categories,
)

urlpatterns = [
    path('',                                        project_list),
    path('project/',                                include('tasks.urls')),
    path('project/create/',                         create_project),
    path('project/category/',                       create_category),
    path('project/category/list/',                  list_categories),
    path('project/category/<int:cat_id>/edit/',     edit_category),
    path('project/category/<int:cat_id>/delete/',   delete_category),
    path('project/edit/<int:project_id>/',          edit_project),
    path('project/delete/<int:project_id>/',        delete_project),
    path('project/<int:project_id>/leave/',         project_leave),
    path('project/<int:project_id>/request-upgrade/', project_request_upgrade),

    # ── Auth ──────────────────────────────────────────────────
    path('login/',                                  user_login),
    path('logout/',                                 LogoutView.as_view(next_page='/login/'), name='logout'),
    path('register/',                               user_register),

    # ── Password Reset ────────────────────────────────────────
    path('password-reset/',                         password_reset_request),
    path('password-reset/verify/',                  password_reset_verify),
    path('password-reset/done/',                    password_reset_done),

    path('terms/',                                  terms_view),
    path('privacy/',                                privacy_view),
    path('my-tasks/',                               my_tasks),
    path('analytics/',                              personal_analytics),
    path('analytics/team/',                         team_analytics),

    # ── Reports & Export ──────────────────────────────────────
    path('reports/',                                reports_view),
    path('reports/export/excel/',                   export_excel),
    path('reports/export/pdf/',                     export_pdf),
    path('settings/',                               settings_view),
    path('profile/',                                profile_view, name='profile'),
    path('profile/<int:user_id>/',                     public_profile_view, name='public_profile'),
    path('profile/<str:username>/',                   public_profile_view, name='public_profile_username'),
    path('settings/delete/',                        delete_account),
    path('help/',                                   help_view),
    path('notifications/',                          get_notifications),
    path('notifications/read/',                     mark_notifications_read),
    
    # ── File Management ─────────────────────────────────────
    path('files/',                                  file_manager),
    path('files/upload/',                           upload_file),
    path('files/<int:file_id>/',                     file_detail),
    path('files/<int:file_id>/download/',           download_file),
    path('files/<int:file_id>/permissions/',        update_file_permissions),
    path('files/<int:file_id>/rename/',             rename_file),
    path('files/<int:file_id>/delete/',             delete_file),
    
    # ── API for tasks by project ─────────────────────────────
    path('project/<int:project_id>/tasks/',         get_project_tasks),
    path('ajax/tasks/',                             get_tasks),
    
    # ── Team ──────────────────────────────────────────────────
    path('team/',                                           team),
    path('team/member/<int:member_id>/remove/',             team_remove_member),
    path('team/member/<int:member_id>/update/',             team_update_projects),
    path('team/member/<int:member_id>/projects/',           team_member_projects),
    path('team/check-user/',                                team_check_user),
]
