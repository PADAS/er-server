<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="2.10.0-Pisa" minimumScale="0" maximumScale="1e+08" hasScaleBasedVisibilityFlag="0">
  <pipe>
    <rasterrenderer opacity="1" alphaBand="-1" classificationMax="55" classificationMinMaxOrigin="CumulativeCutFullExtentEstimated" band="1" classificationMin="30" type="singlebandpseudocolor">
      <rasterTransparency/>
      <rastershader>
        <colorrampshader colorRampType="INTERPOLATED" clip="0">
          <item alpha="255" value="1" label="Cloud Shadows" color="#343434"/>
          <item alpha="255" value="2" label="Clouds" color="#343434"/>
          <item alpha="255" value="30" label="Forest above 600m" color="#267300"/>
          <item alpha="255" value="31" label="Forest below 600m" color="#38a800"/>
          <item alpha="255" value="32" label="Forest Light" color="#cdf57a"/>
          <item alpha="255" value="40" label="Forest Riverine" color="#6699cd"/>
          <item alpha="255" value="41" label="Riparian Zone" color="#73b2ff"/>
          <item alpha="255" value="42" label="Bais" color="#ff00c5"/>
          <item alpha="255" value="43" label="Forest Lowland" color="#a8a800"/>
          <item alpha="255" value="50" label="Savanna" color="#ffaa00"/>
          <item alpha="255" value="51" label="Water" color="#0070ff"/>
          <item alpha="255" value="55" label="Forest High Slope >25%" color="#a87000"/>
          <item alpha="255" value="56" label="Agriculture" color="#ff0000"/>
          <item alpha="255" value="60" label="Village" color="#6b4a09"/>
        </colorrampshader>
      </rastershader>
    </rasterrenderer>
    <brightnesscontrast brightness="0" contrast="0"/>
    <huesaturation colorizeGreen="128" colorizeOn="0" colorizeRed="255" colorizeBlue="128" grayscaleMode="0" saturation="0" colorizeStrength="100"/>
    <rasterresampler maxOversampling="2"/>
  </pipe>
  <blendMode>0</blendMode>
</qgis>
