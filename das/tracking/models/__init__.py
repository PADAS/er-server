from tracking.models.plugin_base import SourcePlugin
from tracking.models.savannah import SavannahPlugin
from tracking.models.demo import DemoSourcePlugin
from tracking.models.inreach import InreachPlugin
from tracking.models.awtgsm import AWTHttpPlugin
from tracking.models.inreachkml import InreachKMLPlugin
from tracking.models.skygistics import SkygisticsSatellitePlugin
from tracking.models.firms import FirmsPlugin
from tracking.models.awetelemetry import AWETelemetryPlugin
from tracking.models.spidertracks import SpiderTracksPlugin
from tracking.models.plugin_base import TrackingPlugin
from tracking.models.sirtrack import SirtrackPlugin
from tracking.models.vectronics import VectronicsPlugin
from tracking.models.awt import AwtPlugin
from tracking.models.er_track import SourceProviderConfiguration

runnable_plugins = (SavannahPlugin, DemoSourcePlugin, InreachPlugin, InreachKMLPlugin, AWTHttpPlugin,
                    SkygisticsSatellitePlugin, SpiderTracksPlugin, AWETelemetryPlugin, SirtrackPlugin,
                    VectronicsPlugin, AwtPlugin)
