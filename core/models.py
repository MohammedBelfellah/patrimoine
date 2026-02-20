from django.db import models


class Placeholder(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "_placeholder"
