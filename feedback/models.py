import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


def public_token():
    return secrets.token_urlsafe(16)


class Project(models.Model):
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    leads = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="led_projects")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class FeedbackCycle(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="cycles")
    opens_at = models.DateTimeField()
    closes_at = models.DateTimeField()
    token = models.CharField(max_length=32, unique=True, default=public_token, editable=False)

    class Meta:
        ordering = ["-opens_at"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(closes_at__gt=models.F("opens_at")),
                name="cycle_closes_after_opening",
            ),
        ]

    def clean(self):
        super().clean()
        if self.opens_at and self.closes_at and self.closes_at <= self.opens_at:
            raise ValidationError({"closes_at": "Closing time must be after opening time."})

    @property
    def is_open(self):
        now = timezone.now()
        return self.opens_at <= now <= self.closes_at

    def __str__(self):
        return f"{self.project} · {self.opens_at:%Y-%m-%d}"


class Response(models.Model):
    cycle = models.ForeignKey(FeedbackCycle, on_delete=models.CASCADE, related_name="responses")
    score = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True)
    network_hash = models.CharField(max_length=64)
    device_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["cycle", "network_hash"], name="one_network_per_cycle"),
            models.UniqueConstraint(fields=["cycle", "device_hash"], name="one_device_per_cycle"),
        ]
        ordering = ["-created_at"]

# Create your models here.
