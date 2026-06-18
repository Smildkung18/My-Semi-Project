import json
import os

import requests
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from .models import Schedule, ScheduleEntry, CalendarEvent

MAX_SCHEDULES = 3


# ── Page ──────────────────────────────────────────────────────────────────
@login_required
def schedule_page(request):
    """Renders the Schedule SPA shell."""
    return render(request, 'schedules/schedule.html')


# ── API: Schedules ────────────────────────────────────────────────────────
@login_required
@require_http_methods(['GET', 'POST'])
def api_schedules(request):
    if request.method == 'GET':
        schedules = Schedule.objects.filter(owner=request.user)
        return JsonResponse({'schedules': [s.as_dict() for s in schedules]})

    # POST — create
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    name = (data.get('name') or '').strip()
    stype = data.get('type', '')

    if not name:
        return JsonResponse({'error': 'ชื่อตารางห้ามว่าง'}, status=400)
    if stype not in ('work', 'study', 'teach'):
        return JsonResponse({'error': 'ประเภทตารางไม่ถูกต้อง'}, status=400)

    count = Schedule.objects.filter(owner=request.user).count()
    if count >= MAX_SCHEDULES:
        return JsonResponse({'error': f'สร้างได้สูงสุด {MAX_SCHEDULES} ตาราง'}, status=400)

    sched = Schedule.objects.create(
        owner=request.user,
        name=name,
        type=stype,
        order=count,
    )
    return JsonResponse({'schedule': sched.as_dict()}, status=201)


@login_required
@require_http_methods(['DELETE'])
def api_schedule_detail(request, pk):
    sched = get_object_or_404(Schedule, pk=pk, owner=request.user)
    sched.delete()
    return JsonResponse({'deleted': pk})


# ── API: Entries ──────────────────────────────────────────────────────────
@login_required
@require_http_methods(['POST'])
def api_entries(request, schedule_pk):
    sched = get_object_or_404(Schedule, pk=schedule_pk, owner=request.user)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    subject  = (data.get('subject') or '').strip()
    day      = data.get('day')
    start    = data.get('start')
    end      = data.get('end')
    location = (data.get('location') or '').strip()
    etype    = data.get('entry_type') or None
    credit   = data.get('credit')  # optional int
    section  = (data.get('section') or '').strip()

    # Validate
    if not subject:
        return JsonResponse({'error': 'กรุณากรอกชื่อ'}, status=400)
    if day is None or not isinstance(day, int) or day not in range(7):
        return JsonResponse({'error': 'วันไม่ถูกต้อง'}, status=400)
    if not start or not end:
        return JsonResponse({'error': 'กรุณาระบุเวลา'}, status=400)
    if start >= end:
        return JsonResponse({'error': 'เวลาสิ้นสุดต้องมากกว่าเวลาเริ่มต้น'}, status=400)
    if sched.type in ('study', 'teach') and etype not in ('theory', 'practice'):
        return JsonResponse({'error': 'กรุณาเลือกประเภท ทฤษฎี/ปฏิบัติ'}, status=400)
    if sched.type == 'work':
        etype = None

    entry = ScheduleEntry.objects.create(
        schedule=sched,
        subject=subject,
        day=day,
        start_time=start,
        end_time=end,
        location=location,
        entry_type=etype,
        section=section,
        credit=credit if isinstance(credit, int) and 0 <= credit <= 9 else None,
    )
    return JsonResponse({'entry': entry.as_dict()}, status=201)


@login_required
@require_http_methods(['DELETE'])
def api_entry_detail(request, pk):
    entry = get_object_or_404(ScheduleEntry, pk=pk, schedule__owner=request.user)
    entry.delete()
    return JsonResponse({'deleted': pk})


