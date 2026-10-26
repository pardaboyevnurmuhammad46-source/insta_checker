import secrets
from django.db import migrations, models
import tracker.models

ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def generate_migration_code():
    return "".join(secrets.choice(ALPHABET) for _ in range(6))


def populate_unique_link_codes(apps, schema_editor):
    UniqueLink = apps.get_model('tracker', 'UniqueLink')
    existing_codes = set(
        UniqueLink.objects.exclude(code__isnull=True).exclude(code='').values_list('code', flat=True)
    )

    for link in UniqueLink.objects.filter(models.Q(code__isnull=True) | models.Q(code='')):
        while True:
            candidate = generate_migration_code()
            if candidate not in existing_codes:
                existing_codes.add(candidate)
                link.code = candidate
                link.save(update_fields=['code'])
                break


def cleanup_post_ig_media_id(apps, schema_editor):
    Post = apps.get_model('tracker', 'Post')
    Post.objects.filter(ig_media_id='').update(ig_media_id=None)


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0012_video_processing_error_video_status'),
    ]

    operations = [
        # 1. UniqueLink ga code ustunini qo'shish (boshida null=True)
        migrations.AddField(
            model_name='uniquelink',
            name='code',
            field=models.CharField(blank=True, max_length=6, null=True),
        ),
        # 2. Mavjud linklarni 6 xonali unikal kod bilan to'ldirish
        migrations.RunPython(
            populate_unique_link_codes,
            reverse_code=migrations.RunPython.noop,
        ),
        # 3. Post.ig_media_id dagi bo'sh satrlarni None ga aylantirish
        migrations.RunPython(
            cleanup_post_ig_media_id,
            reverse_code=migrations.RunPython.noop,
        ),
        # 4. UniqueLink.code ustunini unique=True va default bilan mustahkamlash
        migrations.AlterField(
            model_name='uniquelink',
            name='code',
            field=models.CharField(
                db_index=True,
                default=tracker.models.generate_unique_link_code,
                help_text='0/O/1/I belgilarisiz 6 xonali unikal kod',
                max_length=6,
                unique=True,
            ),
        ),
        # 5. Post modeliga yangi maydonlarni qo'shish va yangilash
        migrations.AddField(
            model_name='post',
            name='source',
            field=models.CharField(choices=[('site', 'Site'), ('self', 'Self')], default='site', max_length=10),
        ),
        migrations.AddField(
            model_name='post',
            name='thumbnail_url',
            field=models.URLField(blank=True, max_length=1000, null=True),
        ),
        migrations.AddField(
            model_name='post',
            name='last_synced_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='post',
            name='status',
            field=models.CharField(
                choices=[
                    ('verified', 'Verified'),
                    ('rejected', 'Rejected'),
                    ('revoked', 'Revoked'),
                    ('queued', 'Queued'),
                    ('publishing', 'Publishing'),
                    ('published', 'Published'),
                    ('deleted', 'Deleted'),
                    ('failed', 'Failed'),
                ],
                default='queued',
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='post',
            name='ig_media_id',
            field=models.CharField(blank=True, max_length=100, null=True, unique=True),
        ),
    ]
