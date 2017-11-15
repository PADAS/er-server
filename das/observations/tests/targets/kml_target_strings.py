master_link_target = '''<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:gx="http://www.google.com/kml/ext/2.2">
  <Folder id="feat_22">
    <name>STE Tracking Service</name>
    <visibility>1</visibility>
    <open>1</open>
    <NetworkLink id="feat_23">
      <name>STE Tracking Service</name>
      <open>1</open>
      <Link id="link_7">
        <href>http://testserver:80/api/v1.0/subjects/kml/?auth={}</href>
      </Link>
    </NetworkLink>
  </Folder>
</kml>
'''

all_subjects_target = '''<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:gx="http://www.google.com/kml/ext/2.2">
  <Folder id="feat_2">
    <name>Tracking Data</name>
    <visibility>1</visibility>
    <Folder id="feat_3">
      <name>Elephant</name>
      <Folder id="feat_4">
        <name>Region 1</name>
        <NetworkLink id="feat_5">
          <name>Elephant 1</name>
          <visibility>0</visibility>
          <Link id="link_0">
            <href>http://testserver:80/api/v1.0/subject/d2ed403e-9419-41aa-8fa9-45a70e5ce2ed/kml/?auth={0}</href>
          </Link>
        </NetworkLink>
        <NetworkLink id="feat_6">
          <name>Elephant 2</name>
          <visibility>0</visibility>
          <Link id="link_1">
            <href>http://testserver:80/api/v1.0/subject/c25e17d0-0337-4f0c-9274-25e5ae4da7c8/kml/?auth={0}</href>
          </Link>
        </NetworkLink>
      </Folder>
      <Folder id="feat_7">
        <name>Region 2</name>
        <NetworkLink id="feat_8">
          <name>Elephant 3</name>
          <visibility>0</visibility>
          <Link id="link_2">
            <href>http://testserver:80/api/v1.0/subject/a873e49c-1cb5-4ad4-b29d-e4b8931036ba/kml/?auth={0}</href>
          </Link>
        </NetworkLink>
      </Folder>
    </Folder>
  </Folder>
</kml>
'''