# ── API: Calendar Events ──────────────────────────────────────────────────
@login_required
@require_http_methods(['GET', 'POST'])
def api_calendar_events(request):
    if request.method == 'GET':
        schedule_id = request.GET.get('schedule_id')
        if not schedule_id:
            return JsonResponse({'error': 'กรุณาระบุ schedule_id'}, status=400)
        sched = get_object_or_404(Schedule, pk=schedule_id, owner=request.user)

        try:
            year  = int(request.GET.get('year',  0))
            month = int(request.GET.get('month', 0))
        except ValueError:
            return JsonResponse({'error': 'Invalid params'}, status=400)

        qs = CalendarEvent.objects.filter(schedule=sched)
        if year and month:
            ce_year = year if year < 2500 else year - 543
            qs = qs.filter(event_date__year=ce_year, event_date__month=month)
        return JsonResponse({'events': [e.as_dict() for e in qs]})

    # POST — create
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    schedule_id = data.get('schedule_id')
    if not schedule_id:
        return JsonResponse({'error': 'กรุณาระบุ schedule_id'}, status=400)
    sched = get_object_or_404(Schedule, pk=schedule_id, owner=request.user)

    title      = (data.get('title') or '').strip()
    event_date = (data.get('date') or '').strip()
    detail     = (data.get('detail') or '').strip()
    start      = (data.get('start') or '').strip() or None
    end        = (data.get('end') or '').strip() or None
    location   = (data.get('location') or '').strip()
    color      = data.get('color', 'indigo')
    remind     = data.get('remind_before', 15)

    if not title:
        return JsonResponse({'error': 'กรุณากรอกชื่อกิจกรรม'}, status=400)
    if not event_date:
        return JsonResponse({'error': 'กรุณาระบุวันที่'}, status=400)
    if color not in ('indigo', 'green', 'rose', 'amber', 'sky', 'orange'):
        color = 'indigo'
    try:
        remind = int(remind)
    except (TypeError, ValueError):
        remind = 15

    from datetime import datetime as dt_type
    try:
        parsed_date = dt_type.strptime(event_date, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'รูปแบบวันที่ไม่ถูกต้อง (YYYY-MM-DD)'}, status=400)

    ev = CalendarEvent.objects.create(
        owner=request.user,
        schedule=sched,
        title=title,
        detail=detail,
        event_date=parsed_date,
        start_time=start,
        end_time=end,
        location=location,
        color=color,
        remind_before=remind,
    )
    return JsonResponse({'event': ev.as_dict()}, status=201)


@login_required
@require_http_methods(['GET', 'PUT', 'DELETE'])
def api_calendar_event_detail(request, pk):
    ev = get_object_or_404(CalendarEvent, pk=pk, schedule__owner=request.user)

    if request.method == 'DELETE':
        ev.delete()
        return JsonResponse({'deleted': pk})

    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        new_date = (data.get('date') or str(ev.event_date)).strip()
        from datetime import datetime as dt_type
        try:
            ev.event_date = dt_type.strptime(new_date, '%Y-%m-%d').date()
        except ValueError:
            return JsonResponse({'error': 'รูปแบบวันที่ไม่ถูกต้อง'}, status=400)
        ev.title      = (data.get('title') or ev.title).strip()
        ev.detail     = (data.get('detail') or '').strip()
        ev.start_time = (data.get('start') or '').strip() or None
        ev.end_time   = (data.get('end') or '').strip() or None
        ev.location   = (data.get('location') or '').strip()
        color = data.get('color', ev.color)
        ev.color = color if color in ('indigo','green','rose','amber','sky','orange') else ev.color
        try:
            ev.remind_before = int(data.get('remind_before', ev.remind_before))
        except (TypeError, ValueError):
            pass
        ev.save()
        return JsonResponse({'event': ev.as_dict()})

    # GET single
    return JsonResponse({'event': ev.as_dict()})


# ── API: Schedule Notifications ───────────────────────────────────────────
@login_required
@require_http_methods(['POST'])
def api_schedule_notify(request):
    """
    ตรวจวิชาที่ใกล้เริ่ม (ภายใน 15 นาที) ของวันนี้
    และสร้าง Notification ถ้ายังไม่เคยสร้างวันนี้
    frontend เรียก endpoint นี้ทุก 5 นาที
    """
    from django.utils import timezone
    from datetime import timedelta
    try:
        from projects.models import Notification
    except ImportError:
        return JsonResponse({'notified': 0})

    now = timezone.localtime()
    today_day = now.weekday() + 1  # Mon=1 … Sat=6, แล้ว Sun จะเป็น 7→0
    if today_day == 7:
        today_day = 0

    window_start = now.time()
    window_end   = (now + timedelta(minutes=15)).time()

    schedules = Schedule.objects.filter(owner=request.user).prefetch_related('entries')
    notified  = 0

    for sched in schedules:
        for entry in sched.entries.all():
            if entry.day != today_day:
                continue
            st = entry.start_time
            if not (window_start <= st <= window_end):
                continue

            # dedup key — 1 notification ต่อ entry ต่อวัน
            dedup_key = f'schedule:{entry.id}:{now.date()}'
            already   = Notification.objects.filter(
                user=request.user,
                message__startswith=dedup_key,
            ).exists()
            if already:
                continue

            start_str = entry.start_time.strftime('%H:%M')
            msg = f'{dedup_key} — {entry.subject} เริ่มเวลา {start_str}'
            if entry.location:
                msg += f' ที่ {entry.location}'
            msg += f' ({sched.name})'

            Notification.objects.create(
                user=request.user,
                message=msg,
                notif_type='schedule_reminder',
            )
            notified += 1

    return JsonResponse({'notified': notified})


