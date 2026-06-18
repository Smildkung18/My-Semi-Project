from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Count, Q
from django.core.mail import send_mail
from django.conf import settings
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.core.cache import cache

from .models import Project, Notification, Category, PasswordResetOTP, ProjectMember, ActivityLog, FileAttachment
from tasks.models import Task


def _run_due_check(user):
    """
    Create notifications for tasks/projects due within 3 days.
    Silently fails on errors to avoid blocking login.
    """
    try:
        from django.utils import timezone
        from datetime import timedelta
        from tasks.models import Task

        today    = timezone.now().date()
        in_3days = today + timedelta(days=3)

        tasks = Task.objects.filter(assigned_to=user, due_date__lte=in_3days).exclude(status='done')
        for task in tasks:
            already = Notification.objects.filter(
                user=user, notif_type='due_soon',
                message__contains=task.title, created_at__date=today,
            ).exists()
            if already:
                continue
            days_left = (task.due_date - today).days
            if days_left < 0:
                time_str = f'overdue by {abs(days_left)} day{"s" if abs(days_left) != 1 else ""}!'
            elif days_left == 0:
                time_str = 'due today!'
            elif days_left == 1:
                time_str = 'due tomorrow'
            else:
                time_str = f'due in {days_left} days'
            Notification.objects.create(
                user=user,
                message=f'⏰ "{task.title}" is {time_str} ({task.project.name})',
                notif_type='due_soon',
            )

        projects = Project.objects.filter(owner=user, deadline__lte=in_3days).exclude(status='completed')
        for project in projects:
            already = Notification.objects.filter(
                user=user, notif_type='due_soon',
                message__contains=project.name, created_at__date=today,
            ).exists()
            if already:
                continue
            days_left = (project.deadline - today).days
            if days_left < 0:
                time_str = f'overdue by {abs(days_left)} day{"s" if abs(days_left) != 1 else ""}!'
            elif days_left == 0:
                time_str = 'deadline is today!'
            elif days_left == 1:
                time_str = 'deadline is tomorrow'
            else:
                time_str = f'deadline in {days_left} days'
            Notification.objects.create(
                user=user,
                message=f'📁 Project "{project.name}" — {time_str}',
                notif_type='due_soon',
            )
    except Exception:
        pass


def user_login(request):
    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            _run_due_check(user)
            return redirect('/')
        else:
            error = 'Username หรือ Password ไม่ถูกต้อง'
    return render(request, 'projects/login.html', {'error': error})


def user_logout(request):
    logout(request)
    return redirect('/login/')


def user_register(request):
    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email    = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        confirm  = request.POST.get('confirm', '')

        if not username:
            error = 'กรุณากรอก Username'
        elif not email:
            error = 'กรุณากรอก Email'
        else:
            try:
                validate_email(email)
            except ValidationError:
                error = 'รูปแบบ Email ไม่ถูกต้อง'

        if not error:
            if password != confirm:
                error = 'Password ไม่ตรงกัน'
            elif len(password) < 6:
                error = 'Password ต้องมีอย่างน้อย 6 ตัวอักษร'
            elif User.objects.filter(username=username).exists():
                error = 'Username นี้มีคนใช้แล้ว'
            elif User.objects.filter(email=email).exists():
                error = 'Email นี้มีบัญชีผูกอยู่แล้ว'

        if not error:
            user = User.objects.create_user(username=username, email=email, password=password)
            login(request, user)
            _run_due_check(user)
            return redirect('/')

    return render(request, 'projects/register.html', {'error': error})


def password_reset_request(request):
    """
    Step 1: Request password reset by username.
    Sends OTP to user's email if it exists.
    """
    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            error = 'ไม่พบ Username นี้ในระบบ'
        else:
            if not user.email:
                error = 'บัญชีนี้ยังไม่มี Email — กรุณาติดต่อผู้ดูแลระบบ'
            else:
                # Rate limiting: 5 OTP requests per email/IP per 10 minutes
                email_key = f'otp_req_{user.email}'
                ip_key = f'otp_req_{request.META.get("REMOTE_ADDR", "unknown")}'
                
                email_count = cache.get(email_key)
                ip_count = cache.get(ip_key)
                
                if email_count is None:
                    email_count = 1
                    cache.set(email_key, email_count, 600)
                else:
                    email_count += 1
                    cache.set(email_key, email_count, 600)
                    
                if ip_count is None:
                    ip_count = 1
                    cache.set(ip_key, ip_count, 600)
                else:
                    ip_count += 1
                    cache.set(ip_key, ip_count, 600)
                
                if email_count >= 5 or ip_count >= 5:
                    error = 'ขอ OTP ได้มากเกินไป กรุณารอ 10 นาที'
                else:
                    otp = PasswordResetOTP.generate_for_user(user)
                    _send_otp_email(user, otp.code)
                    request.session['reset_username'] = user.username
                    return redirect('/password-reset/verify/')

    return render(request, 'projects/password_reset_request.html', {'error': error})


