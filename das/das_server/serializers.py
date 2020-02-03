from rest_framework import serializers

from das_server.models import UserAgreement, EULA


class AcceptEulaSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserAgreement
        fields = ["user", "eula", "accepted",]


class EulaSerializer(serializers.ModelSerializer):
    class Meta:
        model = EULA
        fields = ["version_number", "url"]