# ── API: Calendar Event Notifications ────────────────────────────────────
@login_required
@require_http_methods(['POST'])
def api_calendar_notify(request):
    """ตรวจ CalendarEvent ที่ใกล้ถึง และสร้าง Notification"""
    from django.utils import timezone
    from datetime import timedelta
    try:
        from projects.models import Notification
    except ImportError:
        return JsonResponse({'notified': 0})

    now   = timezone.localtime()
    today = now.date()
    notified = 0

    events = CalendarEvent.objects.filter(owner=request.user, event_date__gte=today)
    for ev in events:
        if ev.remind_before == 0:
            continue

        # คำนวณเวลาที่ต้องแจ้ง
        if ev.start_time:
            from datetime import datetime
            import pytz
            tz = timezone.get_current_timezone()
            event_dt  = datetime.combine(ev.event_date, ev.start_time)
            event_dt  = tz.localize(event_dt)
            remind_dt = event_dt - timedelta(minutes=ev.remind_before)
            if not (remind_dt <= now <= event_dt):
                continue
        else:
            # ไม่ระบุเวลา — แจ้งตอนเช้าวันนั้น (07:00-08:00)
            if ev.event_date != today:
                continue
            if not (7 <= now.hour < 8):
                continue

        dedup_key = f'calevent:{ev.id}:{today}'
        already = Notification.objects.filter(
            user=request.user,
            message__startswith=dedup_key,
        ).exists()
        if already:
            continue

        time_str = f' เวลา {ev.start_time.strftime("%H:%M")}' if ev.start_time else ''
        msg = f'{dedup_key} — {ev.title} วันที่ {ev.event_date.strftime("%d/%m/%Y")}{time_str}'
        if ev.location:
            msg += f' ที่ {ev.location}'

        Notification.objects.create(
            user=request.user,
            message=msg,
            notif_type='calendar_reminder',
        )
        notified += 1

    return JsonResponse({'notified': notified})


# ── Helper: ดึง free models จาก OpenRouter แบบ dynamic ─────────────────
def _get_free_models(api_key: str) -> list[str]:
    """
    ดึงรายชื่อ free models จาก OpenRouter API ณ ขณะนั้น
    เพื่อไม่ต้อง hardcode ชื่อที่อาจ 404 เมื่อ model ถูกถอดออก
    """
    try:
        resp = requests.get(
            'https://openrouter.ai/api/v1/models',
            headers={'Authorization': f'Bearer {api_key}'},
            timeout=10,
        )
        if not resp.ok:
            return []
        models = resp.json().get('data', [])
        free = [
            m['id'] for m in models
            if m.get('id', '').endswith(':free')
            and str(m.get('pricing', {}).get('prompt', '1')) == '0'
        ]
        return free[:12]  # ใช้สูงสุด 12 model
    except Exception:
        return []


