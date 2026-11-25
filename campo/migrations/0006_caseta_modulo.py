from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("campo", "0005_caseta")]

    operations = [
        migrations.AddField(
            model_name="caseta",
            name="modulo",
            field=models.CharField(
                blank=True,
                choices=[("rosita", "Rosita"), ("arana", "Arana"), ("raymi", "Raymi"), ("breeze", "Breeze")],
                max_length=10,
            ),
        ),
    ]
