from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Prize, Notification

@receiver(post_save, sender=Prize)
def create_prize_notification(sender, instance, created, **kwargs):
    if created:
        Notification.objects.create(
            user=instance.post.link.user,
            kind='prize',
            message=f"Tabriklaymiz! Sizning Instagram videongiz {instance.milestone} ta ko'rishlar soniga yetdi!",
            related_prize=instance
        )
