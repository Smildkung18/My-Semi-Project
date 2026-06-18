from django.urls import path
from . import views

app_name = 'schedules'

urlpatterns = [
    # Page
    path('',                                     views.schedule_page,        name='page'),

    # REST-ish API
    path('api/schedules/',                       views.api_schedules,        name='api_schedules'),
    path('api/schedules/<int:pk>/',              views.api_schedule_detail,  name='api_schedule_detail'),
    path('api/schedules/<int:schedule_pk>/entries/', views.api_entries,      name='api_entries'),
    path('api/entries/<int:pk>/',                views.api_entry_detail,     name='api_entry_detail'),
    path("api/ai-parse/",                        views.ai_parse_schedule,    name="ai_parse_schedule"),
    path('api/notify/',                          views.api_schedule_notify,  name='api_schedule_notify'),
    path('api/calendar/events/',                 views.api_calendar_events,        name='api_calendar_events'),
    path('api/calendar/events/<int:pk>/',        views.api_calendar_event_detail,  name='api_calendar_event_detail'),
    path('api/calendar/notify/',                 views.api_calendar_notify,        name='api_calendar_notify'),
]
