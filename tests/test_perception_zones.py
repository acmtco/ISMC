from services.perception.zones import Zone, assign_zone, ground_point, point_in_polygon

SQUARE = [(0, 0), (100, 0), (100, 100), (0, 100)]


def test_ground_point_is_bottom_center():
    assert ground_point([10, 20, 30, 40]) == (25, 60)


def test_point_in_polygon_inside_and_outside():
    assert point_in_polygon((50, 50), SQUARE) is True
    assert point_in_polygon((150, 50), SQUARE) is False


def test_point_in_polygon_boundary_cases_do_not_crash():
    # горизонтальная граница у верхней/нижней стороны — не должно падать
    point_in_polygon((50, 0), SQUARE)
    point_in_polygon((50, 100), SQUARE)


def test_assign_zone_prefers_ground_point_over_bbox_center():
    tall_zone = Zone(zone_id="Z-TALL", polygon=[(0, 80), (100, 80), (100, 200), (0, 200)])
    # высокий бокс: центр бокса выше зоны, но опорная точка (низ бокса) — внутри
    bbox = [40, 20, 20, 100]  # bottom = 20+100=120, внутри Z-TALL (80..200)
    assert assign_zone(bbox, [tall_zone]) == "Z-TALL"


def test_assign_zone_returns_none_outside_all_zones():
    zone = Zone(zone_id="Z-A", polygon=SQUARE)
    assert assign_zone([500, 500, 10, 10], [zone]) is None
