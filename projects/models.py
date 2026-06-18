import random
import string
from datetime import timedelta

from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone


class UserProfile(models.Model):
    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
        ('lgbtq_plus', 'LGBTQ+'),
        ('prefer_not_to_say', 'Prefer not to say'),
    ]
    
    user   = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    display_name = models.CharField(max_length=150, unique=True, null=True, blank=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    bio    = models.TextField(blank=True, default='')
    gender = models.CharField(max_length=20, choices=GENDER_CHOICES, null=True, blank=True)
    name = models.CharField(max_length=100, blank=True, default='')
    surname = models.CharField(max_length=100, blank=True, default='')

    def __str__(self):
        return f"{self.user.username}'s profile"

    def get_avatar_url(self):
        return self.avatar.url if self.avatar else None

    def get_display_name(self):
        return self.display_name or self.user.username
    
    def get_gender_icon(self):
        gender_icons = {
            'male': 'user',
            'female': 'user-round', 
            'lgbtq_plus': 'users',
            'prefer_not_to_say': 'eye-off',
        }
        return gender_icons.get(self.gender, 'help-circle')


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    # Don't call profile.save() here - it would overwrite data saved in the view
    if not hasattr(instance, 'profile'):
        UserProfile.objects.create(user=instance)


class PasswordResetOTP(models.Model):
    """6-digit OTP for password reset, expires in 10 minutes"""
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='otp_codes')
    code       = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used    = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} — {self.code}"

    def is_valid(self):
        expiry = self.created_at + timedelta(minutes=10)
        return not self.is_used and timezone.now() < expiry

    @classmethod
    def generate_for_user(cls, user):
        cls.objects.filter(user=user, is_used=False).update(is_used=True)
        code = ''.join(random.choices(string.digits, k=6))
        return cls.objects.create(user=user, code=code)


class Category(models.Model):
    name  = models.CharField(max_length=100)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='categories')

    class Meta:
        ordering = ['name']
        unique_together = ['name', 'owner']

    def __str__(self):
        return self.name


class Project(models.Model):
    STATUS_CHOICES = [
        ('active',    'Active'),
        ('on_hold',   'On Hold'),
        ('completed', 'Completed'),
    ]

    name        = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    owner       = models.ForeignKey(User, on_delete=models.CASCADE)
    category    = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    deadline    = models.DateField(null=True, blank=True)
    status      = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class ProjectMember(models.Model):
    ROLE_CHOICES = [
        ('viewer', 'Viewer'),   # view only
        ('member', 'Member'),   # can work on tasks
        ('admin',  'Admin'),    # can manage project
    ]

    project    = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='members')
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='project_memberships')
    role       = models.CharField(max_length=10, choices=ROLE_CHOICES, default='member')
    invited_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='sent_invites')
    joined_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['project', 'user']
        ordering = ['joined_at']

    def __str__(self):
        return f"{self.user.username} — {self.project.name} ({self.role})"


class ActivityLog(models.Model):
    ACTION_CHOICES = [
        ('create_task',   'Create Task'),
        ('update_task',   'Update Task'),
        ('delete_task',   'Delete Task'),
        ('change_status', 'Change Status'),
        ('assign_user',   'Assign User'),
    ]
    
    user      = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activities')
    action    = models.CharField(max_length=20, choices=ACTION_CHOICES)
    target    = models.CharField(max_length=200)  # task/project title
    project   = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='activities')
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.user.username} - {self.get_action_display()} - {self.target}"


class Notification(models.Model):
    TYPE_CHOICES = [
        ('task_moved', 'Task Moved'),
        ('due_soon',   'Due Soon'),
        ('invite',     'Invite'),
    ]
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    message    = models.TextField()
    notif_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    is_read    = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} — {self.message}"


