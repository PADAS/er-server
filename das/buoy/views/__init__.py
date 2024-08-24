from django.http import HttpResponse


def GearView(request, id):
    return HttpResponse("GearView: " + str(id))


def GearsView(request):
    return HttpResponse("GearsView")