# ── API: AI Parse Schedule ────────────────────────────────────────────────
@login_required
@require_http_methods(['POST'])
def ai_parse_schedule(request):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    raw_text   = (body.get('text') or '').strip()
    sched_type = body.get('schedule_type', 'study')

    if not raw_text:
        return JsonResponse({'error': 'ไม่มีข้อมูล กรุณาวางข้อความตารางเรียน'}, status=400)

    api_key = os.environ.get('OPENROUTER_API_KEY', '')
    if not api_key:
        return JsonResponse({'error': 'OPENROUTER_API_KEY ยังไม่ได้ตั้งค่าใน .env'}, status=500)

    prompt = f"""You are a schedule parser for a Thai university timetable system.

Schedule type: "{sched_type}" (study=student schedule, teach=teacher schedule, work=work schedule)

Parse the text below and extract ALL schedule entries. Return a JSON array where each object has:
- subject: string  (course code only, e.g. "ENG112" or "HMM318" — just the code, no extra text)
- credit: number or null  (integer credit hours, e.g. 3 from "Credit 3" or "Cr.3"; null if not present)
- section: string  (section number as string, e.g. "001" from "Lec 001" or "Lab 001"; "" if not present)
- day: number      (0=Sunday 1=Monday 2=Tuesday 3=Wednesday 4=Thursday 5=Friday 6=Saturday)
- start: string    (24-hr "HH:MM", e.g. "09:00")
- end: string      (24-hr "HH:MM", e.g. "11:30")
- location: string (building + room, concise)
- entry_type: "theory" or "practice"  (Lec/lecture/ทฤษฎี → "theory"; Lab/ปฏิบัติ → "practice")

Day codes in source: M=1 T=2 W=3 H=4 F=5 S=6 U=0
Time format in source: HHMM-HHMM  →  e.g. 0900-1130 means start=09:00 end=11:30
Credit format: "Credit 3", "Cr.3", "Cr 3", "(3)" — extract the integer only
Section format: "Lec 001", "Lab 002", "Sec.001", "กลุ่ม 001" — extract the number string only

Rules:
- SKIP rows with "ไม่ระบุห้องเรียน" or rows that have no day/time
- If a course has lecture + lab each with their own day/time, create TWO separate entries (each keeps the same credit value)
- Output ONLY the raw JSON array — no markdown, no explanation

Text:
{raw_text}"""

    # ดึง free models แบบ dynamic — อัปเดตอัตโนมัติตาม OpenRouter
    # NOTE: free account = 50 req/day รวมทุก model, เติม $10 credit → 1000 req/day
    free_models = _get_free_models(api_key)
    if not free_models:
        # fallback hardcode เผื่อ API models endpoint ล่ม
        free_models = [
            'deepseek/deepseek-chat-v3-0324:free',
            'meta-llama/llama-4-maverick:free',
            'qwen/qwen3-235b-a22b:free',
            'google/gemma-3-27b-it:free',
        ]

    last_error = None
    text = None

    for model in free_models:
        try:
            resp = requests.post(
                'https://openrouter.ai/api/v1/chat/completions',
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                },
                json={
                    'model': model,
                    'messages': [{'role': 'user', 'content': prompt}],
                    'temperature': 0,
                    'max_tokens': 2048,
                },
                timeout=30,
            )
            # 429 = rate-limit, 404 = model ไม่มีแล้ว → ลอง model ถัดไป
            if resp.status_code in (429, 404):
                last_error = f'{model} → HTTP {resp.status_code}'
                continue
            resp.raise_for_status()
            msg = resp.json()['choices'][0]['message']
            # reasoning models อาจส่ง content=None → ดึงจาก field อื่น
            raw_content = msg.get('content') or msg.get('reasoning_content') or ''
            if not raw_content:
                last_error = f'{model} → empty content'
                continue
            text = raw_content.strip()
            break
        except requests.RequestException as e:
            return JsonResponse({'error': f'ติดต่อ OpenRouter ไม่ได้: {str(e)}'}, status=502)

    if text is None:
        return JsonResponse(
            {'error': f'ไม่สามารถเรียก AI ได้ในขณะนี้ กรุณาลองใหม่อีกครั้ง ({last_error})'},
            status=429,
        )

    try:
        # ลบ markdown fence เผื่อ AI ใส่มา
        if text.startswith('```'):
            text = '\n'.join(
                l for l in text.splitlines()
                if not l.strip().startswith('```')
            ).strip()

        entries = json.loads(text)
        if not isinstance(entries, list):
            raise ValueError('Response is not a JSON array')

        return JsonResponse({'entries': entries})

    except json.JSONDecodeError:
        return JsonResponse({'error': 'AI ตอบกลับในรูปแบบที่ไม่ถูกต้อง กรุณาลองใหม่'}, status=500)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
