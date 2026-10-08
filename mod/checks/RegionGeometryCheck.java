import java.util.List;
import pack.world.geo.RegionGeometry;
import pack.world.geo.RegionGeometry.Point;
import pack.world.geo.RegionGeometry.Shape;

/**
 * Offline check of pack_world:region's geometry (no Minecraft, no server). Run after building the mod:
 * <pre>
 *   cd mod
 *   JAVA_HOME="C:\Program Files\Java\jdk-22.0.1" ./gradlew compileJava
 *   "$JAVA_HOME/bin/java" -cp build/classes/java/main checks/RegionGeometryCheck.java
 * </pre>
 * The real projection is TFC: Real World's and is checked on the test server (tools/structures_test.py); here a stand-in with the same
 * contract: block x grows with longitude fitted into the map's edges (a profile of -170 to 190 here, like the pack's), z falls with
 * latitude, 1,000 blocks per degree.
 */
public final class RegionGeometryCheck
{
    private static int failures;

    static int[] project(double west, double east, double lat, double lon)
    {
        double l = lon;
        while (l < west)
        {
            l += 360;
        }
        while (l > east)
        {
            l -= 360;
        }
        return new int[] {(int) Math.round(l * 1000), (int) Math.round(-lat * 1000)};
    }

    static void check(String name, boolean ok, String detail)
    {
        if (!ok)
        {
            failures++;
        }
        System.out.println((ok ? "PASS " : "FAIL ") + name + (detail.isEmpty() ? "" : ": " + detail));
    }

    static Shape shape(String name, List<Point> ring, double west, double east)
    {
        final String[] problem = new String[1];
        final Shape s = RegionGeometry.project(name, ring, (la, lo) -> project(west, east, la, lo), 16, 180_000, problem);
        if (s == null)
        {
            System.out.println("  (" + name + " dropped: " + problem[0] + ")");
        }
        return s;
    }

    public static void main(String[] args)
    {
        // a concave L: 0..10 x 0..4 and 0..4 x 0..10 (lat, lon)
        final List<Point> ell = List.of(new Point(0, 0), new Point(0, 10), new Point(4, 10), new Point(4, 4), new Point(10, 4), new Point(10, 0));
        final Shape l = shape("L", ell, -170, 190);
        check("L: inside the long arm", l.contains(2000, -2000), "");
        check("L: inside the tall arm", l.contains(2000, -8000), "");
        check("L: the notch is outside", !l.contains(8000, -8000), "");
        check("L: far outside", !l.contains(50000, 50000), "");
        check("L: area is the sum of the arms (64 deg^2 at 1e6 blocks^2/deg^2)", Math.abs(l.area() - 64e6) < 1e3, "" + l.area());

        // densify: a 10-degree edge gets 10 steps; a 0.5-degree edge one
        final List<Point> dense = RegionGeometry.densify(List.of(new Point(0, 0), new Point(0, 10), new Point(0.5, 10)), 1.0);
        check("densify: 10 + 1 + 10 points (the ring closes)", dense.size() == 21, "" + dense.size());

        // the short way round the globe
        final List<Point> across = RegionGeometry.densify(List.of(new Point(0, 179), new Point(0, -179), new Point(1, -179), new Point(1, 179)), 1.0);
        boolean sane = true;
        for (Point p : across)
        {
            final double lon = (p.lon() + 360) % 360;
            sane &= lon >= 178.5 && lon <= 181.5;
        }
        check("densify: 179 to -179 crosses the antimeridian (stays within 178.5..181.5 mod 360)", sane, across.toString());

        // a box over the antimeridian
        final Shape box = shape("pacific", RegionGeometry.boxRing(10, 170, 20, -175), -170, 190);
        check("antimeridian box: contains 180", box != null && box.contains(180_000, -15_000), "");
        check("antimeridian box: contains -177 (fitted to 183)", box != null && box.contains(183_000, -15_000), "");
        check("antimeridian box: not 0", box != null && !box.contains(0, -15_000), "");
        check("antimeridian box: not 160", box != null && !box.contains(160_000, -15_000), "");

        // the same box on a map whose seam is the antimeridian: the region crosses the seam and is dropped
        check("seam: a region crossing the map's seam is dropped", shape("seam", RegionGeometry.boxRing(10, 170, 20, -175), -180, 180) == null, "");

        // outside the profile: the vertices clamp onto the border (a degenerate sliver) and the region is dropped
        final String[] problem = new String[1];
        final Shape sliver = RegionGeometry.project("clamped", RegionGeometry.boxRing(10, 30, 20, 40), (la, lo) -> new int[] {5000, (int) (-la * 1000)}, 16, 180_000, problem);
        check("clamped: narrower than 16 blocks is dropped", sliver == null && problem[0] != null, String.valueOf(problem[0]));

        // an ordinary box (Iceland-sized) and a triangle
        final Shape iceland = shape("iceland", RegionGeometry.boxRing(63.2, -24.6, 66.6, -13.3), -170, 190);
        check("iceland box contains Reykjavik", iceland.contains(-21_943, -64_147), "");
        check("iceland box does not contain Oslo", !iceland.contains(10_752, -59_914), "");
        final Shape tri = shape("tri", List.of(new Point(0, 0), new Point(0, 10), new Point(10, 0)), -170, 190);
        check("triangle: inside the hypotenuse", tri.contains(2000, -2000) && !tri.contains(8000, -8000), "");
        check("triangle: vertex count after densifying", tri.vertices() == 30, "" + tri.vertices());

        System.out.println(failures == 0 ? "all passed" : failures + " FAILED");
        System.exit(failures == 0 ? 0 : 1);
    }
}
