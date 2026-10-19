import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0006_migrate_uniquelink_video_data'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='uniquelink',
            name='video',
        ),
        migrations.RenameField(
            model_name='uniquelink',
            old_name='video_new',
            new_name='video',
        ),
        migrations.AlterField(
            model_name='uniquelink',
            name='video',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='links',
                to='tracker.video',
            ),
        ),
    ]
