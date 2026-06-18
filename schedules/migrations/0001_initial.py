from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Schedule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('type', models.CharField(
                    choices=[('work', 'ตารางงาน'), ('study', 'ตารางเรียน'), ('teach', 'ตารางสอน')],
                    default='study', max_length=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('order', models.PositiveSmallIntegerField(default=0)),
                ('owner', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='schedules',
                    to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['order', 'created_at']},
        ),
        migrations.CreateModel(
            name='ScheduleEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('subject', models.CharField(max_length=200)),
                ('day', models.PositiveSmallIntegerField(
                    choices=[(0, 'อาทิตย์'), (1, 'จันทร์'), (2, 'อังคาร'),
                             (3, 'พุธ'), (4, 'พฤหัสบดี'), (5, 'ศุกร์'), (6, 'เสาร์')])),
                ('start_time', models.TimeField()),
                ('end_time', models.TimeField()),
                ('location', models.CharField(blank=True, max_length=100)),
                ('entry_type', models.CharField(
                    blank=True, max_length=10, null=True,
                    choices=[('theory', 'ทฤษฎี'), ('practice', 'ปฏิบัติ')],
                    help_text='ใช้เฉพาะตารางเรียน/ตารางสอน')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('schedule', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='entries',
                    to='schedules.schedule')),
            ],
            options={'ordering': ['day', 'start_time']},
        ),
    ]
