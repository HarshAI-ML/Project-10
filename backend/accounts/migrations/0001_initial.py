# Generated migration for TelegramOTP model

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='TelegramOTP',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('telegram_user_id', models.CharField(blank=True, max_length=20, null=True)),
                ('telegram_username', models.CharField(blank=True, max_length=255, null=True)),
                ('otp_code', models.CharField(max_length=6)),
                ('ref_id', models.CharField(max_length=50, unique=True)),
                ('purpose', models.CharField(choices=[('registration', 'User Registration'), ('forgot_password', 'Forgot Password'), ('reset_password', 'Reset Password')], max_length=20)),
                ('email', models.EmailField(blank=True, max_length=254, null=True)),
                ('is_verified', models.BooleanField(default=False)),
                ('expires_at', models.DateTimeField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('verified_at', models.DateTimeField(blank=True, null=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='telegramotp',
            index=models.Index(fields=['ref_id'], name='accounts_tel_ref_id_xxxxxx_idx'),
        ),
        migrations.AddIndex(
            model_name='telegramotp',
            index=models.Index(fields=['telegram_user_id'], name='accounts_tel_telegr_xxxxxx_idx'),
        ),
        migrations.AddIndex(
            model_name='telegramotp',
            index=models.Index(fields=['expires_at'], name='accounts_tel_expires_xxxxxx_idx'),
        ),
    ]
