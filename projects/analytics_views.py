from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.contrib.auth.models import User
from django.db.models import Count, Q, Avg
from django.utils import timezone
from datetime import timedelta

from projects.models import Project, ProjectMember, ActivityLog
from tasks.models import Task


# ══════════════════════════════════════════════════════════════
#  PERSONAL ANALYTICS  /analytics/
# ══════════════════════════════════════════════════════════════

@login_required
def personal_analytics(request):
    from datetime import datetime
    today = timezone.localdate()
    now   = timezone.now()

    # ── โปรเจคของตัวเอง + ที่เป็นสมาชิก ──────────────────────
    own_projects    = Project.objects.filter(owner=request.user)
    member_pids     = ProjectMember.objects.filter(user=request.user).values_list('project_id', flat=True)
    all_my_projects = Project.objects.filter(Q(owner=request.user) | Q(id__in=member_pids)).distinct()

    # ── Task ทั้งหมดที่ assigned ให้ตัวเอง ─────────────────────
    my_tasks = Task.objects.filter(assigned_to=request.user).select_related('project')

    total_tasks     = my_tasks.count()
    done_tasks      = my_tasks.filter(status='done').count()
    doing_tasks     = my_tasks.filter(status='doing').count()
    todo_tasks      = my_tasks.filter(status='todo').count()
    overdue_tasks   = my_tasks.exclude(status='done').filter(due_date__lt=today).count()
    completion_rate = round(done_tasks / total_tasks * 100) if total_tasks else 0

    # ── Peak Hours (จาก ActivityLog) ──────────────────────────
    activities = ActivityLog.objects.filter(user=request.user)
    hour_counts = [0] * 24
    for act in activities:
        local_ts = timezone.localtime(act.timestamp)
        hour_counts[local_ts.hour] += 1

    peak_hour = hour_counts.index(max(hour_counts)) if any(hour_counts) else 9
    peak_label = f"{peak_hour:02d}:00–{peak_hour+1:02d}:00"

    # ── Focus Score (0–100) ────────────────────────────────────
    # คำนวณจาก: completion_rate * 0.5 + (1 - overdue/total) * 0.5
    overdue_ratio = overdue_tasks / total_tasks if total_tasks else 0
    focus_score   = round(completion_rate * 0.5 + (1 - overdue_ratio) * 50)

    # ── Avg Tasks / Day (7 วันล่าสุด) ─────────────────────────
    week_ago   = today - timedelta(days=7)
    week_tasks = my_tasks.filter(created_at__date__gte=week_ago).count()
    avg_tasks_per_day = round(week_tasks / 7, 1)

    # ── Completion Trend (8 สัปดาห์) ──────────────────────────
    trend_data     = []
    current_monday = today - timedelta(days=today.weekday())
    for i in range(7, -1, -1):
        week_start = current_monday - timedelta(weeks=i)
        week_end   = week_start + timedelta(days=6)
        added = my_tasks.filter(created_at__date__range=[week_start, week_end]).count()
        done  = my_tasks.filter(status='done', created_at__date__range=[week_start, week_end]).count()
        trend_data.append({
            'label': week_start.strftime('%d %b').lstrip('0'),
            'added': added,
            'done':  done,
        })

    # ── Project Health (เฉพาะโปรเจคของตัวเอง) ────────────────
    project_health = []
    for p in own_projects.order_by('-created_at')[:8]:
        ptasks = my_tasks.filter(project=p)
        ptotal = ptasks.count()
        pdone  = ptasks.filter(status='done').count()
        pdoing = ptasks.filter(status='doing').count()
        ptodo  = ptasks.filter(status='todo').count()
        pover  = ptasks.exclude(status='done').filter(due_date__lt=today).count()
        prog   = round(pdone / ptotal * 100) if ptotal else 0

        if prog >= 75:
            health = 'good'
        elif prog >= 40 or pover == 0:
            health = 'warning'
        else:
            health = 'critical'

        project_health.append({
            'id':       p.id,
            'name':     p.name,
            'total':    ptotal,
            'done':     pdone,
            'doing':    pdoing,
            'todo':     ptodo,
            'overdue':  pover,
            'progress': prog,
            'health':   health,
            'status':   p.status,
            'deadline': p.deadline,
        })

    # ── Project Stats for Workspace Overview ───────────────────
    project_stats = []
    for p in all_my_projects.order_by('name')[:8]:  # Sort alphabetically by name
        ptasks = my_tasks.filter(project=p)
        ptotal = ptasks.count()
        pdone  = ptasks.filter(status='done').count()
        prog   = round(pdone / ptotal * 100) if ptotal else 0

        project_stats.append({
            'id':       p.id,
            'name':     p.name,
            'total':    ptotal,
            'done':     pdone,
            'progress': prog,
        })

    # ── Personal Recommendations ──────────────────────────────
    recommendations = _personal_recommendations(
        completion_rate, overdue_tasks, total_tasks,
        focus_score, avg_tasks_per_day, project_health
    )

    return render(request, 'projects/analytics_personal.html', {
        # Stats
        'total_tasks':      total_tasks,
        'done_tasks':       done_tasks,
        'doing_tasks':      doing_tasks,
        'todo_tasks':       todo_tasks,
        'overdue_tasks':    overdue_tasks,
        'completion_rate':  completion_rate,
        # Performance
        'peak_label':       peak_label,
        'peak_hour':        peak_hour,
        'focus_score':      focus_score,
        'avg_tasks_per_day': avg_tasks_per_day,
        # Charts
        'trend_data':       trend_data,
        'project_stats':    project_stats,
        'project_health':   project_health,
        # Recommendations
        'recommendations':  recommendations,
    })


