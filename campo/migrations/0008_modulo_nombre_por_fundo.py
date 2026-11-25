from django.db import migrations, models
from django.db.models.functions import Lower


class Migration(migrations.Migration):
    dependencies = [("campo", "0007_fundos_modulos")]

    operations = [
        migrations.AlterField(
            model_name="modulomuestreo", name="nombre", field=models.CharField(max_length=80),
        ),
        migrations.AlterModelOptions(name="modulomuestreo", options={"ordering": ["nombre", "pk"]}),
        migrations.AddConstraint(
            model_name="modulomuestreo",
            constraint=models.UniqueConstraint(Lower("nombre"), "fundo", name="modulo_nombre_unico_por_fundo"),
        ),
    ]
