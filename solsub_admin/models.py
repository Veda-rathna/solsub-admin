# solsub_admin/models.py
from django.db import models
from django.utils.crypto import get_random_string
import secrets

class Cluster(models.Model):
    cluster_name = models.CharField(max_length=255, unique=True)
    cluster_id = models.CharField(max_length=100, unique=True)
    cluster_price = models.DecimalField(max_digits=10, decimal_places=2)
    timeline_days = models.IntegerField(default=30)
    api_key = models.CharField(max_length=32, unique=True, blank=True)
    trial_period = models.IntegerField(default=0)

    def save(self, *args, **kwargs):
        if not self.api_key:
            while True:
                key = secrets.token_hex(16)
                if not Cluster.objects.filter(api_key=key).exists():
                    self.api_key = key
                    break
        super().save(*args, **kwargs)

    def __str__(self):
        return self.cluster_name