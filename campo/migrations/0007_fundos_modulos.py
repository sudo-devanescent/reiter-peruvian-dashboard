from django.db import migrations, models
import django.db.models.deletion


MODULOS = {"rosita": "Rosita", "arana": "Arana", "raymi": "Raymi", "breeze": "Breeze"}


def trasladar_modulos(apps, schema_editor):
    fundo = apps.get_model("campo", "Fundo")
    modulo = apps.get_model("campo", "ModuloMuestreo")
    caseta = apps.get_model("campo", "Caseta")
    db = schema_editor.connection.alias
    fundo.objects.using(db).bulk_create([fundo(nombre="Achirana"), fundo(nombre="Papito")])
    for codigo, nombre in MODULOS.items():
        registro = modulo.objects.using(db).create(nombre=nombre)
        caseta.objects.using(db).filter(modulo_anterior=codigo).update(modulo=registro)


def restaurar_modulos(apps, schema_editor):
    caseta = apps.get_model("campo", "Caseta")
    db = schema_editor.connection.alias
    for codigo, nombre in MODULOS.items():
        caseta.objects.using(db).filter(modulo__nombre=nombre).update(modulo_anterior=codigo)


class Migration(migrations.Migration):
    dependencies = [("campo", "0006_caseta_modulo")]

    operations = [
        migrations.CreateModel(
            name="Fundo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=80, unique=True)),
            ],
            options={"ordering": ["nombre"]},
        ),
        migrations.CreateModel(
            name="ModuloMuestreo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=80, unique=True)),
                ("fundo", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                            related_name="modulos", to="campo.fundo")),
            ],
            options={"ordering": ["nombre"]},
        ),
        migrations.RenameField(model_name="caseta", old_name="modulo", new_name="modulo_anterior"),
        migrations.AddField(
            model_name="caseta",
            name="modulo",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                    related_name="casetas", to="campo.modulomuestreo"),
        ),
        migrations.RunPython(trasladar_modulos, restaurar_modulos),
        migrations.RemoveField(model_name="caseta", name="modulo_anterior"),
    ]
