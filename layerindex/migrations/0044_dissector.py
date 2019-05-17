from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('layerindex', '0043_layerbranch_set_local_path'),
    ]

    database_operations = [
        migrations.AlterModelTable('ImageComparison', 'dissector_imagecomparison'),
        migrations.AlterModelTable('ImageComparisonRecipe', 'dissector_imagecomparisonrecipe'),
        migrations.AlterModelTable('VersionComparison', 'dissector_versioncomparison'),
        migrations.AlterModelTable('VersionComparisonDifference', 'dissector_versioncomparisondifference'),
        migrations.AlterModelTable('VersionComparisonFileDiff', 'dissector_versioncomparisonfilediff'),
    ]

    state_operations = [
        migrations.DeleteModel('ImageComparison'),
        migrations.DeleteModel('ImageComparisonRecipe'),
        migrations.DeleteModel('VersionComparison'),
        migrations.DeleteModel('VersionComparisonDifference'),
        migrations.DeleteModel('VersionComparisonFileDiff'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=database_operations,
            state_operations=state_operations)
    ]
