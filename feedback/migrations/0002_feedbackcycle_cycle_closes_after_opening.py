from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("feedback", "0001_initial"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="feedbackcycle",
            constraint=models.CheckConstraint(
                check=models.Q(("closes_at__gt", models.F("opens_at"))),
                name="cycle_closes_after_opening",
            ),
        ),
    ]
