from django.test import TestCase

import tracking.models.inreachkml as inreachkml


KML_RESULT_EMPTY = """<?xml version="1.0" encoding="utf-8"?>
<kml xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>KML Export 3/9/2019 4:25:51 PM</name>
    <Style id="style_emergency">
      <IconStyle>
        <colorMode>normal</colorMode>
        <Icon>
          <href>http://maps.google.com/mapfiles/kml/shapes/caution.png</href>
        </Icon>
      </IconStyle>
      <BalloonStyle>
        <text>&lt;table&gt;&lt;tr&gt;&lt;td&gt;Id&lt;/td&gt;&lt;td&gt; $[Id] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Time&lt;/td&gt;&lt;td&gt; $[Time] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Time UTC&lt;/td&gt;&lt;td&gt; $[Time UTC] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Name&lt;/td&gt;&lt;td&gt; $[Name] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Map Display Name&lt;/td&gt;&lt;td&gt; $[Map Display Name] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Device Type&lt;/td&gt;&lt;td&gt; $[Device Type] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;IMEI&lt;/td&gt;&lt;td&gt; $[IMEI] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Incident Id&lt;/td&gt;&lt;td&gt; $[Incident Id] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Latitude&lt;/td&gt;&lt;td&gt; $[Latitude] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Longitude&lt;/td&gt;&lt;td&gt; $[Longitude] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Elevation&lt;/td&gt;&lt;td&gt; $[Elevation] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Velocity&lt;/td&gt;&lt;td&gt; $[Velocity] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Course&lt;/td&gt;&lt;td&gt; $[Course] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Valid GPS Fix&lt;/td&gt;&lt;td&gt; $[Valid GPS Fix] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;In Emergency&lt;/td&gt;&lt;td&gt; $[In Emergency] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Text&lt;/td&gt;&lt;td&gt; $[Text] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Event&lt;/td&gt;&lt;td&gt; $[Event] &lt;/td&gt;&lt;/tr&gt;&lt;/table&gt;</text>
      </BalloonStyle>
    </Style>
  </Document>
</kml>
"""