def _personal_recommendations(completion_rate, overdue, total, focus, avg, project_health):
    recs = []
    if overdue > 0:
        recs.append({
            'icon':    'alert-triangle',
            'color':   'red',
            'title':   f'มี {overdue} งานที่เกินกำหนด',
            'detail':  'ควรจัดลำดับความสำคัญและติดต่อผู้เกี่ยวข้อง',
        })
    if completion_rate < 40 and total > 0:
        recs.append({
            'icon':    'trending-down',
            'color':   'orange',
            'title':   'อัตราการทำงานเสร็จต่ำกว่า 40%',
            'detail':  'ลองแบ่งงานใหญ่เป็นงานย่อย ๆ เพื่อเพิ่มโมเมนตัม',
        })
    if avg < 1 and total > 0:
        recs.append({
            'icon':    'clock',
            'color':   'blue',
            'title':   'ยังไม่ค่อยได้สร้างงานใหม่สัปดาห์นี้',
            'detail':  'ลองวางแผนงานประจำวันเพื่อให้โปรเจคเดินหน้า',
        })
    critical = [p for p in project_health if p['health'] == 'critical']
    if critical:
        recs.append({
            'icon':    'activity',
            'color':   'red',
            'title':   f'{len(critical)} โปรเจคอยู่ในสถานะวิกฤต',
            'detail':  f'เช่น "{critical[0]["name"]}" — ควรตรวจสอบด่วน',
        })
    if focus >= 80:
        recs.append({
            'icon':    'star',
            'color':   'green',
            'title':   'Focus Score ยอดเยี่ยม!',
            'detail':  'คุณทำงานได้อย่างมีประสิทธิภาพมาก ทำต่อไปเลย',
        })
    if not recs:
        recs.append({
            'icon':    'check-circle',
            'color':   'green',
            'title':   'ทุกอย่างดูดี!',
            'detail':  'ไม่มีปัญหาเร่งด่วนในขณะนี้',
        })
    return recs[:4]


# ══════════════════════════════════════════════════════════════
#  TEAM ANALYTICS  /analytics/team/
# ══════════════════════════════════════════════════════════════

