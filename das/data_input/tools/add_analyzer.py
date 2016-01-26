import django
django.setup()
import observations.models
import analyzers.models
import analyzers.models

sub = observations.models.Subject.objects.get(name='Russel')


an = analyzers.models.ImmobilityAnalyzer(radius=200.0)

an.save()

sub_an = analyzers.models.SubjectAnalyzer(content_object=an, subject=sub)

sub_an.save()






