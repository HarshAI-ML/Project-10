from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import random
import string


class TelegramOTP(models.Model):
    """Store Telegram OTP sessions for authentication flows."""
    
    PURPOSE_CHOICES = [
        ('registration', 'User Registration'),
        ('forgot_password', 'Forgot Password'),
        ('reset_password', 'Reset Password'),
    ]
    
    # Telegram data
    telegram_user_id = models.CharField(max_length=20, null=True, blank=True)
    telegram_username = models.CharField(max_length=255, null=True, blank=True)
    
    # OTP data
    otp_code = models.CharField(max_length=6)
    ref_id = models.CharField(max_length=50, unique=True)  # Reference ID for linking to QR
    
    # Metadata
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES)
    email = models.EmailField(null=True, blank=True)  # For forgot password flow
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    
    # Status tracking
    is_verified = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['ref_id']),
            models.Index(fields=['telegram_user_id']),
            models.Index(fields=['expires_at']),
        ]
    
    def __str__(self):
        return f"{self.purpose} - {self.email or self.telegram_user_id}"
    
    @staticmethod
    def generate_otp():
        """Generate a 6-digit OTP code."""
        return ''.join(random.choices(string.digits, k=6))
    
    @staticmethod
    def generate_ref_id():
        """Generate a unique reference ID."""
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
    
    @staticmethod
    def generate_expiry(minutes=10):
        """Generate expiry time (default 10 minutes)."""
        return timezone.now() + timezone.timedelta(minutes=minutes)
    
    def is_expired(self):
        """Check if OTP has expired."""
        return timezone.now() > self.expires_at
    
    def is_valid(self, otp_code):
        """Validate OTP code and expiry."""
        return not self.is_expired() and self.otp_code == otp_code and not self.is_verified
    
    def mark_verified(self):
        """Mark OTP as verified."""
        self.is_verified = True
        self.verified_at = timezone.now()
        self.save()
