import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('tracker', '0004_alter_datadeletionrequest_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='instagramuser',
            name='user',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='instagram_user',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.CreateModel(
            name='Video',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255)),
                ('file', models.FileField(upload_to='videos/')),
                ('is_default', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('is_active', models.BooleanField(default=True)),
                ('owner', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='videos',
                    to='tracker.instagramuser',
                )),
            ],
            options={
                'ordering': ['-created_at'],
                'constraints': [
                    models.UniqueConstraint(
                        condition=models.Q(is_default=True),
                        fields=['is_default'],
                        name='unique_default_video',
                    )
                ],
            },
        ),
        migrations.AddField(
            model_name='uniquelink',
            name='video_new',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='links_temp',
                to='tracker.video',
            ),
        ),
        migrations.AddField(
            model_name='post',
            name='deleted_detected_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterModelOptions(
            name='post',
            options={'ordering': ['-id']},
        ),
        migrations.AddIndex(
            model_name='post',
            index=models.Index(fields=['status', 'next_check_at'], name='tracker_pos_status_31caec_idx'),
        ),
        migrations.AddIndex(
            model_name='post',
            index=models.Index(fields=['link', 'posted_at'], name='tracker_pos_link_id_9fa515_idx'),
        ),
        migrations.CreateModel(
            name='PostStat',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('views', models.PositiveIntegerField(default=0)),
                ('likes', models.PositiveIntegerField(default=0)),
                ('comments_count', models.PositiveIntegerField(default=0)),
                ('checked_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('post', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='stats',
                    to='tracker.post',
                )),
            ],
            options={
                'ordering': ['-checked_at'],
                'indexes': [
                    models.Index(fields=['post', '-checked_at'], name='tracker_pos_post_id_658ae5_idx')
                ],
            },
        ),
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(
                    choices=[('prize', 'Prize'), ('system', 'System')],
                    default='system',
                    max_length=20,
                )),
                ('message', models.TextField()),
                ('is_read', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('related_prize', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='notifications',
                    to='tracker.prize',
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='notifications',
                    to='tracker.instagramuser',
                )),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='prize',
            constraint=models.UniqueConstraint(fields=['post', 'milestone'], name='unique_post_milestone'),
        ),
    ]
