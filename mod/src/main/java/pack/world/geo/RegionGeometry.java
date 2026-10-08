package pack.world.geo;

import java.util.ArrayList;
import java.util.List;

/**
 * The geometry of {@code pack_world:region}, with no Minecraft classes so it can be tested on its own
 * ({@code src/test/java/pack/world/geo/RegionGeometryCheck}). A region is a ring of latitude/longitude vertices; edges are
 * densified in latitude/longitude (so they follow parallels and meridians, as the author drew them), every point goes through the
 * world's projection, and containment is tested in block space with the even-odd rule.
 */
public final class RegionGeometry
{
    private RegionGeometry() {}

    /** A latitude and longitude in degrees. Longitudes may leave [-180, 180] after densifying across the antimeridian. */
    public record Point(double lat, double lon) {}

    /** Latitude/longitude to block x and z (what TFC: Real World does for its own waypoints). */
    @FunctionalInterface
    public interface Projection
    {
        int[] toBlockXZ(double latitude, double longitude);
    }

    /** One projected ring. */
    public static final class Shape
    {
        private final String name;
        private final double[] xs;
        private final double[] zs;
        private final double minX;
        private final double maxX;
        private final double minZ;
        private final double maxZ;

        Shape(String name, double[] xs, double[] zs)
        {
            this.name = name;
            this.xs = xs;
            this.zs = zs;
            double x0 = Double.POSITIVE_INFINITY;
            double x1 = Double.NEGATIVE_INFINITY;
            double z0 = Double.POSITIVE_INFINITY;
            double z1 = Double.NEGATIVE_INFINITY;
            for (int i = 0; i < xs.length; i++)
            {
                x0 = Math.min(x0, xs[i]);
                x1 = Math.max(x1, xs[i]);
                z0 = Math.min(z0, zs[i]);
                z1 = Math.max(z1, zs[i]);
            }
            this.minX = x0;
            this.maxX = x1;
            this.minZ = z0;
            this.maxZ = z1;
        }

        public String name()
        {
            return name;
        }

        public int vertices()
        {
            return xs.length;
        }

        /** The bounding box in blocks: {minX, minZ, maxX, maxZ}. */
        public double[] bounds()
        {
            return new double[] {minX, minZ, maxX, maxZ};
        }

        /** The area of the ring in blocks squared (shoelace formula). */
        public double area()
        {
            double sum = 0;
            for (int i = 0, j = xs.length - 1; i < xs.length; j = i++)
            {
                sum += (xs[j] + xs[i]) * (zs[j] - zs[i]);
            }
            return Math.abs(sum) / 2;
        }

        public boolean contains(double x, double z)
        {
            if (x < minX || x > maxX || z < minZ || z > maxZ)
            {
                return false;
            }
            boolean in = false;
            for (int i = 0, j = xs.length - 1; i < xs.length; j = i++)
            {
                if ((zs[i] > z) != (zs[j] > z) && x < (xs[j] - xs[i]) * (z - zs[i]) / (zs[j] - zs[i]) + xs[i])
                {
                    in = !in;
                }
            }
            return in;
        }
    }

    /** The ring of a box {@code [south, west, north, east]}; west greater than east means the box crosses the antimeridian. */
    public static List<Point> boxRing(double south, double west, double north, double east)
    {
        final double e = east < west ? east + 360 : east;
        return List.of(new Point(south, west), new Point(south, e), new Point(north, e), new Point(north, west));
    }

    /**
     * Edges in steps of at most {@code step} degrees along the longer of their latitude and longitude change, the short way round
     * the globe (an edge from 179 to -179 crosses the antimeridian). The last vertex of each edge is the first of the next.
     */
    public static List<Point> densify(List<Point> ring, double step)
    {
        final List<Point> out = new ArrayList<>();
        for (int i = 0; i < ring.size(); i++)
        {
            final Point a = ring.get(i);
            final Point b = ring.get((i + 1) % ring.size());
            final double dLat = b.lat() - a.lat();
            double dLon = b.lon() - a.lon();
            dLon -= 360 * Math.floor((dLon + 180) / 360);
            final int n = Math.max(1, (int) Math.ceil(Math.max(Math.abs(dLat), Math.abs(dLon)) / step));
            for (int k = 0; k < n; k++)
            {
                out.add(new Point(a.lat() + dLat * k / n, a.lon() + dLon * k / n));
            }
        }
        return out;
    }

    /**
     * Projects a ring. Returns null (and says why in {@code problem[0]}) for a shape that cannot be used: one narrower than
     * {@code minSize} blocks in x or z (a map profile that does not contain it clamps its vertices onto the border), or one with an
     * edge longer than {@code maxJump} blocks (it crosses the seam of the map).
     */
    public static Shape project(String name, List<Point> ring, Projection projection, double minSize, double maxJump, String[] problem)
    {
        final List<Point> dense = densify(ring, 1.0);
        final double[] xs = new double[dense.size()];
        final double[] zs = new double[dense.size()];
        for (int i = 0; i < xs.length; i++)
        {
            final int[] xz = projection.toBlockXZ(dense.get(i).lat(), dense.get(i).lon());
            xs[i] = xz[0];
            zs[i] = xz[1];
        }
        final Shape shape = new Shape(name, xs, zs);
        if (shape.maxX - shape.minX < minSize || shape.maxZ - shape.minZ < minSize)
        {
            problem[0] = "narrower than " + (int) minSize + " blocks (outside the map profile?)";
            return null;
        }
        for (int i = 0, j = xs.length - 1; i < xs.length; j = i++)
        {
            if (Math.abs(xs[i] - xs[j]) > maxJump)
            {
                problem[0] = "an edge spans " + (int) Math.abs(xs[i] - xs[j]) + " blocks: the region crosses the seam of the map";
                return null;
            }
        }
        return shape;
    }
}