def _send_otp_email(user, code):
    masked_email = _mask_email(user.email)
    send_mail(
        subject='[KanFlow] รหัส OTP สำหรับ Reset Password',
        message=(
            f'สวัสดีคุณ {user.username},\n\n'
            f'รหัส OTP ของคุณคือ: {code}\n\n'
            f'รหัสนี้จะหมดอายุใน 10 นาที\n'
            f'ถ้าคุณไม่ได้ขอ reset password กรุณาเพิกเฉยต่ออีเมลนี้\n\n'
            f'— KanFlow Team'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )


def _mask_email(email):
    """john.doe@gmail.com → j***.d**@g*****.com"""
    try:
        local, domain = email.split('@')
        masked_local  = local[0] + '***' + (('.' + local.split('.')[1][0] + '**') if '.' in local else '')
        domain_parts  = domain.split('.')
        masked_domain = domain_parts[0][0] + '*' * (len(domain_parts[0]) - 1)
        return f"{masked_local}@{masked_domain}.{'.'.join(domain_parts[1:])}"
    except Exception:
        return email[:2] + '***@***'


def password_reset_verify(request):
    """
    Step 2: Verify OTP and set new password.
    Requires session['reset_username'] from step 1.
    """
    username = request.session.get('reset_username')
    if not username:
        return redirect('/password-reset/')

    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        return redirect('/password-reset/')

    masked_email = _mask_email(user.email)
    error   = None
    success = None

    if request.method == 'POST':
        action = request.POST.get('action', 'verify')

        if action == 'resend':
            # Rate limiting: 5 OTP requests per email/IP per 10 minutes
            email_key = f'otp_req_{user.email}'
            ip_key = f'otp_req_{request.META.get("REMOTE_ADDR", "unknown")}'
            
            email_count = cache.get(email_key)
            ip_count = cache.get(ip_key)
            
            if email_count is None:
                email_count = 1
                cache.set(email_key, email_count, 600)
            else:
                email_count += 1
                cache.set(email_key, email_count, 600)
                
            if ip_count is None:
                ip_count = 1
                cache.set(ip_key, ip_count, 600)
            else:
                ip_count += 1
                cache.set(ip_key, ip_count, 600)
            
            if email_count >= 5 or ip_count >= 5:
                error = 'ขอ OTP ได้มากเกินไป กรุณารอ 10 นาที'
            else:
                otp = PasswordResetOTP.generate_for_user(user)
                _send_otp_email(user, otp.code)
                success = f'ส่ง OTP ใหม่ไปยัง {masked_email} แล้วครับ'

        else:
            code       = request.POST.get('otp', '').strip()
            new_pw     = request.POST.get('new_password', '')
            confirm_pw = request.POST.get('confirm_password', '')
            
            # Rate limiting: 5 OTP attempts per email/IP per 10 minutes
            email_key = f'otp_verify_{user.email}'
            ip_key = f'otp_verify_{request.META.get("REMOTE_ADDR", "unknown")}'
            
            email_count = cache.get(email_key)
            ip_count = cache.get(ip_key)
            
            if email_count is None:
                email_count = 1
                cache.set(email_key, email_count, 600)
            else:
                email_count += 1
                cache.set(email_key, email_count, 600)
                
            if ip_count is None:
                ip_count = 1
                cache.set(ip_key, ip_count, 600)
            else:
                ip_count += 1
                cache.set(ip_key, ip_count, 600)
            
            if email_count >= 5 or ip_count >= 5:
                error = 'พยายามยืนยัน OTP ได้มากเกินไป กรุณารอ 10 นาที'
            else:
                try:
                    otp_obj = PasswordResetOTP.objects.filter(
                        user=user, code=code, is_used=False
                    ).latest('created_at')
                except PasswordResetOTP.DoesNotExist:
                    error = 'รหัส OTP ไม่ถูกต้อง'
                else:
                    if not otp_obj.is_valid():
                        error = 'รหัส OTP หมดอายุแล้ว กรุณากด "ส่ง OTP ใหม่"'
                    elif new_pw != confirm_pw:
                        error = 'Password ไม่ตรงกัน'
                    elif len(new_pw) < 6:
                        error = 'Password ต้องมีอย่างน้อย 6 ตัวอักษร'
                    else:
                        otp_obj.is_used = True
                        otp_obj.save()
                        user.set_password(new_pw)
                        user.save()
                        del request.session['reset_username']
                        cache.delete(email_key)
                        cache.delete(ip_key)
                        return redirect('/password-reset/done/')

    return render(request, 'projects/password_reset_verify.html', {
        'masked_email': masked_email,
        'username':     username,
        'error':        error,
        'success':      success,
    })


def password_reset_done(request):
    """Password reset success page"""
    return render(request, 'projects/password_reset_done.html')


def google_login_redirect(request):
    """Redirect to django-allauth OAuth flow"""
    from allauth.socialaccount.providers.google.views import oauth2_login
    return oauth2_login(request)

@login_required
def project_list(request):
    from django.utils import timezone
    from tasks.models import Task

    today = timezone.now().date()

    # Own projects + shared projects
    own_projects    = Project.objects.filter(owner=request.user)
    shared_ids      = ProjectMember.objects.filter(user=request.user).values_list('project_id', flat=True)
    shared_projects = Project.objects.filter(id__in=shared_ids).exclude(owner=request.user)

    # Combine and annotate is_shared for template
    from itertools import chain
    all_projects = list(own_projects.select_related('category')) + list(shared_projects.select_related('category'))
    own_ids = set(own_projects.values_list('id', flat=True))

    projects = all_projects

    for p in projects:
        p.days_left    = (p.deadline - today).days if p.deadline else None
        p.todo_count   = Task.objects.filter(project=p, status='todo').count()
        p.doing_count  = Task.objects.filter(project=p, status='doing').count()
        p.done_count   = Task.objects.filter(project=p, status='done').count()
        p.total_tasks  = p.todo_count + p.doing_count + p.done_count
        p.progress     = round(p.done_count / p.total_tasks * 100) if p.total_tasks else 0
        p.overdue_count = Task.objects.filter(
            project=p, due_date__lt=today
        ).exclude(status='done').count()
        p.is_shared    = p.id not in own_ids

    categories = Category.objects.filter(owner=request.user)

    try:
        from tasks.models import TaskCategory
        task_categories = TaskCategory.objects.filter(owner=request.user)
    except Exception:
        task_categories = []

    active_count    = sum(1 for p in projects if p.status == 'active')
    completed_count = sum(1 for p in projects if p.status == 'completed')
    member_count    = ProjectMember.objects.filter(
        project__in=own_projects
    ).values('user').distinct().count()

    selected_cat = request.GET.get('category', '')
    if selected_cat:
        projects = [p for p in projects if p.category_id and str(p.category_id) == selected_cat]

    selected_task_cat = request.GET.get('task_category', '')
    if selected_task_cat:
        projects = [
            p for p in projects
            if Task.objects.filter(project=p, category_id=selected_task_cat).exists()
        ]

    return render(request, 'projects/project_list.html', {
        'projects':          projects,
        'categories':        categories,
        'task_categories':   task_categories,
        'active_count':      active_count,
        'completed_count':   completed_count,
        'member_count':      member_count,
        'selected_cat':      selected_cat,
        'selected_task_cat': selected_task_cat,
    })


@login_required
def create_project(request):
    if request.method == 'POST':
        name        = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        deadline    = request.POST.get('deadline', '').strip()
        status      = request.POST.get('status', 'active')
        category_id = request.POST.get('category_id') or None
        if not deadline:
            return redirect('/?error=deadline_required')
        if name:
            Project.objects.create(
                name=name, description=description, deadline=deadline,
                status=status, category_id=category_id, owner=request.user,
            )
    return redirect('/')


@login_required
def create_category(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if name:
            cat, created = Category.objects.get_or_create(name=name, owner=request.user)
            return JsonResponse({'id': cat.id, 'name': cat.name, 'created': created})
        return JsonResponse({'error': 'Name is required'}, status=400)
    return JsonResponse({'error': 'POST only'}, status=405)


@login_required
def edit_category(request, cat_id):
    cat = get_object_or_404(Category, id=cat_id, owner=request.user)
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if not name:
            return JsonResponse({'error': 'Name is required'}, status=400)
        if Category.objects.filter(name=name, owner=request.user).exclude(id=cat_id).exists():
            return JsonResponse({'error': f'Category "{name}" already exists'}, status=400)
        cat.name = name
        cat.save()
        return JsonResponse({'id': cat.id, 'name': cat.name})
    return JsonResponse({'error': 'POST only'}, status=405)


@login_required
def delete_category(request, cat_id):
    cat = get_object_or_404(Category, id=cat_id, owner=request.user)
    if request.method == 'POST':
        cat.delete()
        return JsonResponse({'status': 'ok'})
    return JsonResponse({'error': 'POST only'}, status=405)


@login_required
def list_categories(request):
    cats = Category.objects.filter(owner=request.user).values('id', 'name')
    return JsonResponse({'categories': list(cats)})


@login_required
def my_tasks(request):
    from tasks.models import Task
    from django.utils import timezone
    tasks = Task.objects.filter(assigned_to=request.user).select_related('project').order_by('due_date')
    today = timezone.localdate()
    return render(request, 'projects/my_tasks.html', {
        'tasks':         tasks,
        'doing_count':   tasks.filter(status='doing').count(),
        'done_count':    tasks.filter(status='done').count(),
        'overdue_count': tasks.exclude(status='done').filter(due_date__lt=today).count(),
    })


@login_required
def profile_view(request):
    # Stats
    tasks_created = Task.objects.filter(assigned_to=request.user).count()
    tasks_completed = Task.objects.filter(assigned_to=request.user, status='done').count()
    projects_joined = ProjectMember.objects.filter(user=request.user).count() + Project.objects.filter(owner=request.user).count()
    
    # Recent activities
    recent_activities = ActivityLog.objects.filter(user=request.user).select_related('project').order_by('-timestamp')[:10]
    
    # My projects
    my_projects = Project.objects.filter(
        Q(owner=request.user) | Q(members__user=request.user)
    ).distinct().order_by('name')[:10]
    
    # Mask email for display
    request.user.email_masked = _mask_email(request.user.email) if getattr(request.user, 'email', '') else None
    
    return render(request, 'projects/profile.html', {
        'target_user': request.user,
        'tasks_created': tasks_created,
        'tasks_completed': tasks_completed,
        'projects_joined': projects_joined,
        'recent_activities': recent_activities,
        'my_projects': my_projects,
        'is_owner': True,
    })


@login_required
def public_profile_view(request, user_id_or_username=None, username=None, user_id=None):
    # Handle all parameter naming conventions
    identifier = user_id or username or user_id_or_username
    
    if not identifier:
        from django.http import HttpResponseBadRequest
        return HttpResponseBadRequest("Missing user identifier")
    
    # Check if it's a user_id (numeric) or username (string)
    try:
        # Try to parse as integer (user_id)
        user_id = int(identifier)
        target_user = get_object_or_404(User, id=user_id)
    except (ValueError, TypeError):
        # Treat as username
        target_user = get_object_or_404(User, username=identifier)
    
    # Security check: only allow viewing if they share at least one project
    shared_projects = Project.objects.filter(
        Q(members__user__in=[target_user, request.user]) |
        Q(owner=target_user, members__user=request.user) |
        Q(owner=request.user, members__user=target_user)
    ).distinct()
    
    if not shared_projects.exists() and request.user != target_user:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("คุณไม่มีสิทธิ์ดูโปรไฟล์นี้")
    
    # Stats
    tasks_created = Task.objects.filter(assigned_to=target_user).count()
    tasks_completed = Task.objects.filter(assigned_to=target_user, status='done').count()
    projects_joined = ProjectMember.objects.filter(user=target_user).count() + Project.objects.filter(owner=target_user).count()
    
    # Recent activities (only from shared projects)
    recent_activities = ActivityLog.objects.filter(
        user=target_user,
        project__in=shared_projects
    ).select_related('project').order_by('-timestamp')[:10]
    
    # My projects (only shared projects)
    my_projects = shared_projects.order_by('name')[:10]
    
    # Mask email for display
    target_user.email_masked = _mask_email(target_user.email) if getattr(target_user, 'email', '') else None
    
    return render(request, 'projects/profile.html', {
        'target_user': target_user,
        'tasks_created': tasks_created,
        'tasks_completed': tasks_completed,
        'projects_joined': projects_joined,
        'recent_activities': recent_activities,
        'my_projects': my_projects,
        'is_owner': (request.user == target_user),
    })


# ── analytics() replaced by new Personal/Team analytics ──────
# imported at bottom of file:
#   from .analytics_views import personal_analytics, team_analytics
# analytics URL now points to personal_analytics directly.


@login_required
def team(request):
    from tasks.models import Task
    from .models import ProjectMember
    invite_error   = None
    invite_success = None
    projects = Project.objects.filter(owner=request.user)

    if request.method == 'POST':
        username    = request.POST.get('username', '').strip()
        project_ids = request.POST.getlist('project_ids')
        role        = request.POST.get('role', 'member')

        if username == request.user.username:
            invite_error = 'ไม่สามารถเพิ่มตัวเองได้'
        elif not project_ids:
            invite_error = 'กรุณาเลือกอย่างน้อย 1 โปรเจค'
        else:
            try:
                invited_user = User.objects.get(username=username)
                added = []
                for pid in project_ids:
                    try:
                        project = projects.get(id=pid)
                        pm, created = ProjectMember.objects.get_or_create(
                            project=project,
                            user=invited_user,
                            defaults={'role': role, 'invited_by': request.user},
                        )
                        if created:
                            added.append(project.name)
                        else:
                            pm.role = role
                            pm.save()
                    except Project.DoesNotExist:
                        pass
                Notification.objects.create(
                    user=invited_user,
                    message=f'\U0001f44b {request.user.username} added you to: {", ".join(added) if added else "existing projects"}',
                    notif_type='task_moved',
                )
                invite_success = f'Added {username} to team!'
            except User.DoesNotExist:
                invite_error = f'ไม่พบ Username "{username}"'

    # สมาชิกทั้งหมดจาก ProjectMember + owner
    member_ids = list(ProjectMember.objects.filter(
        project__in=projects
    ).values_list('user_id', flat=True).distinct())
    member_ids = list(set(member_ids + [request.user.id]))
    members = User.objects.filter(id__in=member_ids).select_related('profile')

    members_data = []
    for m in members:
        # ปิดบังอีเมลเพื่อความปลอดภัย (ไม่แสดงเต็มแบบเดิม)
        m.email_masked = _mask_email(m.email) if getattr(m, 'email', '') else None
        m.task_count = Task.objects.filter(assigned_to=m, project__in=projects).count()
        m.done_count = Task.objects.filter(assigned_to=m, project__in=projects, status='done').count()
        m.accessible_projects = list(ProjectMember.objects.filter(
            user=m, project__in=projects
        ).select_related('project'))
        m.is_owner = (m.id == request.user.id)
        members_data.append(m)

    total_tasks  = Task.objects.filter(project__in=projects).count()
    active_tasks = Task.objects.filter(project__in=projects).exclude(status='done').count()
    member_count = len(members_data) or 1
    avg = active_tasks / member_count
    if avg <= 2:
        capacity = 'Low'
    elif avg <= 5:
        capacity = 'Medium'
    else:
        capacity = 'High'

    return render(request, 'projects/team.html', {
        'members':        members_data,
        'projects':       projects,
        'total_tasks':    total_tasks,
        'capacity':       capacity,
        'invite_error':   invite_error,
        'invite_success': invite_success,
    })


@login_required
def team_member_projects(request, member_id):
    """GET: คืน project_ids และ role ของ member ใน projects ของ owner"""
    from .models import ProjectMember
    projects = Project.objects.filter(owner=request.user)
    memberships = ProjectMember.objects.filter(user_id=member_id, project__in=projects)
    project_ids = list(memberships.values_list('project_id', flat=True))
    role = memberships.first().role if memberships.exists() else 'member'
    return JsonResponse({'project_ids': project_ids, 'role': role})


@login_required

@login_required
def team_check_user(request):
    username = request.GET.get('username', '').strip()
    if not username:
        return JsonResponse({'exists': False})
    try:
        u = User.objects.get(username=username)
        if u == request.user:
            return JsonResponse({'exists': False, 'msg': 'ไม่สามารถเพิ่มตัวเองได้'})
        profile = getattr(u, 'profile', None)
        display_name = profile.display_name if profile and profile.display_name else u.username
        display = f"{display_name} ({u.username})"
        return JsonResponse({'exists': True, 'display': display})
    except User.DoesNotExist:
        return JsonResponse({'exists': False})

@login_required
def team_remove_member(request, member_id):
    from .models import ProjectMember
    if request.method == 'POST':
        projects = Project.objects.filter(owner=request.user)
        ProjectMember.objects.filter(user_id=member_id, project__in=projects).delete()
        return JsonResponse({'status': 'ok'})
    return JsonResponse({'error': 'POST only'}, status=405)


@login_required
def project_request_upgrade(request, project_id):
    """ขอ upgrade role ใน project ที่ถูก share มา"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    project = get_object_or_404(Project, id=project_id)

    # ต้องเป็น member ของ project นี้ (ไม่ใช่ owner)
    try:
        pm = ProjectMember.objects.get(project=project, user=request.user)
    except ProjectMember.DoesNotExist:
        return JsonResponse({'error': 'คุณไม่ได้เป็นสมาชิกของโปรเจคนี้'}, status=403)

    requested_role = request.POST.get('role', 'member')
    if requested_role not in ['member', 'admin']:
        return JsonResponse({'error': 'Role ไม่ถูกต้อง'}, status=400)

    # แจ้ง owner
    Notification.objects.create(
        user=project.owner,
        message=f'🙋 {request.user.username} ขอสิทธิ์ "{requested_role}" ในโปรเจค "{project.name}"',
        notif_type='task_moved',
    )
    return JsonResponse({'status': 'ok', 'message': f'ส่งคำขอ "{requested_role}" ไปยัง owner แล้ว'})


@login_required
def project_leave(request, project_id):
    """ออกจาก project ที่ถูก share มา"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    project = get_object_or_404(Project, id=project_id)

    # owner ออกไม่ได้
    if project.owner == request.user:
        return JsonResponse({'error': 'เจ้าของโปรเจคไม่สามารถออกได้'}, status=403)

    deleted, _ = ProjectMember.objects.filter(
        project=project, user=request.user
    ).delete()

    if deleted == 0:
        return JsonResponse({'error': 'คุณไม่ได้เป็นสมาชิกของโปรเจคนี้'}, status=403)

    Notification.objects.create(
        user=project.owner,
        message=f'👋 {request.user.username} ออกจากโปรเจค "{project.name}" แล้ว',
        notif_type='task_moved',
    )
    return JsonResponse({'status': 'ok'})


@login_required
def team_update_projects(request, member_id):
    from .models import ProjectMember
    if request.method == 'POST':
        projects    = Project.objects.filter(owner=request.user)
        project_ids = request.POST.getlist('project_ids')
        role        = request.POST.get('role', 'member')
        try:
            member = User.objects.get(id=member_id)
        except User.DoesNotExist:
            return JsonResponse({'error': 'User not found'}, status=404)
        # ลบ project ที่ไม่ได้เลือก
        ProjectMember.objects.filter(user=member, project__in=projects).exclude(
            project_id__in=project_ids
        ).delete()
        # เพิ่ม/อัปเดต project ที่เลือก
        for pid in project_ids:
            try:
                project = projects.get(id=pid)
                pm, _ = ProjectMember.objects.get_or_create(
                    project=project, user=member,
                    defaults={'role': role, 'invited_by': request.user},
                )
                pm.role = role
                pm.save()
            except Project.DoesNotExist:
                pass
        return JsonResponse({'status': 'ok'})
    return JsonResponse({'error': 'POST only'}, status=405)


@login_required
def settings_view(request):
    success = None
    error   = None
    from .models import UserProfile
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        
        # Handle profile form submission (normal POST)
        if form_type == 'profile' or form_type is None:
            display_name = request.POST.get('display_name', '').strip()
            email = request.POST.get('email', '').strip()
            bio = request.POST.get('bio', '').strip()
            gender = request.POST.get('gender', '')
            name = request.POST.get('name', '').strip()
            surname = request.POST.get('surname', '').strip()
            
            # Debug: Print received data
            print(f"DEBUG - Profile update data:")
            print(f"  name: '{name}'")
            print(f"  surname: '{surname}'")
            print(f"  display_name: '{display_name}'")
            print(f"  email: '{email}'")
            print(f"  bio: '{bio}'")
            print(f"  gender: '{gender}'")
            print(f"  form_type: '{form_type}'")
            
            # For gender-only changes (no form_type), just update gender
            if form_type is None and gender:
                profile.gender = gender
                profile.save()
                messages.success(request, 'Gender updated successfully')
                return redirect('/settings/')
            
            # Validate display name
            if not display_name:
                messages.error(request, 'กรุณาระบุชื่อที่ต้องการแสดง')
            elif UserProfile.objects.filter(display_name__iexact=display_name).exclude(user=request.user).exists():
                messages.error(request, 'ชื่อนี้ถูกใช้งานแล้ว กรุณาใช้ชื่ออื่น')
            else:
                # Validate email if provided
                if email and User.objects.filter(email=email).exclude(pk=request.user.pk).exists():
                    messages.error(request, 'Email นี้ถูกใช้งานโดยบัญชีอื่นแล้ว')
                else:
                    # Update profile fields
                    profile.display_name = display_name
                    profile.bio = bio
                    profile.gender = gender
                    profile.name = name
                    profile.surname = surname

                    # Handle avatar upload
                    if 'avatar' in request.FILES:
                        avatar_file = request.FILES['avatar']
                        # Validate file size (2MB max)
                        if avatar_file.size > 2 * 1024 * 1024:
                            messages.error(request, 'ขนาดรูปภาพต้องไม่เกิน 2MB')
                            return redirect('/settings/')
                        profile.avatar = avatar_file

                    # Save profile BEFORE user.save() to prevent signal override
                    profile.save()

                    # Update email on User model
                    request.user.email = email
                    # Use update() to avoid triggering post_save signal that re-saves profile
                    User.objects.filter(pk=request.user.pk).update(email=email)
                    
                    messages.success(request, 'Profile updated successfully')
            
            return redirect('/settings/')
        
        elif form_type == 'password':
            old_pw = request.POST.get('old_password')
            new_pw = request.POST.get('new_password')
            confirm = request.POST.get('confirm_password')
            
            if not request.user.check_password(old_pw):
                messages.error(request, 'Current password is incorrect.')
            elif new_pw != confirm:
                messages.error(request, 'New passwords do not match.')
            elif len(new_pw) < 6:
                messages.error(request, 'Password must be at least 6 characters long.')
            else:
                request.user.set_password(new_pw)
                request.user.save()
                update_session_auth_hash(request, request.user)
                messages.success(request, 'Password updated successfully')
            
            return redirect('/settings/')
    
    # Handle GET request (display form)
    return render(request, 'projects/settings.html', {'success': success, 'error': error})


@login_required
def delete_account(request):
    if request.method == 'POST':
        user = request.user
        logout(request)
        user.delete()
        return redirect('/register/')
    return redirect('/settings/')


@login_required
def help_view(request):
    shortcuts = [
        {'label': 'Quick Search',         'keys': ['/']},
        {'label': 'Close Modal / Panel',  'keys': ['ESC']},
        {'label': 'Add New Task (Board)', 'keys': ['/', 'T']},
        {'label': 'Submit Form',          'keys': ['CTRL', 'ENTER']},
        {'label': 'Navigate Projects',    'keys': ['CTRL', 'SHIFT', 'P']},
        {'label': 'Open Settings',       'keys': ['CTRL', 'SHIFT', 'S']},
        {'label': 'View Team',           'keys': ['ALT', 'T']},
    ]
    faqs = [
        {'question': 'How do I create a new project?',
         'answer':   'Click the "New Project" button on the Projects page. Fill in the name, description, and deadline (required), then click Create.'},
        {'question': 'How do I move a task between columns?',
         'answer':   'Simply drag and drop a task card from one column (To Do / Doing / Done) to another on the board. The status updates automatically.'},
        {'question': 'How do notifications work?',
         'answer':   'You receive a notification when a task you are assigned to is moved to a different column, or when a task is due within 3 days.'},
        {'question': 'How do I add team members?',
         'answer':   'Go to the Team page and click "Invite Member". Enter their username to add them.'},
        {'question': 'Can I change my password?',
         'answer':   'Yes — go to Settings, scroll to the "Change Password" section, enter your current and new password, then save.'},
        {'question': 'What is the difference between Project Categories and Task Categories?',
         'answer':   'Project Categories are used to group and filter your projects (e.g. "Design", "Engineering"). Task Categories are separate labels for individual tasks within any project (e.g. "Bug", "Feature", "Research").'},
        {'question': 'How do I reset my password if I forgot it?',
         'answer':   'Click "Forgot password?" on the login page. Enter your username, then check your email for a 6-digit OTP code. Enter the code to set a new password. The OTP expires in 10 minutes.'},
    ]
    return render(request, 'projects/help.html', {'shortcuts': shortcuts, 'faqs': faqs})


@login_required
def edit_project(request, project_id):
    project = get_object_or_404(Project, id=project_id, owner=request.user)
    if request.method == 'POST':
        name        = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        deadline    = request.POST.get('deadline', '').strip()
        status      = request.POST.get('status', 'active')
        category_id = request.POST.get('category_id') or None
        if not deadline:
            return redirect('/?error=deadline_required')
        if name:
            project.name        = name
            project.description = description
            project.deadline    = deadline
            project.status      = status
            project.category_id = category_id
            project.save()
    return redirect('/')


@login_required
def delete_project(request, project_id):
    project = get_object_or_404(Project, id=project_id, owner=request.user)
    if request.method == 'POST':
        project.delete()
        return JsonResponse({'status': 'ok'})
    return JsonResponse({'error': 'POST only'}, status=405)


@login_required
def get_notifications(request):
    notifs_qs = Notification.objects.filter(user=request.user)
    unread    = notifs_qs.filter(is_read=False).count()
    notifs    = notifs_qs[:20]
    data = [{
        'id':         n.id,
        'message':    n.message,
        'type':       n.notif_type,
        'is_read':    n.is_read,
        'created_at': n.created_at.strftime('%d %b, %H:%M'),
    } for n in notifs]
    return JsonResponse({'notifications': data, 'unread': unread})


@login_required
def mark_notifications_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return JsonResponse({'status': 'ok'})


# ══════════════════════════════════════════════════════════════
#  FILE MANAGEMENT VIEWS
# ══════════════════════════════════════════════════════════════

@login_required
def file_manager(request):
    """หน้าจัดการไฟล์ทั้งหมด"""
    user_files = FileAttachment.objects.filter(
        Q(uploaded_by=request.user) |
        Q(project__owner=request.user) |
        Q(project__members__user=request.user) |
        Q(can_view=request.user)
    ).select_related('project', 'task', 'uploaded_by').prefetch_related(
        'can_view', 'can_download', 'can_edit'
    ).distinct()

    # กรองตามโปรเจค
    project_id = request.GET.get('project')
    if project_id:
        user_files = user_files.filter(project_id=project_id)

    # กรองตามประเภทไฟล์
    file_type = request.GET.get('type')
    if file_type:
        user_files = user_files.filter(file_type=file_type)

    # กรองตามคำค้นหา
    search = request.GET.get('search')
    if search:
        user_files = user_files.filter(filename__icontains=search)

    # Annotate สิทธิ์ลง object โดยตรง เพื่อให้ template เรียกได้แบบ attribute
    files_with_perms = []
    for f in user_files:
        f.perm_download = f.can_user_download(request.user)
        f.perm_edit     = f.can_user_edit(request.user)
        f.perm_delete   = (f.uploaded_by == request.user or f.project.owner == request.user)
        files_with_perms.append(f)

    accessible_projects = Project.objects.filter(
        Q(owner=request.user) | Q(members__user=request.user)
    ).distinct()

    return render(request, 'projects/file_manager.html', {
        'files':      files_with_perms,
        'projects':   accessible_projects,
        'file_types': FileAttachment.FILE_TYPES,
    })


@login_required
def upload_file(request):
    """อัปโหลดไฟล์"""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        file       = request.FILES.get("file")
        project_id = request.POST.get("project_id")
        task_id    = request.POST.get("task_id")
        comment_id = request.POST.get("comment_id")

        if not file:
            return JsonResponse({"error": "No file provided"}, status=400)

        # ── ตรวจสิทธิ์ ─────────────────────────────────────────────────────
        project = get_object_or_404(Project, id=project_id)
        if not (
            project.owner == request.user
            or ProjectMember.objects.filter(project=project, user=request.user).exists()
        ):
            return JsonResponse({"error": "Permission denied"}, status=403)

        # ── Detect file_type ก่อน ─────────────────────────────────────────
        # สำคัญ: ต้องรู้ file_type ก่อนที่ Django จะ save FileField
        # เพราะ upload_to (attachment_upload_path) ใช้ instance.file_type
        # ในการสร้าง path → ถ้า set ทีหลังจะได้ path "other" ผิดทุกครั้ง
        file_type = FileAttachment._detect_file_type(file.name)

        # ── สร้าง instance โดยกำหนด file_type ก่อน แล้วค่อย assign file ──
        # (หาก objects.create(file=file, ...) โดยไม่ผ่าน _detect_file_type
        #  ก่อน → file_type จะยังเป็น default 'other' ตอนที่ upload_to ถูกเรียก
        #  แม้ว่า save() จะ detect ทีหลัง แต่ path ถูกคำนวณแล้ว ณ ตอนนั้น)
        attachment = FileAttachment(
            file_type  = file_type,
            filename   = file.name.split("/")[-1],
            file_size  = file.size,
            uploaded_by= request.user,
            project    = project,
            task_id    = task_id    or None,
            comment_id = comment_id or None,
        )
        attachment.file = file               # ← assign file หลังจาก file_type พร้อมแล้ว
        attachment.save()

        return JsonResponse({
            "success"   : True,
            "file_id"   : attachment.id,
            "filename"  : attachment.filename,
            "file_type" : attachment.file_type,
            "file_size" : attachment.get_file_size_display(),
            "created_at": attachment.created_at.strftime("%d %b, %H:%M"),
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def file_detail(request, file_id):
    """รายละเอียดไฟล์"""
    file_obj = get_object_or_404(FileAttachment, id=file_id)
    
    # ตรวจสอบสิทธิ์การดู
    if not file_obj.can_user_view(request.user):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    return JsonResponse({
        'id': file_obj.id,
        'filename': file_obj.filename,
        'file_type': file_obj.file_type,
        'file_size': file_obj.get_file_size_display(),
        'uploaded_by': file_obj.uploaded_by.profile.display_name if file_obj.uploaded_by.profile else file_obj.uploaded_by.username,
        'project': file_obj.project.name,
        'task': file_obj.task.title if file_obj.task else None,
        'created_at': file_obj.created_at.strftime('%d %b %Y, %H:%M'),
        'can_download': file_obj.can_user_download(request.user),
        'can_edit': file_obj.can_user_edit(request.user),
    })


@login_required
def download_file(request, file_id):
    """ดาวน์โหลดไฟล์"""
    file_obj = get_object_or_404(FileAttachment, id=file_id)
    
    # ตรวจสอบสิทธิ์การดาวน์โหลด
    if not file_obj.can_user_download(request.user):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    # สร้าง HTTP response
    from django.http import HttpResponse
    import os
    
    if os.path.exists(file_obj.file.path):
        with open(file_obj.file.path, 'rb') as f:
            response = HttpResponse(f.read(), content_type='application/octet-stream')
            response['Content-Disposition'] = f'attachment; filename="{file_obj.filename}"'
            return response
    else:
        return JsonResponse({'error': 'File not found'}, status=404)


@login_required
def update_file_permissions(request, file_id):
    """อัปเดตสิทธิ์ไฟล์"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    file_obj = get_object_or_404(FileAttachment, id=file_id)
    
    # ตรวจสอบสิทธิ์การแก้ไข
    if not file_obj.can_user_edit(request.user):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        # รับข้อมูลสิทธิ์
        view_users = request.POST.getlist('view_users')
        download_users = request.POST.getlist('download_users')
        edit_users = request.POST.getlist('edit_users')
        
        # ล้างสิทธิ์เก่า
        file_obj.can_view.clear()
        file_obj.can_download.clear()
        file_obj.can_edit.clear()
        
        # เพิ่มสิทธิ์ใหม่
        if view_users:
            file_obj.can_view.set(view_users)
        if download_users:
            file_obj.can_download.set(download_users)
        if edit_users:
            file_obj.can_edit.set(edit_users)
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def delete_file(request, file_id):
    """ลบไฟล์"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    file_obj = get_object_or_404(FileAttachment, id=file_id)
    
    # ตรวจสอบสิทธิ์การลบ (เจ้าของไฟล์หรือเจ้าของโปรเจค)
    if not (file_obj.uploaded_by == request.user or file_obj.project.owner == request.user):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        # ลบไฟล์จริง
        if file_obj.file and os.path.exists(file_obj.file.path):
            os.remove(file_obj.file.path)
        
        # ลบ record
        file_obj.delete()
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def rename_file(request, file_id):
    """เปลี่ยนชื่อไฟล์ (เฉพาะ filename field — ไม่เปลี่ยนชื่อไฟล์จริงบน disk)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    file_obj = get_object_or_404(FileAttachment, id=file_id)

    if not file_obj.can_user_edit(request.user):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    new_name = request.POST.get('filename', '').strip()
    if not new_name:
        return JsonResponse({'error': 'Filename is required'}, status=400)

    file_obj.filename = new_name
    file_obj.save(update_fields=['filename'])
    return JsonResponse({'success': True, 'filename': file_obj.filename})


# ── compat alias — ลบ view เดิม password_reset ออก แล้วใช้ตัวนี้แทน ──
password_reset = password_reset_request


# ── Static pages ──────────────────────────────────────────────
def terms_view(request):
    sections = [
        {'title': 'Acceptance of Terms',
         'body': 'By accessing or using KanFlow, you agree to be bound by these Terms of Service.'},
        {'title': 'Use of the Service',
         'body': 'KanFlow is a project management tool intended for personal and educational use.'},
        {'title': 'Your Account',
         'body': 'You are responsible for maintaining the confidentiality of your account credentials.'},
        {'title': 'Data and Content',
         'body': 'You retain ownership of all content you create within KanFlow.'},
        {'title': 'Modifications',
         'body': 'We reserve the right to modify these terms at any time.'},
        {'title': 'Limitation of Liability',
         'body': 'KanFlow is provided "as is" without warranties of any kind.'},
    ]
    return render(request, 'projects/terms.html', {'sections': sections})


def privacy_view(request):
    sections = [
        {'title': 'Information We Collect',
         'body': 'We collect information you provide directly, such as your username and the content you create.'},
        {'title': 'How We Use Your Information',
         'body': 'Your information is used solely to provide and improve the KanFlow service.'},
        {'title': 'Data Storage',
         'body': 'Your data is stored locally on the server running KanFlow.'},
        {'title': 'Cookies',
         'body': 'KanFlow uses session cookies to keep you logged in.'},
        {'title': 'Your Rights',
         'body': 'You may delete your account at any time via the Settings page.'},
        {'title': 'Contact',
         'body': 'If you have any questions, please contact the administrator of this KanFlow instance.'},
    ]
    return render(request, 'projects/privacy.html', {'sections': sections})


def get_project_tasks(request, project_id):
    """API endpoint to get tasks for a specific project"""
    try:
        project = Project.objects.get(id=project_id)
        
        # Check if user has access to this project
        if project.owner != request.user and not ProjectMember.objects.filter(project=project, user=request.user).exists():
            return JsonResponse({'error': 'Access denied'}, status=403)
        
        tasks = Task.objects.filter(project=project).values('id', 'title', 'status')
        return JsonResponse({'tasks': list(tasks)})
    
    except Project.DoesNotExist:
        return JsonResponse({'error': 'Project not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def get_tasks(request):
    """AJAX endpoint to get tasks for a specific project"""
    # ตรวจ login แบบ manual เพื่อ return JSON แทน redirect
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'not authenticated'}, status=401)

    project_id = request.GET.get('project_id')
    if not project_id:
        return JsonResponse([], safe=False)

    try:
        project = Project.objects.get(id=project_id)

        # ตรวจสิทธิ์ — owner หรือ member เข้าได้
        is_owner  = project.owner == request.user
        is_member = ProjectMember.objects.filter(
            project=project, user=request.user
        ).exists()

        if not is_owner and not is_member:
            return JsonResponse([], safe=False)

        # ดึง task ทุกตัวในโปรเจคนี้
        tasks = Task.objects.filter(project=project).order_by('status', 'title').values('id', 'title', 'status')
        results = [{'id': t['id'], 'name': t['title']} for t in tasks]

        return JsonResponse(results, safe=False)

    except Project.DoesNotExist:
        return JsonResponse([], safe=False)
    except Exception as e:
        print(f"[get_tasks] ERROR: {e}")
        return JsonResponse([], safe=False)


# ══════════════════════════════════════════════════════════════
#  Analytics & Reports — imported from separate modules
# ══════════════════════════════════════════════════════════════
from .analytics_views import personal_analytics, team_analytics
from .reports_views   import reports_view, export_excel, export_pdf