@login_required
def team_analytics(request):
    today = timezone.localdate()

    # โปรเจคที่ user เป็น owner
    owned_projects = Project.objects.filter(owner=request.user)
    if not owned_projects.exists():
        return render(request, 'projects/analytics_team.html', {'no_projects': True})

    # สมาชิกทั้งหมด (รวม owner)
    member_ids = list(
        ProjectMember.objects.filter(project__in=owned_projects)
        .values_list('user_id', flat=True).distinct()
    )
    member_ids = list(set(member_ids + [request.user.id]))
    members    = User.objects.filter(id__in=member_ids).select_related('profile')

    all_tasks = Task.objects.filter(project__in=owned_projects)

    # ── Team Overview ──────────────────────────────────────────
    total_members    = len(member_ids)
    total_tasks      = all_tasks.count()
    done_tasks_count = all_tasks.filter(status='done').count()
    team_completion  = round(done_tasks_count / total_tasks * 100) if total_tasks else 0

    # Collaboration Score = % สมาชิกที่มีงาน done อย่างน้อย 1 งาน
    members_with_done = 0
    for mid in member_ids:
        if all_tasks.filter(assigned_to_id=mid, status='done').exists():
            members_with_done += 1
    collab_score = round(members_with_done / total_members * 100) if total_members else 0

    # ── Member Performance ─────────────────────────────────────
    member_stats = []
    for m in members:
        m_tasks = all_tasks.filter(assigned_to=m)
        m_total = m_tasks.count()
        m_done  = m_tasks.filter(status='done').count()
        m_doing = m_tasks.filter(status='doing').count()
        m_over  = m_tasks.exclude(status='done').filter(due_date__lt=today).count()
        m_eff   = round(m_done / m_total * 100) if m_total else 0

        # Workload balance: เทียบกับ avg
        avg_tasks = total_tasks / total_members if total_members else 0
        if avg_tasks == 0:
            workload_label = 'balanced'
        elif m_total > avg_tasks * 1.3:
            workload_label = 'overloaded'
        elif m_total < avg_tasks * 0.5:
            workload_label = 'underloaded'
        else:
            workload_label = 'balanced'

        member_stats.append({
            'user':           m,
            'display_name':   m.profile.get_display_name() if hasattr(m, 'profile') else m.username,
            'avatar_url':     m.profile.get_avatar_url() if hasattr(m, 'profile') else None,
            'total':          m_total,
            'done':           m_done,
            'doing':          m_doing,
            'overdue':        m_over,
            'efficiency':     m_eff,
            'workload_label': workload_label,
            'is_owner':       m.id == request.user.id,
        })

    # เรียง efficiency สูง → ต่ำ
    member_stats.sort(key=lambda x: x['efficiency'], reverse=True)

    # ── Avg Efficiency ─────────────────────────────────────────
    avg_efficiency = round(
        sum(m['efficiency'] for m in member_stats) / len(member_stats)
    ) if member_stats else 0

    # ── Workload Pie (สัดส่วนงานต่อ member) ───────────────────
    workload_data = [
        {'name': m['display_name'], 'count': m['total']}
        for m in member_stats if m['total'] > 0
    ]

    # ── Team Recommendations ───────────────────────────────────
    recommendations = _team_recommendations(
        member_stats, team_completion, collab_score, total_tasks
    )

    return render(request, 'projects/analytics_team.html', {
        'total_members':   total_members,
        'total_tasks':     total_tasks,
        'team_completion': team_completion,
        'collab_score':    collab_score,
        'avg_efficiency':  avg_efficiency,
        'member_stats':    member_stats,
        'workload_data':   workload_data,
        'recommendations': recommendations,
        'owned_projects':  owned_projects,
        'no_projects':     False,
    })


def _team_recommendations(member_stats, completion, collab, total):
    recs = []
    overloaded = [m for m in member_stats if m['workload_label'] == 'overloaded']
    underloaded = [m for m in member_stats if m['workload_label'] == 'underloaded']

    if overloaded and underloaded:
        recs.append({
            'icon':   'shuffle',
            'color':  'orange',
            'title':  'Workload ไม่สมดุล',
            'detail': f'{overloaded[0]["display_name"]} มีงานมากเกินไป — ลองโยกงานให้ {underloaded[0]["display_name"]}',
        })
    for m in member_stats:
        if m['overdue'] > 2:
            recs.append({
                'icon':   'alert-triangle',
                'color':  'red',
                'title':  f'{m["display_name"]} มี {m["overdue"]} งานเกินกำหนด',
                'detail': 'ควรติดตามและช่วยเหลือสมาชิกคนนี้',
            })
            break
    if collab < 50 and total > 0:
        recs.append({
            'icon':   'users',
            'color':  'blue',
            'title':  'Collaboration Score ต่ำกว่า 50%',
            'detail': 'สมาชิกหลายคนยังไม่มีงานที่เสร็จ — ลองจัดประชุมทีม',
        })
    if completion >= 70:
        recs.append({
            'icon':   'award',
            'color':  'green',
            'title':  f'ทีมมี completion rate {completion}%',
            'detail': 'ทีมทำงานได้ดีมาก ขอบคุณทุกคน!',
        })
    if not recs:
        recs.append({
            'icon':   'check-circle',
            'color':  'green',
            'title':  'ทีมทำงานสมดุลดี',
            'detail': 'ไม่มีปัญหาเร่งด่วนในขณะนี้',
        })
    return recs[:4]
