from django.apps import apps
from django.core.management.base import BaseCommand, CommandParser
from django.db.models.fields.related import ForeignKey, ManyToManyField, OneToOneField


class Command(BaseCommand):
    help = "Dumps Django model schema into textual representation"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--output",
            "-o",
            type=str,
            help="Output file path. If not specified, writes to stdout",
        )

    def handle(self, *args, **options):
        output_lines = []

        for model in apps.get_models():
            output_lines.append(f"Table: {model._meta.db_table}")
            for field in model._meta.get_fields():
                # Skip reverse TenantForeignKey fields
                if field.auto_created and not field.concrete:
                    continue

                if field.is_relation and isinstance(field, (ForeignKey, OneToOneField)):

                    related_table = field.related_model._meta.db_table
                    line = f"- {field.name} ({field.get_internal_type()}, foreign key to {related_table}.{field.target_field.column})"
                elif field.is_relation and isinstance(field, ManyToManyField):
                    related_table = field.related_model._meta.db_table
                    line = f"- {field.name} (ManyToMany relationship with {related_table})"
                elif hasattr(field, "get_internal_type"):
                    line = f"- {field.name} ({field.get_internal_type()})"
                else:
                    continue
                output_lines.append(line)
            output_lines.append("")

        # Write output either to file or stdout
        if options["output"]:
            with open(options["output"], "w") as f:
                f.write("\n".join(output_lines))
            self.stdout.write(self.style.SUCCESS(f"Schema dumped to {options['output']}"))
        else:
            self.stdout.write("\n".join(output_lines))
