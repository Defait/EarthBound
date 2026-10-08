package pack.world.geo;

import net.yazloysasha.tfcrealworld.config.TFCRealWorldConfig;
import net.yazloysasha.tfcrealworld.util.geography.WaypointCoordinates;

/**
 * Every reference to TFC: Real World lives here, so the class only loads when the mod is present (it is optional).
 */
final class RealWorld
{
    private RealWorld() {}

    /**
     * Block x and z for a latitude and longitude, the way Real World places its own waypoint markers (fits the longitude to
     * the map's edges, projects, clamps to the map, rounds).
     */
    static int[] toBlockXZ(double latitude, double longitude)
    {
        return WaypointCoordinates.toBlockXZ(latitude, longitude);
    }

    /** Half the map's width in blocks: no projected point lies further from the centre (Real World clamps to it). */
    static int horizontalScale()
    {
        return TFCRealWorldConfig.HORIZONTAL_SCALE.get();
    }

    /** What the projection depends on: the world's scale and the map profile's edges. */
    static String configKey()
    {
        return TFCRealWorldConfig.HORIZONTAL_SCALE.get() + "/" + TFCRealWorldConfig.VERTICAL_SCALE.get() + "/"
            + TFCRealWorldConfig.getWestEdgeLongitude() + "/" + TFCRealWorldConfig.getEastEdgeLongitude() + "/"
            + TFCRealWorldConfig.getSouthEdgeLatitude() + "/" + TFCRealWorldConfig.getNorthEdgeLatitude() + "/"
            + TFCRealWorldConfig.MAP_PROFILE.get();
    }
}