def attachment_upload_path(instance, filename):
    """
    Upload path: attachments/project_<id>/<file_type>/<filename>
    
    file_type must be set before Django calls upload_to (see FileAttachment.save())
    """
    project_id = instance.project_id or "unknown"
    file_type  = instance.file_type  or "other"
    return f"attachments/project_{project_id}/{file_type}/{filename}"


class FileAttachment(models.Model):
    """File attachments for tasks and comments"""
    FILE_TYPES = [
        ('document', 'Document'),
        ('image', 'Image'),
        ('video', 'Video'),
        ('audio', 'Audio'),
        ('archive', 'Archive'),
        ('other', 'Other'),
    ]
    
    file = models.FileField(upload_to=attachment_upload_path)
    filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=20, choices=FILE_TYPES, default='other')
    file_size = models.BigIntegerField(help_text="File size in bytes")
    
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='uploaded_files')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='files')
    task = models.ForeignKey('tasks.Task', on_delete=models.CASCADE, related_name='files', null=True, blank=True)
    comment = models.ForeignKey('tasks.Comment', on_delete=models.CASCADE, related_name='files', null=True, blank=True)
    
    can_view = models.ManyToManyField(User, related_name='viewable_files', blank=True, help_text="Users who can view this file")
    can_download = models.ManyToManyField(User, related_name='downloadable_files', blank=True, help_text="Users who can download this file")
    can_edit = models.ManyToManyField(User, related_name='editable_files', blank=True, help_text="Users who can edit this file")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', 'created_at']),
            models.Index(fields=['task', 'created_at']),
            models.Index(fields=['uploaded_by', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.filename} ({self.project.name})"
    
    def save(self, *args, **kwargs):
        if self.file and not self.filename:
            self.filename = self.file.name.split("/")[-1]
        if self.file and not self.file_size:
            self.file_size = self.file.size

        # Detect file_type before super().save() - upload_to depends on it
        # Bug fix: added parentheses to prevent re-detection when file_type == 'other'
        if self.file and (not self.file_type or self.file_type == "other"):
            self.file_type = FileAttachment._detect_file_type(self.file.name)

        super().save(*args, **kwargs)

    @staticmethod
    def _detect_file_type(filename: str) -> str:
        """
        Detect file type from extension.
        Static method to allow calling before instance creation.
        """
        if not filename:
            return "other"

        ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""

        if ext in {"jpg", "jpeg", "png", "gif", "bmp", "webp", "svg"}:
            return "image"
        if ext in {"pdf", "doc", "docx", "txt", "rtf", "odt", "xls", "xlsx", "ppt", "pptx"}:
            return "document"
        if ext in {"mp4", "avi", "mov", "wmv", "flv", "webm", "mkv"}:
            return "video"
        if ext in {"mp3", "wav", "flac", "aac", "ogg", "wma"}:
            return "audio"
        if ext in {"zip", "rar", "7z", "tar", "gz", "bz2"}:
            return "archive"
        return "other"
    
    def get_file_size_display(self):
        """Return human-readable file size"""
        size = self.file_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
    
    def can_user_view(self, user):
        """Check if user can view this file"""
        # Owner and project owner can always view
        if user == self.uploaded_by or user == self.project.owner:
            return True
        
        # Users with explicit view permission
        if user in self.can_view.all():
            return True
        
        # Project members (if not restricted)
        if ProjectMember.objects.filter(project=self.project, user=user).exists():
            return True
        
        return False
    
    def can_user_download(self, user):
        """Check if user can download this file"""
        # Owner and project owner can always download
        if user == self.uploaded_by or user == self.project.owner:
            return True
        
        # Users with explicit download permission
        if user in self.can_download.all():
            return True
        
        # Default: if can view, can download
        return self.can_user_view(user)
    
    def can_user_edit(self, user):
        """Check if user can edit this file"""
        # Owner and project owner can always edit
        if user == self.uploaded_by or user == self.project.owner:
            return True
        
        # Users with explicit edit permission
        if user in self.can_edit.all():
            return True
        
        return False