single_subject_target = '''<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:gx="http://www.google.com/kml/ext/2.2">
  <Folder id="None">
    <name>Elephant 1</name>
    <visibility>1</visibility>
    <ScreenOverlay id="feat_11">
      <name>Logo</name>
      <Icon id="link_3">
        <href>http://107.21.94.89/Images/Logos/STE_Logo.png</href>
      </Icon>
      <overlayXY x="0" xunits="fraction" y="0" yunits="fraction"/>
      <screenXY x="0" xunits="fraction" y="0" yunits="fraction"/>
      <rotationXY x="0" xunits="fraction" y="0" yunits="fraction"/>
      <size x="0" xunits="fraction" y="0" yunits="fraction"/>
    </ScreenOverlay>
    <Document id="feat_12">
      <Style id="Elephant_1_Pointstyle">
        <IconStyle id="substyle_0">
          <color>ffdc1e1e</color>
          <colorMode>normal</colorMode>
          <scale>0.7</scale>
          <heading>0</heading>
          <Icon id="link_4">
            <href>http://testserver:80/static/unassigned-black.svg</href>
          </Icon>
        </IconStyle>
        <LabelStyle id="substyle_1">
          <colorMode>normal</colorMode>
          <scale>0</scale>
        </LabelStyle>
      </Style>
      <name>Elephant 1_points</name>
      <visibility>1</visibility>
      <Placemark id="feat_13">
        <name/>
        <description>2017-10-20 17:22</description>
        <Snippet>2017-10-20 17:22</Snippet>
        <TimeStamp id="time_0">
          <when>2017-10-20 17:22</when>
        </TimeStamp>
        <styleUrl>#Elephant_1_Pointstyle</styleUrl>
        <Point id="geom_0">
          <coordinates>2.0,2.0,0.0</coordinates>
        </Point>
      </Placemark>
      <Placemark id="feat_14">
        <name/>
        <description>2017-10-20 17:22</description>
        <Snippet>2017-10-20 17:22</Snippet>
        <TimeStamp id="time_1">
          <when>2017-10-20 17:22</when>
        </TimeStamp>
        <styleUrl>#Elephant_1_Pointstyle</styleUrl>
        <Point id="geom_1">
          <coordinates>2.0,1.0,0.0</coordinates>
        </Point>
      </Placemark>
      <Placemark id="feat_15">
        <name/>
        <description>2017-10-20 17:22</description>
        <Snippet>2017-10-20 17:22</Snippet>
        <TimeStamp id="time_2">
          <when>2017-10-20 17:22</when>
        </TimeStamp>
        <styleUrl>#Elephant_1_Pointstyle</styleUrl>
        <Point id="geom_2">
          <coordinates>1.0,1.0,0.0</coordinates>
        </Point>
      </Placemark>
    </Document>
    <Document id="feat_16">
      <Style id="Elephant_1_Linestyle">
        <LineStyle id="substyle_2">
          <color>ffdc1e1e</color>
          <colorMode>normal</colorMode>
          <width>0.4</width>
        </LineStyle>
      </Style>
      <name>Elephant 1_tracks</name>
      <visibility>1</visibility>
      <Placemark id="feat_17">
        <name/>
        <styleUrl>#Elephant_1_Linestyle</styleUrl>
        <LineString id="geom_3">
          <coordinates>2.0,2.0,0 2.0,1.0,0</coordinates>
          <extrude>0</extrude>
          <tessellate>1</tessellate>
        </LineString>
      </Placemark>
      <Placemark id="feat_18">
        <name/>
        <styleUrl>#Elephant_1_Linestyle</styleUrl>
        <LineString id="geom_4">
          <coordinates>2.0,1.0,0 1.0,1.0,0</coordinates>
          <extrude>0</extrude>
          <tessellate>1</tessellate>
        </LineString>
      </Placemark>
    </Document>
    <Document id="feat_19">
      <Style id="sh_Elephant_1_Finalmarkerstyle">
        <IconStyle id="substyle_3">
          <color>ffdc1e1e</color>
          <colorMode>normal</colorMode>
          <scale>0.7</scale>
          <heading>0</heading>
          <Icon id="link_5">
            <href>http://testserver:80/static/unassigned-black.svg</href>
          </Icon>
        </IconStyle>
        <LabelStyle id="substyle_4">
          <color>ffdc1e1e</color>
          <colorMode>normal</colorMode>
          <scale>1</scale>
        </LabelStyle>
        <BalloonStyle>
          <bgColor>ffdc1e1e</bgColor>
          <text>$[description</text>
          <displayMode>default</displayMode>
        </BalloonStyle>
      </Style>
      <Style id="sn_Elephant_1_Finalmarkerstyle">
        <IconStyle id="substyle_5">
          <color>ffdc1e1e</color>
          <colorMode>normal</colorMode>
          <scale>0.7</scale>
          <heading>0</heading>
          <Icon id="link_6">
            <href>http://testserver:80/static/unassigned-black.svg</href>
          </Icon>
        </IconStyle>
        <LabelStyle id="substyle_6">
          <colorMode>normal</colorMode>
          <scale>0</scale>
        </LabelStyle>
        <BalloonStyle>
          <bgColor>ffdc1e1e</bgColor>
          <text>$[description</text>
          <displayMode>default</displayMode>
        </BalloonStyle>
      </Style>
      <StyleMap id="msn_Elephant_1_Finalmarkerstyle">
        <Pair>
          <key>normal</key>
          <styleUrl>#sn_Elephant_1_Finalmarkerstyle</styleUrl>
        </Pair>
        <Pair>
          <key>highlight</key>
          <styleUrl>#sh_Elephant_1_Finalmarkerstyle</styleUrl>
        </Pair>
      </StyleMap>
      <name>Elephant 1' Last Position</name>
      <visibility>1</visibility>
      <Placemark id="feat_20">
        <name>Last Position: 2017-10-20 17:22</name>
        <description>2017-10-20 17:22</description>
        <Snippet/>
        <TimeStamp id="time_3">
          <when>2017-10-20 17:22</when>
        </TimeStamp>
        <styleUrl>#msn_Elephant_1_Finalmarkerstyle</styleUrl>
        <Point id="geom_5">
          <coordinates>2.0,2.0,0.0</coordinates>
        </Point>
      </Placemark>
    </Document>
  </Folder>
</kml>
'''