KML_RESULT_SINGLE_POINT = """<?xml version="1.0" encoding="utf-8"?>
<kml xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>KML Export 3/9/2019 3:59:11 PM</name>
    <Style id="style_emergency">
      <IconStyle>
        <colorMode>normal</colorMode>
        <Icon>
          <href>http://maps.google.com/mapfiles/kml/shapes/caution.png</href>
        </Icon>
      </IconStyle>
      <BalloonStyle>
        <text>&lt;table&gt;&lt;tr&gt;&lt;td&gt;Id&lt;/td&gt;&lt;td&gt; $[Id] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Time&lt;/td&gt;&lt;td&gt; $[Time] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Time UTC&lt;/td&gt;&lt;td&gt; $[Time UTC] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Name&lt;/td&gt;&lt;td&gt; $[Name] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Map Display Name&lt;/td&gt;&lt;td&gt; $[Map Display Name] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Device Type&lt;/td&gt;&lt;td&gt; $[Device Type] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;IMEI&lt;/td&gt;&lt;td&gt; $[IMEI] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Incident Id&lt;/td&gt;&lt;td&gt; $[Incident Id] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Latitude&lt;/td&gt;&lt;td&gt; $[Latitude] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Longitude&lt;/td&gt;&lt;td&gt; $[Longitude] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Elevation&lt;/td&gt;&lt;td&gt; $[Elevation] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Velocity&lt;/td&gt;&lt;td&gt; $[Velocity] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Course&lt;/td&gt;&lt;td&gt; $[Course] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Valid GPS Fix&lt;/td&gt;&lt;td&gt; $[Valid GPS Fix] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;In Emergency&lt;/td&gt;&lt;td&gt; $[In Emergency] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Text&lt;/td&gt;&lt;td&gt; $[Text] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Event&lt;/td&gt;&lt;td&gt; $[Event] &lt;/td&gt;&lt;/tr&gt;&lt;/table&gt;</text>
      </BalloonStyle>
    </Style>
    <Style id="style_979267">
      <IconStyle>
        <color>ff006cff</color>
        <colorMode>normal</colorMode>
        <Icon>
          <href>http://maps.google.com/mapfiles/kml/paddle/wht-blank.png</href>
        </Icon>
      </IconStyle>
      <BalloonStyle>
        <text>&lt;table&gt;&lt;tr&gt;&lt;td&gt;Id&lt;/td&gt;&lt;td&gt; $[Id] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Time&lt;/td&gt;&lt;td&gt; $[Time] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Time UTC&lt;/td&gt;&lt;td&gt; $[Time UTC] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Name&lt;/td&gt;&lt;td&gt; $[Name] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Map Display Name&lt;/td&gt;&lt;td&gt; $[Map Display Name] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Device Type&lt;/td&gt;&lt;td&gt; $[Device Type] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;IMEI&lt;/td&gt;&lt;td&gt; $[IMEI] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Incident Id&lt;/td&gt;&lt;td&gt; $[Incident Id] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Latitude&lt;/td&gt;&lt;td&gt; $[Latitude] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Longitude&lt;/td&gt;&lt;td&gt; $[Longitude] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Elevation&lt;/td&gt;&lt;td&gt; $[Elevation] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Velocity&lt;/td&gt;&lt;td&gt; $[Velocity] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Course&lt;/td&gt;&lt;td&gt; $[Course] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Valid GPS Fix&lt;/td&gt;&lt;td&gt; $[Valid GPS Fix] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;In Emergency&lt;/td&gt;&lt;td&gt; $[In Emergency] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Text&lt;/td&gt;&lt;td&gt; $[Text] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Event&lt;/td&gt;&lt;td&gt; $[Event] &lt;/td&gt;&lt;/tr&gt;&lt;/table&gt;</text>
      </BalloonStyle>
    </Style>
    <Style id="waypointstyle_979267">
      <IconStyle>
        <color>ff006cff</color>
        <colorMode>normal</colorMode>
        <Icon>
          <href>http://maps.google.com/mapfiles/kml/paddle/wht-blank.png</href>
        </Icon>
      </IconStyle>
      <BalloonStyle>
        <text>&lt;table&gt;&lt;tr&gt;&lt;td&gt;Time&lt;/td&gt;&lt;td&gt; $[Time] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Time UTC&lt;/td&gt;&lt;td&gt; $[Time UTC] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Latitude&lt;/td&gt;&lt;td&gt; $[Latitude] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Longitude&lt;/td&gt;&lt;td&gt; $[Longitude] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Text&lt;/td&gt;&lt;td&gt; $[Text] &lt;/td&gt;&lt;/tr&gt;&lt;/table&gt;</text>
      </BalloonStyle>
    </Style>
    <Style id="linestyle_979267">
      <LineStyle>
        <color>ff006cff</color>
        <colorMode>normal</colorMode>
        <width>1</width>
        <labelVisibility xmlns="http://www.google.com/kml/ext/2.2">false</labelVisibility>
      </LineStyle>
    </Style>
    <Folder>
      <name>Chris Jones</name>
      <Placemark>
        <name>Chris Jones</name>
        <visibility>true</visibility>
        <description />
        <TimeStamp>
          <when>2019-03-08T20:00:00Z</when>
        </TimeStamp>
        <styleUrl>#style_979267</styleUrl>
        <ExtendedData>
          <Data name="Id">
            <value>289906908</value>
          </Data>
          <Data name="Time UTC">
            <value>3/8/2019 8:00:00 PM</value>
          </Data>
          <Data name="Time">
            <value>3/8/2019 12:00:00 PM</value>
          </Data>
          <Data name="Name">
            <value>Chris Jones</value>
          </Data>
          <Data name="Map Display Name">
            <value>ChrisJ</value>
          </Data>
          <Data name="Device Type">
            <value>inReach 2.5</value>
          </Data>
          <Data name="IMEI">
            <value>300434060291470</value>
          </Data>
          <Data name="Incident Id">
            <value />
          </Data>
          <Data name="Latitude">
            <value>47.600766</value>
          </Data>
          <Data name="Longitude">
            <value>-122.329008</value>
          </Data>
          <Data name="Elevation">
            <value>34.82 m from MSL</value>
          </Data>
          <Data name="Velocity">
            <value>5.0 km/h</value>
          </Data>
          <Data name="Course">
            <value>337.50 ° True</value>
          </Data>
          <Data name="Valid GPS Fix">
            <value>True</value>
          </Data>
          <Data name="In Emergency">
            <value>False</value>
          </Data>
          <Data name="Text">
            <value />
          </Data>
          <Data name="Event">
            <value>Tracking interval received.</value>
          </Data>
        </ExtendedData>
        <Point>
          <extrude>false</extrude>
          <altitudeMode>absolute</altitudeMode>
          <coordinates>-122.329008,47.600766,34.82</coordinates>
        </Point>
      </Placemark>
      <Placemark>
        <name>Chris Jones</name>
        <visibility>true</visibility>
        <description>Chris Jones's track log</description>
        <styleUrl>#linestyle_979267</styleUrl>
        <LineString>
          <tessellate>true</tessellate>
          <coordinates>-122.329008,47.600766,34.82</coordinates>
        </LineString>
      </Placemark>
    </Folder>
  </Document>
</kml>
"""

