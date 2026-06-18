from django.db import models
from django.contrib.auth.models import User


class Schedule(models.Model):
    TYPE_WORK  = 'work'
    TYPE_STUDY = 'study'
    TYPE_TEACH = 'teach'
    TYPE_CHOICES = [
        (TYPE_WORK,  'ตารางงาน'),
        (TYPE_STUDY, 'ตารางเรียน'),
        (TYPE_TEACH, 'ตารางสอน'),
    ]

    owner      = models.ForeignKey(User, on_delete=models.CASCADE, related_name='schedules')
    name       = models.CharField(max_length=120)
    type       = models.CharField(max_length=10, choices=TYPE_CHOICES, default=TYPE_STUDY)
    created_at = models.DateTimeField(auto_now_add=True)
    order      = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', 'created_at']

    def __str__(self):
        return f'{self.owner.username} – {self.name}'

    def as_dict(self):
        return {
            'id':      self.pk,
            'name':    self.name,
            'type':    self.type,
            'entries': [e.as_dict() for e in self.entries.all()],
        }


class ScheduleEntry(models.Model):
    ENTRY_THEORY   = 'theory'
    ENTRY_PRACTICE = 'practice'
    ENTRY_TYPE_CHOICES = [
        (ENTRY_THEORY,   'ทฤษฎี'),
        (ENTRY_PRACTICE, 'ปฏิบัติ'),
    ]
    DAY_CHOICES = [
        (0, 'อาทิตย์'),
        (1, 'จันทร์'),
        (2, 'อังคาร'),
        (3, 'พุธ'),
        (4, 'พฤหัสบดี'),
        (5, 'ศุกร์'),
        (6, 'เสาร์'),
    ]

    schedule   = models.ForeignKey(Schedule, on_delete=models.CASCADE, related_name='entries')
    subject    = models.CharField(max_length=200)
    day        = models.PositiveSmallIntegerField(choices=DAY_CHOICES)
    start_time = models.TimeField()
    end_time   = models.TimeField()
    location   = models.CharField(max_length=100, blank=True)
    entry_type = models.CharField(
        max_length=10,
        choices=ENTRY_TYPE_CHOICES,
        blank=True,
        null=True,
        help_text='ใช้เฉพาะตารางเรียน/ตารางสอน',
    )
    section    = models.CharField(
        max_length=20,
        blank=True,
        default='',
        help_text='เซ็คชั่น เช่น 001, 002',
    )
    credit     = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text='หน่วยกิต (0-9)',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['day', 'start_time']

    def __str__(self):
        return f'{self.subject} ({self.get_day_display()}) {self.start_time}–{self.end_time}'

    def as_dict(self):
        return {
            'id':         self.pk,
            'subject':    self.subject,
            'day':        self.day,
            'start': self.start_time.strftime('%H:%M') if hasattr(self.start_time, 'strftime') else str(self.start_time)[:5],
            'end':   self.end_time.strftime('%H:%M')   if hasattr(self.end_time,   'strftime') else str(self.end_time)[:5],
            'location':   self.location,
            'entry_type': self.entry_type or '',
            'section':    self.section or '',
            'credit':     self.credit,
        }


# ── Calendar Events (แยกจาก ScheduleEntry) ───────────────────────────────
class CalendarEvent(models.Model):
    COLOR_CHOICES = [
        ('indigo', 'สีม่วงน้ำเงิน'),
        ('green',  'สีเขียว'),
        ('rose',   'สีชมพู'),
        ('amber',  'สีเหลือง'),
        ('sky',    'สีฟ้า'),
        ('orange', 'สีส้ม'),
    ]

    owner         = models.ForeignKey(User, on_delete=models.CASCADE, related_name='calendar_events')
    schedule      = models.ForeignKey(Schedule, on_delete=models.CASCADE, related_name='calendar_events', null=True, blank=True)
    title         = models.CharField(max_length=200)
    detail        = models.TextField(blank=True, default='')
    event_date    = models.DateField()
    start_time    = models.TimeField(null=True, blank=True)
    end_time      = models.TimeField(null=True, blank=True)
    location      = models.CharField(max_length=100, blank=True, default='')
    color         = models.CharField(max_length=10, choices=COLOR_CHOICES, default='indigo')
    remind_before = models.PositiveSmallIntegerField(
        default=15,
        help_text='แจ้งเตือนก่อน (นาที): 0=ไม่แจ้ง',
    )
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['event_date', 'start_time']

    def __str__(self):
        return f'{self.title} ({self.event_date})'

    def as_dict(self):
        from datetime import date as date_type, time as time_type, datetime as dt_type

        event_date = self.event_date
        if isinstance(event_date, str):
            event_date = dt_type.strptime(event_date, '%Y-%m-%d').date()

        def _fmt_time(t):
            if not t:
                return ''
            if isinstance(t, str):
                return t[:5]  # "HH:MM:SS" → "HH:MM"
            return t.strftime('%H:%M')

        return {
            'id':            self.pk,
            'title':         self.title,
            'detail':        self.detail,
            'date':          event_date.strftime('%Y-%m-%d'),
            'start':         _fmt_time(self.start_time),
            'end':           _fmt_time(self.end_time),
            'location':      self.location,
            'color':         self.color,
            'remind_before': self.remind_before,
        }
