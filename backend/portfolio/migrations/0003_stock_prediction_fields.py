from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("portfolio", "0002_stock_portfolio_delete_portfoliostock"),
    ]

    operations = [
        migrations.AddField(
            model_name="stock",
            name="predicted_price_30d",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="stock",
            name="expected_change_pct",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="stock",
            name="direction_signal",
            field=models.CharField(blank=True, default="", max_length=30),
        ),
        migrations.AddField(
            model_name="stock",
            name="model_confidence_r2",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="stock",
            name="prediction_status",
            field=models.CharField(default="unavailable", max_length=30),
        ),
        migrations.AddField(
            model_name="stock",
            name="recommended_action",
            field=models.CharField(blank=True, default="", max_length=50),
        ),
        migrations.AddField(
            model_name="stock",
            name="prediction_updated_at",
            field=models.DateTimeField(blank=True, default=django.utils.timezone.now, null=True),
        ),
    ]