KML_RESULT_MULTIPLE_POINTS = """<?xml version="1.0" encoding="utf-8"?>
<kml xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>KML Export 3/9/2019 6:38:04 PM</name>
    <Style id="style_emergency">
      <IconStyle>
        <colorMode>normal</colorMode>
        <Icon>
          <href>http://maps.google.com/mapfiles/kml/shapes/caution.png</href>
        </Icon>
      </IconStyle>
      <BalloonStyle>
        <text>&lt;table&gt;&lt;tr&gt;&lt;td&gt;Id&lt;/td&gt;&lt;td&gt; $[Id] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Time&lt;/td&gt;&lt;td&gt; $[Time] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Time UTC&lt;/td&gt;&lt;td&gt; $[Time UTC] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Name&lt;/td&gt;&lt;td&gt; $[Name] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Map Display Name&lt;/td&gt;&lt;td&gt; $[Map Display Name] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Device Type&lt;/td&gt;&lt;td&gt; $[Device Type] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;IMEI&lt;/td&gt;&lt;td&gt; $[IMEI] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Incident Id&lt;/td&gt;&lt;td&gt; $[Incident Id] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Latitude&lt;/td&gt;&lt;td&gt; $[Latitude] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Longitude&lt;/td&gt;&lt;td&gt; $[Longitude] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Elevation&lt;/td&gt;&lt;td&gt; $[Elevation] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Velocity&lt;/td&gt;&lt;td&gt; $[Velocity] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Course&lt;/td&gt;&lt;td&gt; $[Course] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Valid GPS Fix&lt;/td&gt;&lt;td&gt; $[Valid GPS Fix] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;In Emergency&lt;/td&gt;&lt;td&gt; $[In Emergency] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Text&lt;/td&gt;&lt;td&gt; $[Text] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Event&lt;/td&gt;&lt;td&gt; $[Event] &lt;/td&gt;&lt;/tr&gt;&lt;/table&gt;</text>
      </BalloonStyle>
    </Style>
    <Style id="style_979267">
      <IconStyle>
        <color>ff006cff</color>
        <colorMode>normal</colorMode>
        <Icon>
          <href>http://maps.google.com/mapfiles/kml/paddle/wht-blank.png</href>
        </Icon>
      </IconStyle>
      <BalloonStyle>
        <text>&lt;table&gt;&lt;tr&gt;&lt;td&gt;Id&lt;/td&gt;&lt;td&gt; $[Id] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Time&lt;/td&gt;&lt;td&gt; $[Time] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Time UTC&lt;/td&gt;&lt;td&gt; $[Time UTC] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Name&lt;/td&gt;&lt;td&gt; $[Name] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Map Display Name&lt;/td&gt;&lt;td&gt; $[Map Display Name] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Device Type&lt;/td&gt;&lt;td&gt; $[Device Type] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;IMEI&lt;/td&gt;&lt;td&gt; $[IMEI] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Incident Id&lt;/td&gt;&lt;td&gt; $[Incident Id] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Latitude&lt;/td&gt;&lt;td&gt; $[Latitude] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Longitude&lt;/td&gt;&lt;td&gt; $[Longitude] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Elevation&lt;/td&gt;&lt;td&gt; $[Elevation] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Velocity&lt;/td&gt;&lt;td&gt; $[Velocity] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Course&lt;/td&gt;&lt;td&gt; $[Course] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Valid GPS Fix&lt;/td&gt;&lt;td&gt; $[Valid GPS Fix] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;In Emergency&lt;/td&gt;&lt;td&gt; $[In Emergency] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Text&lt;/td&gt;&lt;td&gt; $[Text] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Event&lt;/td&gt;&lt;td&gt; $[Event] &lt;/td&gt;&lt;/tr&gt;&lt;/table&gt;</text>
      </BalloonStyle>
    </Style>
    <Style id="waypointstyle_979267">
      <IconStyle>
        <color>ff006cff</color>
        <colorMode>normal</colorMode>
        <Icon>
          <href>http://maps.google.com/mapfiles/kml/paddle/wht-blank.png</href>
        </Icon>
      </IconStyle>
      <BalloonStyle>
        <text>&lt;table&gt;&lt;tr&gt;&lt;td&gt;Time&lt;/td&gt;&lt;td&gt; $[Time] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Time UTC&lt;/td&gt;&lt;td&gt; $[Time UTC] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Latitude&lt;/td&gt;&lt;td&gt; $[Latitude] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Longitude&lt;/td&gt;&lt;td&gt; $[Longitude] &lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;Text&lt;/td&gt;&lt;td&gt; $[Text] &lt;/td&gt;&lt;/tr&gt;&lt;/table&gt;</text>
      </BalloonStyle>
    </Style>
    <Style id="linestyle_979267">
      <LineStyle>
        <color>ff006cff</color>
        <colorMode>normal</colorMode>
        <width>1</width>
        <labelVisibility xmlns="http://www.google.com/kml/ext/2.2">false</labelVisibility>
      </LineStyle>
    </Style>
    <Folder>
      <name>Chris Jones</name>
      <Placemark>
        <name />
        <visibility>true</visibility>
        <description />
        <TimeStamp>
          <when>2019-03-08T19:53:45Z</when>
        </TimeStamp>
        <styleUrl>#style_979267</styleUrl>
        <ExtendedData>
          <Data name="Id">
            <value>289905914</value>
          </Data>
          <Data name="Time UTC">
            <value>3/8/2019 7:53:45 PM</value>
          </Data>
          <Data name="Time">
            <value>3/8/2019 11:53:45 AM</value>
          </Data>
          <Data name="Name">
            <value>Chris Jones</value>
          </Data>
          <Data name="Map Display Name">
            <value>ChrisJ</value>
          </Data>
          <Data name="Device Type">
            <value>inReach 2.5</value>
          </Data>
          <Data name="IMEI">
            <value>300434060291470</value>
          </Data>
          <Data name="Incident Id">
            <value />
          </Data>
          <Data name="Latitude">
            <value>47.598535</value>
          </Data>
          <Data name="Longitude">
            <value>-122.329116</value>
          </Data>
          <Data name="Elevation">
            <value>40.92 m from MSL</value>
          </Data>
          <Data name="Velocity">
            <value>4.0 km/h</value>
          </Data>
          <Data name="Course">
            <value>0.00 ° True</value>
          </Data>
          <Data name="Valid GPS Fix">
            <value>True</value>
          </Data>
          <Data name="In Emergency">
            <value>False</value>
          </Data>
          <Data name="Text">
            <value />
          </Data>
          <Data name="Event">
            <value>Tracking turned on from device.</value>
          </Data>
        </ExtendedData>
        <Point>
          <extrude>false</extrude>
          <altitudeMode>absolute</altitudeMode>
          <coordinates>-122.329116,47.598535,40.92</coordinates>
        </Point>
      </Placemark>
      <Placemark>
        <name />
        <visibility>true</visibility>
        <description />
        <TimeStamp>
          <when>2019-03-08T19:55:15Z</when>
        </TimeStamp>
        <styleUrl>#style_979267</styleUrl>
        <ExtendedData>
          <Data name="Id">
            <value>289905926</value>
          </Data>
          <Data name="Time UTC">
            <value>3/8/2019 7:55:15 PM</value>
          </Data>
          <Data name="Time">
            <value>3/8/2019 11:55:15 AM</value>
          </Data>
          <Data name="Name">
            <value>Chris Jones</value>
          </Data>
          <Data name="Map Display Name">
            <value>ChrisJ</value>
          </Data>
          <Data name="Device Type">
            <value>inReach 2.5</value>
          </Data>
          <Data name="IMEI">
            <value>300434060291470</value>
          </Data>
          <Data name="Incident Id">
            <value />
          </Data>
          <Data name="Latitude">
            <value>47.599135</value>
          </Data>
          <Data name="Longitude">
            <value>-122.328945</value>
          </Data>
          <Data name="Elevation">
            <value>10.46 m from MSL</value>
          </Data>
          <Data name="Velocity">
            <value>4.0 km/h</value>
          </Data>
          <Data name="Course">
            <value>270.00 ° True</value>
          </Data>
          <Data name="Valid GPS Fix">
            <value>True</value>
          </Data>
          <Data name="In Emergency">
            <value>False</value>
          </Data>
          <Data name="Text">
            <value />
          </Data>
          <Data name="Event">
            <value>Tracking message received.</value>
          </Data>
        </ExtendedData>
        <Point>
          <extrude>false</extrude>
          <altitudeMode>absolute</altitudeMode>
          <coordinates>-122.328945,47.599135,10.46</coordinates>
        </Point>
      </Placemark>
      <Placemark>
        <name />
        <visibility>true</visibility>
        <description />
        <TimeStamp>
          <when>2019-03-08T19:56:15Z</when>
        </TimeStamp>
        <styleUrl>#style_979267</styleUrl>
        <ExtendedData>
          <Data name="Id">
            <value>289906980</value>
          </Data>
          <Data name="Time UTC">
            <value>3/8/2019 7:56:15 PM</value>
          </Data>
          <Data name="Time">
            <value>3/8/2019 11:56:15 AM</value>
          </Data>
          <Data name="Name">
            <value>Chris Jones</value>
          </Data>
          <Data name="Map Display Name">
            <value>ChrisJ</value>
          </Data>
          <Data name="Device Type">
            <value>inReach 2.5</value>
          </Data>
          <Data name="IMEI">
            <value>300434060291470</value>
          </Data>
          <Data name="Incident Id">
            <value />
          </Data>
          <Data name="Latitude">
            <value>47.598996</value>
          </Data>
          <Data name="Longitude">
            <value>-122.329201</value>
          </Data>
          <Data name="Elevation">
            <value>10.46 m from MSL</value>
          </Data>
          <Data name="Velocity">
            <value>0.0 km/h</value>
          </Data>
          <Data name="Course">
            <value>0.00 ° True</value>
          </Data>
          <Data name="Valid GPS Fix">
            <value>True</value>
          </Data>
          <Data name="In Emergency">
            <value>False</value>
          </Data>
          <Data name="Text">
            <value />
          </Data>
          <Data name="Event">
            <value>Tracking turned off from device.</value>
          </Data>
        </ExtendedData>
        <Point>
          <extrude>false</extrude>
          <altitudeMode>absolute</altitudeMode>
          <coordinates>-122.329201,47.598996,10.46</coordinates>
        </Point>
      </Placemark>
      <Placemark>
        <name />
        <visibility>true</visibility>
        <description />
        <TimeStamp>
          <when>2019-03-08T19:56:30Z</when>
        </TimeStamp>
        <styleUrl>#style_979267</styleUrl>
        <ExtendedData>
          <Data name="Id">
            <value>289906905</value>
          </Data>
          <Data name="Time UTC">
            <value>3/8/2019 7:56:30 PM</value>
          </Data>
          <Data name="Time">
            <value>3/8/2019 11:56:30 AM</value>
          </Data>
          <Data name="Name">
            <value>Chris Jones</value>
          </Data>
          <Data name="Map Display Name">
            <value>ChrisJ</value>
          </Data>
          <Data name="Device Type">
            <value>inReach 2.5</value>
          </Data>
          <Data name="IMEI">
            <value>300434060291470</value>
          </Data>
          <Data name="Incident Id">
            <value />
          </Data>
          <Data name="Latitude">
            <value>47.598975</value>
          </Data>
          <Data name="Longitude">
            <value>-122.329245</value>
          </Data>
          <Data name="Elevation">
            <value>8.43 m from MSL</value>
          </Data>
          <Data name="Velocity">
            <value>0.0 km/h</value>
          </Data>
          <Data name="Course">
            <value>0.00 ° True</value>
          </Data>
          <Data name="Valid GPS Fix">
            <value>True</value>
          </Data>
          <Data name="In Emergency">
            <value>False</value>
          </Data>
          <Data name="Text">
            <value />
          </Data>
          <Data name="Event">
            <value>Tracking turned on from device.</value>
          </Data>
        </ExtendedData>
        <Point>
          <extrude>false</extrude>
          <altitudeMode>absolute</altitudeMode>
          <coordinates>-122.329245,47.598975,8.43</coordinates>
        </Point>
      </Placemark>
      <Placemark>
        <name />
        <visibility>true</visibility>
        <description />
        <TimeStamp>
          <when>2019-03-08T19:57:30Z</when>
        </TimeStamp>
        <styleUrl>#style_979267</styleUrl>
        <ExtendedData>
          <Data name="Id">
            <value>289906953</value>
          </Data>
          <Data name="Time UTC">
            <value>3/8/2019 7:57:30 PM</value>
          </Data>
          <Data name="Time">
            <value>3/8/2019 11:57:30 AM</value>
          </Data>
          <Data name="Name">
            <value>Chris Jones</value>
          </Data>
          <Data name="Map Display Name">
            <value>ChrisJ</value>
          </Data>
          <Data name="Device Type">
            <value>inReach 2.5</value>
          </Data>
          <Data name="IMEI">
            <value>300434060291470</value>
          </Data>
          <Data name="Incident Id">
            <value />
          </Data>
          <Data name="Latitude">
            <value>47.599221</value>
          </Data>
          <Data name="Longitude">
            <value>-122.329180</value>
          </Data>
          <Data name="Elevation">
            <value>4.37 m from MSL</value>
          </Data>
          <Data name="Velocity">
            <value>4.0 km/h</value>
          </Data>
          <Data name="Course">
            <value>22.50 ° True</value>
          </Data>
          <Data name="Valid GPS Fix">
            <value>True</value>
          </Data>
          <Data name="In Emergency">
            <value>False</value>
          </Data>
          <Data name="Text">
            <value />
          </Data>
          <Data name="Event">
            <value>Tracking interval received.</value>
          </Data>
        </ExtendedData>
        <Point>
          <extrude>false</extrude>
          <altitudeMode>absolute</altitudeMode>
          <coordinates>-122.32918,47.599221,4.37</coordinates>
        </Point>
      </Placemark>
      <Placemark>
        <name />
        <visibility>true</visibility>
        <description />
        <TimeStamp>
          <when>2019-03-08T19:59:00Z</when>
        </TimeStamp>
        <styleUrl>#style_979267</styleUrl>
        <ExtendedData>
          <Data name="Id">
            <value>289906925</value>
          </Data>
          <Data name="Time UTC">
            <value>3/8/2019 7:59:00 PM</value>
          </Data>
          <Data name="Time">
            <value>3/8/2019 11:59:00 AM</value>
          </Data>
          <Data name="Name">
            <value>Chris Jones</value>
          </Data>
          <Data name="Map Display Name">
            <value>ChrisJ</value>
          </Data>
          <Data name="Device Type">
            <value>inReach 2.5</value>
          </Data>
          <Data name="IMEI">
            <value>300434060291470</value>
          </Data>
          <Data name="Incident Id">
            <value />
          </Data>
          <Data name="Latitude">
            <value>47.600305</value>
          </Data>
          <Data name="Longitude">
            <value>-122.329201</value>
          </Data>
          <Data name="Elevation">
            <value>30.76 m from MSL</value>
          </Data>
          <Data name="Velocity">
            <value>6.0 km/h</value>
          </Data>
          <Data name="Course">
            <value>337.50 ° True</value>
          </Data>
          <Data name="Valid GPS Fix">
            <value>True</value>
          </Data>
          <Data name="In Emergency">
            <value>False</value>
          </Data>
          <Data name="Text">
            <value />
          </Data>
          <Data name="Event">
            <value>Tracking interval received.</value>
          </Data>
        </ExtendedData>
        <Point>
          <extrude>false</extrude>
          <altitudeMode>absolute</altitudeMode>
          <coordinates>-122.329201,47.600305,30.76</coordinates>
        </Point>
      </Placemark>
      <Placemark>
        <name>Chris Jones</name>
        <visibility>true</visibility>
        <description />
        <TimeStamp>
          <when>2019-03-08T20:00:00Z</when>
        </TimeStamp>
        <styleUrl>#style_979267</styleUrl>
        <ExtendedData>
          <Data name="Id">
            <value>289906908</value>
          </Data>
          <Data name="Time UTC">
            <value>3/8/2019 8:00:00 PM</value>
          </Data>
          <Data name="Time">
            <value>3/8/2019 12:00:00 PM</value>
          </Data>
          <Data name="Name">
            <value>Chris Jones</value>
          </Data>
          <Data name="Map Display Name">
            <value>ChrisJ</value>
          </Data>
          <Data name="Device Type">
            <value>inReach 2.5</value>
          </Data>
          <Data name="IMEI">
            <value>300434060291470</value>
          </Data>
          <Data name="Incident Id">
            <value />
          </Data>
          <Data name="Latitude">
            <value>47.600766</value>
          </Data>
          <Data name="Longitude">
            <value>-122.329008</value>
          </Data>
          <Data name="Elevation">
            <value>34.82 m from MSL</value>
          </Data>
          <Data name="Velocity">
            <value>5.0 km/h</value>
          </Data>
          <Data name="Course">
            <value>337.50 ° True</value>
          </Data>
          <Data name="Valid GPS Fix">
            <value>True</value>
          </Data>
          <Data name="In Emergency">
            <value>False</value>
          </Data>
          <Data name="Text">
            <value />
          </Data>
          <Data name="Event">
            <value>Tracking interval received.</value>
          </Data>
        </ExtendedData>
        <Point>
          <extrude>false</extrude>
          <altitudeMode>absolute</altitudeMode>
          <coordinates>-122.329008,47.600766,34.82</coordinates>
        </Point>
      </Placemark>
      <Placemark>
        <name>Chris Jones</name>
        <visibility>true</visibility>
        <description>Chris Jones's track log</description>
        <styleUrl>#linestyle_979267</styleUrl>
        <LineString>
          <tessellate>true</tessellate>
          <coordinates>-122.329116,47.598535,40.92
-122.328945,47.599135,10.46
-122.329201,47.598996,10.46
-122.329245,47.598975,8.43
-122.32918,47.599221,4.37
-122.329201,47.600305,30.76
-122.329008,47.600766,34.82</coordinates>
        </LineString>
      </Placemark>
    </Folder>
  </Document>
</kml>"""


class TestInreachKML(TestCase):
    def test_kml_parse_single_point(self):
        client = inreachkml.InreachKMLClient('', '', '')

        placemarks = client.gen_placemarks(
            KML_RESULT_SINGLE_POINT.encode('utf-8'))

        for pos in placemarks:
            self.assertIsNotNone(pos['recorded_at'])

    def test_kml_parse_multiple_points(self):
        client = inreachkml.InreachKMLClient('', '', '')

        placemarks = client.gen_placemarks(
            KML_RESULT_MULTIPLE_POINTS.encode('utf-8'))

        ct = 0
        for pos in placemarks:
            self.assertIsNotNone(pos['recorded_at'])
            ct += 1

        self.assertGreater(ct, 1)

    def test_empty_kml(self):
        client = inreachkml.InreachKMLClient('', '', '')

        placemarks = client.gen_placemarks(KML_RESULT_EMPTY.encode('utf-8'))

        self.assertEqual(len(list(placemarks)), 0)
