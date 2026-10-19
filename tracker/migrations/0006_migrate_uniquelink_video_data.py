from django.db import migrations


def copy_uniquelink_videos(apps, schema_editor):
    UniqueLink = apps.get_model('tracker', 'UniqueLink')
    Video = apps.get_model('tracker', 'Video')
    for link in UniqueLink.objects.all():
        if link.video:
            file_str = str(link.video)
            file_name = file_str.split('/')[-1]
            owner_name = link.user.name if link.user else "User"
            video_obj = Video.objects.create(
                title=f"{owner_name} - {file_name}",
                file=link.video,
                owner=link.user,
                is_active=True,
                is_default=False,
            )
            link.video_new = video_obj
            link.save(update_fields=['video_new'])


def reverse_copy_uniquelink_videos(apps, schema_editor):
    UniqueLink = apps.get_model('tracker', 'UniqueLink')
    for link in UniqueLink.objects.all():
        if link.video_new and link.video_new.file:
            link.video = link.video_new.file
            link.save(update_fields=['video'])


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0005_video_notification_poststat_and_more'),
    ]

    operations = [
        migrations.RunPython(copy_uniquelink_videos, reverse_code=reverse_copy_uniquelink_videos),
    ]
