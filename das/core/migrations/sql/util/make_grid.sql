CREATE OR REPLACE FUNCTION makegrid_2d_as_collection (
  bound_polygon public.geometry,
  grid_step float,
  metric_srid integer = 4326, --metric SRID (this particular is optimal for the Western Russia)
  border_correction_factor float = 0.000000000001
)
RETURNS TABLE(geom public.geometry) AS
$body$
DECLARE
  BoundM public.geometry; --Bound polygon transformed to the metric projection (with metric_srid SRID)
  Xmin DOUBLE PRECISION;
  Xmax DOUBLE PRECISION;
  Ymax DOUBLE PRECISION;
  X DOUBLE PRECISION;
  Y DOUBLE PRECISION;
  X2 DOUBLE PRECISION;
  Y2 DOUBLE PRECISION;
  sectors public.geometry[];
  i INTEGER;
BEGIN
  BoundM := ST_Transform(bound_polygon, metric_srid); --From WGS84 (SRID 4326) to the metric projection, to operate with step in meters
  Xmin := ST_XMin(BoundM);
  Xmax := ST_XMax(BoundM);
  Ymax := ST_YMax(BoundM);

  Y := ST_YMin(BoundM); --current sector's corner coordinate
  i := -1;
  <<yloop>>
  LOOP
    --Better if generating polygons exceeds the bound for one step. You always can crop the result. But if not you may
    -- get not quite correct data for outbound polygons (e.g. if you calculate frequency per sector)
    IF (Y >= Ymax) THEN
        EXIT;
    END IF;

    X := Xmin;
    <<xloop>>
    LOOP
      IF (X >= Xmax) THEN
          EXIT;
      END IF;

      i := i + 1;

      X2 := X + grid_step;
      IF X2 < Xmax THEN
        X2 := X2 - border_correction_factor;
      END IF;

      Y2 := Y + grid_step;
      IF Y2 < Ymax THEN
        Y2 := Y2 - border_correction_factor;
      END IF;

      geom := ST_GeomFromText(format('POLYGON((%s %s, %s %2$s, %3$s %4$s, %1$s %4$s, %1$s %2$s))', X, Y, X2, Y2),
                              metric_srid);
      RETURN next;

      X := X + grid_step;
    END LOOP xloop;
    Y := Y + grid_step;
  END LOOP yloop;

  RETURN next;
END;
$body$
LANGUAGE 'plpgsql';
