from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.views.decorators.http import require_POST
from .models import Task, TaskCategory, Comment
from projects.models import Project, Notification, ActivityLog
import os


def _get_project_role(project, user):
    from projects.models import ProjectMember
    if project.owner == user:
        return 'owner'
    membership = ProjectMember.objects.filter(project=project, user=user).first()
    return membership.role if membership else None


def _can_modify_task(role):
    return role in ('owner', 'admin', 'member')


def _display_name(user):
    profile = getattr(user, 'profile', None)
    return profile.display_name if profile and profile.display_name else user.username


def _get_file_type(filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp'):
        return 'image'
    elif ext in ('.mp4', '.mov', '.avi', '.mkv', '.webm'):
        return 'video'
    elif ext in ('.mp3', '.wav', '.ogg', '.flac', '.aac'):
        return 'audio'
    elif ext in ('.zip', '.rar', '.7z', '.tar', '.gz'):
        return 'archive'
    else:
        return 'document'


def _save_attachments(files, task, user):
    """บันทึกไฟล์แนบ และสร้าง FileAttachment ใน file manager ด้วย"""
    from projects.models import FileAttachment
    for f in files:
        if not f:
            continue
        file_type = _get_file_type(f.name)
        # สร้าง FileAttachment เดียว — ใช้ทั้งใน task และ file manager
        FileAttachment.objects.create(
            project=task.project,
            task=task,
            uploaded_by=user,
            file=f,
            filename=f.name,
            file_type=file_type,
            file_size=f.size,
        )


@login_required
def task_list(request, project_id):
    from projects.models import ProjectMember
    from django.utils import timezone
    from datetime import timedelta
    project = get_object_or_404(Project, id=project_id)

    # ตรวจสิทธิ์: owner หรือ member ที่ถูก invite เท่านั้น
    is_owner = (project.owner == request.user)
    if not is_owner:
        membership = ProjectMember.objects.filter(project=project, user=request.user).first()
        if not membership:
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden("คุณไม่มีสิทธิ์เข้าถึงโปรเจคนี้")
        member_role = membership.role  # 'viewer' / 'member' / 'admin'
    else:
        member_role = 'owner'

    # category: owner ใช้ของตัวเอง, member ใช้ของ project owner
    if is_owner:
        task_categories = TaskCategory.objects.filter(owner=request.user)
    else:
        task_categories = TaskCategory.objects.filter(owner=project.owner)

    # ใช้สำหรับ assign/transfer งานในหน้า edit
    member_user_ids = list(project.members.values_list('user_id', flat=True))
    assignable_user_ids = [project.owner_id, *member_user_ids]
    seen_user_ids = set()
    deduped_ids = []
    for uid in assignable_user_ids:
        if uid in seen_user_ids:
            continue
        seen_user_ids.add(uid)
        deduped_ids.append(uid)
    assignable_users = User.objects.filter(id__in=deduped_ids).order_by('username')

    selected_cat      = request.GET.get('category', '')
    selected_status   = request.GET.get('status', '')
    selected_priority = request.GET.get('priority', '')   # ← priority filter ใหม่

    qs_base = Task.objects.filter(project=project).select_related('assigned_to', 'assigned_to__profile', 'category')

    # ── Category filter ──────────────────────────────────────
    if selected_cat:
        qs_base = qs_base.filter(category_id=selected_cat)

    # ── Priority filter ──────────────────────────────────────
    if selected_priority in ('high', 'medium', 'low'):
        qs_base = qs_base.filter(priority=selected_priority)

    # ── Status filter ────────────────────────────────────────
    # กันกรณี status ใน DB ถูกตั้งค่าไม่ถูกต้อง (เช่น "comments") ทำให้หายจากบอร์ด
    invalid_status_qs = qs_base.exclude(status__in=('todo', 'doing', 'done'))

    if selected_status in ('todo', 'doing', 'done'):
        todo_q  = qs_base.filter(status='todo')
        doing_q = qs_base.filter(status='doing')
        done_q  = qs_base.filter(status='done')

        # ให้ task ที่ status ผิด “ไม่หาย” ไปไหน โดยโยนไปรวมกับคอลัมน์ที่ผู้ใช้กำลังกรองอยู่
        if selected_status == 'todo':
            todo  = todo_q | invalid_status_qs
            doing = Task.objects.none()
            done  = Task.objects.none()
        elif selected_status == 'doing':
            todo  = Task.objects.none()
            doing = doing_q | invalid_status_qs
            done  = Task.objects.none()
        else:  # 'done'
            todo  = Task.objects.none()
            doing = Task.objects.none()
            done  = done_q | invalid_status_qs
    else:
        # ไม่ได้กรอง status: แสดง tasks ที่ status ผิดไว้ที่คอลัมน์ To Do
        todo  = qs_base.filter(status='todo') | invalid_status_qs
        doing = qs_base.filter(status='doing')
        done  = qs_base.filter(status='done')

    # ── Due date badges (overdue / soon) ─────────────────────
    # overdue: ใช้ Task.is_overdue (due_date < today และ status != done)
    # due soon: due_date อยู่ในช่วงวันนี้ถึงอีก 2 วัน (และยังไม่ completed)
    today = timezone.localdate()
    soon_until = today + timedelta(days=2)
    for t in todo:
        t.is_due_soon = bool(t.due_date) and t.status != 'done' and (t.due_date >= today) and (t.due_date <= soon_until)
    for t in doing:
        t.is_due_soon = bool(t.due_date) and t.status != 'done' and (t.due_date >= today) and (t.due_date <= soon_until)
    for t in done:
        t.is_due_soon = False

    return render(request, 'tasks/task_list.html', {
        'project':           project,
        'todo':              todo,
        'doing':             doing,
        'done':              done,
        'task_categories':   task_categories,
        'selected_cat':      selected_cat,
        'selected_status':   selected_status,
        'selected_priority': selected_priority,
        'is_owner':          is_owner,
        'member_role':       member_role,   # 'owner' / 'admin' / 'member' / 'viewer'
        'assignable_users':  assignable_users,
        'current_user_display_name': _display_name(request.user),
    })


@login_required
def create_task(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    role = _get_project_role(project, request.user)
    if role not in ('owner', 'admin'):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    if request.method == 'POST':
        title       = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        due_date    = request.POST.get('due_date', '').strip()
        status      = request.POST.get('status', 'todo')
        priority    = request.POST.get('priority', 'medium')
        category_id = request.POST.get('category_id') or None

        if category_id:
            if not TaskCategory.objects.filter(id=category_id, owner=project.owner).exists():
                return JsonResponse({'error': 'Invalid category for this project'}, status=400)

        # ── Validate: due_date required ──────────────────────
        if not due_date:
            # redirect กลับพร้อม error (ใช้ session message หรือ query param)
            return redirect(f'/project/{project.id}/?error=due_date_required')

        if title:
            assigned_to_id = request.POST.get('assigned_to_id')
            assigned_to = request.user
            if assigned_to_id:
                try:
                    assigned_to_id_int = int(assigned_to_id)
                except (TypeError, ValueError):
                    return JsonResponse({'error': 'Invalid assignee'}, status=400)
                # อนุญาตให้ assign ได้เฉพาะคนในโปรเจค (owner + project members)
                from projects.models import ProjectMember
                is_member = (
                    assigned_to_id_int == project.owner_id or
                    ProjectMember.objects.filter(project=project, user_id=assigned_to_id_int).exists()
                )
                if not is_member:
                    return JsonResponse({'error': 'Assignee must be in this project'}, status=400)
                assigned_to = User.objects.get(id=assigned_to_id_int)
            task = Task.objects.create(
                title=title,
                description=description,
                due_date=due_date,
                project=project,
                status=status,
                priority=priority,
                category_id=category_id,
                assigned_to=assigned_to,
            )
            # ── Handle file attachments ──────────────────────
            _save_attachments(request.FILES.getlist('attachments'), task, request.user)
            ActivityLog.objects.create(
                user=request.user,
                action='create_task',
                target=title,
                project=project,
            )
    return redirect(f'/project/{project.id}/')


@login_required
@require_POST
def update_status(request, task_id, status):
    task       = get_object_or_404(Task, id=task_id)
    role = _get_project_role(task.project, request.user)
    if not _can_modify_task(role):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    if status not in ('todo', 'doing', 'done'):
        return JsonResponse({'error': 'Invalid status'}, status=400)
    old_status = task.status
    task.status = status
    task.save()
    ActivityLog.objects.create(
        user=request.user,
        action='change_status',
        target=f'"{task.title}" {old_status} → {status}',
        project=task.project,
    )
    labels = {'todo': 'To Do', 'doing': 'Doing', 'done': 'Done'}
    if old_status != status:
        Notification.objects.create(
            user=task.assigned_to,
            message=f'"{task.title}" moved from {labels.get(old_status, old_status)} → {labels.get(status, status)} in {task.project.name}',
            notif_type='task_moved',
        )
    return JsonResponse({'status': 'ok'})


@login_required
def task_detail(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    role = _get_project_role(task.project, request.user)
    if not role:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    is_owner = (role == 'owner')

    from projects.models import FileAttachment
    attachments = FileAttachment.objects.filter(task=task, is_deleted=False).select_related('uploaded_by')
    attachments_data = [
        {
            'id':          a.id,
            'filename':    a.filename,
            'file_url':    a.file.url,
            'file_type':   a.file_type,
            'file_size':   a.get_file_size_display(),
            'icon':        a.file_type,
            'uploaded_by': _display_name(a.uploaded_by),
            'can_delete':  (a.uploaded_by_id == request.user.id) or is_owner,
        }
        for a in attachments
    ]

    return JsonResponse({
        'id':           task.id,
        'title':        task.title,
        'description':  task.description,
        'status':       task.status,
        'priority':     task.priority,
        'category':     task.category.name if task.category else None,
        'category_id':  task.category.id   if task.category else '',
        'due_date':     task.due_date.strftime('%b %d, %Y') if task.due_date else None,
        'due_date_raw': task.due_date.strftime('%Y-%m-%d')  if task.due_date else '',
        'assigned_to':  _display_name(task.assigned_to),
        'project':      task.project.name,
        'created_at':   task.created_at.strftime('%b %d, %Y'),
        'is_owner':     is_owner,
        'role':         role,
        'assigned_to_id': task.assigned_to_id,
        'can_edit':       _can_modify_task(role),
        'can_delete':     is_owner,
        'attachments':    attachments_data,
    })


@login_required
def edit_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    role = _get_project_role(task.project, request.user)
    if not _can_modify_task(role):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    if request.method == 'POST':
        due_date = request.POST.get('due_date', '').strip()

        # ── Validate: due_date required ──────────────────────
        if not due_date:
            return redirect(f'/project/{task.project.id}/?error=due_date_required')

        old_assigned_to_id = task.assigned_to_id
        old_status       = task.status
        task.title       = request.POST.get('title', task.title).strip()
        task.description = request.POST.get('description', '').strip()
        new_status = request.POST.get('status', '').strip()
        task.status = new_status if new_status in ('todo', 'doing', 'done') else task.status
        task.priority    = request.POST.get('priority', task.priority)
        task.category_id = request.POST.get('category_id') or None
        if task.category_id:
            if not TaskCategory.objects.filter(id=task.category_id, owner=task.project.owner).exists():
                return JsonResponse({'error': 'Invalid category for this project'}, status=400)
        assigned_to_id = request.POST.get('assigned_to_id')
        if assigned_to_id:
            try:
                assigned_to_id_int = int(assigned_to_id)
            except (TypeError, ValueError):
                return JsonResponse({'error': 'Invalid assignee'}, status=400)
            member_user_ids = set(task.project.members.values_list('user_id', flat=True))
            member_user_ids.add(task.project.owner_id)
            if assigned_to_id_int not in member_user_ids:
                return JsonResponse({'error': 'Assignee must be in this project'}, status=400)
            task.assigned_to_id = assigned_to_id_int
        task.due_date    = due_date
        task.save()

        # ── Handle new file attachments ──────────────────────
        _save_attachments(request.FILES.getlist('attachments'), task, request.user)

        # Log activities
        if old_status != task.status:
            ActivityLog.objects.create(
                user=request.user,
                action='change_status',
                target=f'"{task.title}" {old_status} → {task.status}',
                project=task.project,
            )
        if old_assigned_to_id != task.assigned_to_id:
            ActivityLog.objects.create(
                user=request.user,
                action='assign_user',
                target=f'"{task.title}" ให้ {_display_name(task.assigned_to)}',
                project=task.project,
            )
        else:
            ActivityLog.objects.create(
                user=request.user,
                action='update_task',
                target=task.title,
                project=task.project,
            )

        labels = {'todo': 'To Do', 'doing': 'Doing', 'done': 'Done'}
        if old_status != task.status:
            Notification.objects.create(
                user=task.assigned_to,
                message=f'"{task.title}" moved from {labels.get(old_status, old_status)} → {labels.get(task.status, task.status)} in {task.project.name}',
                notif_type='task_moved',
            )
    # Redirect กลับไปพร้อม filter เดิม (ส่งตรงๆ ไม่ match กับค่า task)
    params = []
    cat = request.POST.get('_selected_cat', '').strip()
    pri = request.POST.get('_selected_priority', '').strip()
    sts = request.POST.get('_selected_status', '').strip()

    if cat and cat.isdigit():
        params.append(f'category={cat}')
    if pri in ('high', 'medium', 'low'):
        params.append(f'priority={pri}')
    if sts in ('todo', 'doing', 'done'):
        params.append(f'status={sts}')

    qs = ('?' + '&'.join(params)) if params else ''
    return redirect(f'/project/{task.project.id}/{qs}')


@login_required
@require_POST
def delete_task(request, task_id):
    task       = get_object_or_404(Task, id=task_id)
    role = _get_project_role(task.project, request.user)
    if role != 'owner':
        return JsonResponse({'error': 'Permission denied'}, status=403)
    project_id = task.project.id
    task_title = task.title
    ActivityLog.objects.create(
        user=request.user,
        action='delete_task',
        target=task_title,
        project=task.project,
    )
    task.delete()
    return JsonResponse({'status': 'ok', 'project_id': project_id})


# ── Task Category API ─────────────────────────────────
@login_required
def create_task_category(request):
    if request.method == 'POST':
        project_id = request.POST.get('project_id')
        if project_id:
            project = get_object_or_404(Project, id=project_id)
            if project.owner != request.user:
                return JsonResponse({'error': 'Only project owner can manage categories'}, status=403)
        name = request.POST.get('name', '').strip()
        if name:
            cat, created = TaskCategory.objects.get_or_create(name=name, owner=request.user)
            return JsonResponse({'id': cat.id, 'name': cat.name, 'created': created})
        return JsonResponse({'error': 'Name is required'}, status=400)
    return JsonResponse({'error': 'POST only'}, status=405)


@login_required
def list_task_categories(request):
    # ถ้าส่ง project_id มาด้วย ให้คืน category ของ project owner แทน
    project_id = request.GET.get('project_id')
    if project_id:
        try:
            from projects.models import ProjectMember
            project = Project.objects.get(id=project_id)
            is_owner = (project.owner == request.user)
            is_member = ProjectMember.objects.filter(project=project, user=request.user).exists()
            if is_owner or is_member:
                cats = TaskCategory.objects.filter(owner=project.owner).values('id', 'name')
                return JsonResponse({'categories': list(cats)})
        except Project.DoesNotExist:
            pass
    cats = TaskCategory.objects.filter(owner=request.user).values('id', 'name')
    return JsonResponse({'categories': list(cats)})


@login_required
def edit_task_category(request, cat_id):
    cat = get_object_or_404(TaskCategory, id=cat_id, owner=request.user)
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if not name:
            return JsonResponse({'error': 'Name is required'}, status=400)
        if TaskCategory.objects.filter(name=name, owner=request.user).exclude(id=cat_id).exists():
            return JsonResponse({'error': f'Category "{name}" already exists'}, status=400)
        cat.name = name
        cat.save()
        return JsonResponse({'id': cat.id, 'name': cat.name})
    return JsonResponse({'error': 'POST only'}, status=405)


@login_required
def delete_task_category(request, cat_id):
    cat = get_object_or_404(TaskCategory, id=cat_id, owner=request.user)
    if request.method == 'POST':
        cat.delete()
        return JsonResponse({'status': 'ok'})
    return JsonResponse({'error': 'POST only'}, status=405)


# ── Comments ──────────────────────────────────────────
@login_required
def get_comments(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    role = _get_project_role(task.project, request.user)
    if not role:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    is_project_owner = (task.project.owner_id == request.user.id)
    comments = task.comments.select_related('user').order_by('created_at')
    return JsonResponse({
        'comments': [
            {
                'id':         c.id,
                'user_id':    c.user_id,
                'username':   _display_name(c.user),
                'avatar_url': c.user.profile.get_avatar_url(),
                'message':    c.message,
                'created_at': c.created_at.strftime('%d %b %Y, %H:%M').lstrip('0'),
                'can_edit':   (c.user_id == request.user.id),
                'can_delete': (c.user_id == request.user.id) or is_project_owner,
            }
            for c in comments
        ]
    })


@login_required
@require_POST
def add_comment(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    role = _get_project_role(task.project, request.user)
    if not role:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    message = request.POST.get('message', '').strip()
    if not message:
        return JsonResponse({'error': 'Message is required'}, status=400)
    Comment.objects.create(task=task, user=request.user, message=message)
    return JsonResponse({'status': 'ok', 'task_id': task.id, 'project_id': task.project_id})


@login_required
@require_POST
def edit_comment(request, comment_id):
    comment = get_object_or_404(Comment.objects.select_related('task__project'), id=comment_id)
    role = _get_project_role(comment.task.project, request.user)
    if not role:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    if comment.user_id != request.user.id:
        return JsonResponse({'error': 'You can only edit your own comment'}, status=403)

    message = request.POST.get('message', '').strip()
    if not message:
        return JsonResponse({'error': 'Message is required'}, status=400)

    comment.message = message
    comment.save(update_fields=['message'])
    return JsonResponse({'status': 'ok', 'comment_id': comment.id})


@login_required
@require_POST
def delete_comment(request, comment_id):
    comment = get_object_or_404(Comment.objects.select_related('task__project'), id=comment_id)
    role = _get_project_role(comment.task.project, request.user)
    if not role:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    is_project_owner = (comment.task.project.owner_id == request.user.id)
    is_own_comment = (comment.user_id == request.user.id)
    if not (is_own_comment or is_project_owner):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    deleted_id = comment.id
    comment.delete()
    return JsonResponse({'status': 'ok', 'comment_id': deleted_id})


# ── Activity Log ────────────────────────────────────────
@login_required
def activity_log(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    
    # ตรวจสิทธิ์: owner หรือ member ที่ถูก invite เท่านั้น
    is_owner = (project.owner == request.user)
    if not is_owner:
        membership = ProjectMember.objects.filter(project=project, user=request.user).first()
        if not membership:
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden("คุณไม่มีสิทธิ์เข้าถึงโปรเจคนี้")
    
    activities = project.activities.select_related('user').order_by('-timestamp')[:50]
    
    return render(request, 'tasks/activity_log.html', {
        'project': project,
        'activities': activities,
    })


# ── Task Attachments ────────────────────────────────────
@login_required
@require_POST
def delete_attachment(request, attachment_id):
    from projects.models import FileAttachment
    attachment = get_object_or_404(
        FileAttachment.objects.select_related('project', 'uploaded_by'),
        id=attachment_id
    )
    role = _get_project_role(attachment.project, request.user)
    if not role:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    is_owner = (attachment.project.owner_id == request.user.id)
    is_uploader = (attachment.uploaded_by_id == request.user.id)
    if not (is_owner or is_uploader):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    try:
        if attachment.file and os.path.isfile(attachment.file.path):
            os.remove(attachment.file.path)
    except Exception:
        pass

    deleted_id = attachment.id
    attachment.delete()
    return JsonResponse({'status': 'ok', 'attachment_id': deleted_id})