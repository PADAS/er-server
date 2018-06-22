#!/bin/sh

if [ $SEND_ALERTS == "true" ]; then
    sed -i -e "s;$.ALERTS_SLACK_CHANNEL.;$ALERTS_SLACK_CHANNEL;g" /config/alertmanager.yaml
    sed -i -e "s;$.ALERTS_SLACK_URL.;$ALERTS_SLACK_URL;g" /config/alertmanager.yaml
    ALERT_CONFIG=/config/alertmanager.yaml
else
    ALERT_CONFIG=/config/silentalerts.yaml
fi

/bin/alertmanager \
    -config.file=$ALERT_CONFIG \
    -storage.path=/alertmanager \
    -web.external-url=http://${ALERTMANAGER_PUBLIC_IP-"NoNginxUtilityStaticIpSet"}:9093
